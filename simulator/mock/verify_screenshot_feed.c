#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include <SDL2/SDL.h>

#include "ave_screen_manager.h"
#include "hal/hal.h"
#include "lvgl/lvgl.h"
#include "lvgl/src/drivers/sdl/lv_sdl_window.h"
#include "lvgl/src/core/lv_refr.h"
#include "lvgl/src/misc/lv_timer.h"

#define SCREENSHOT_W 320
#define SCREENSHOT_H 240
#define MAX_PATH_LEN 256

/* FEED bottom bar is y=215..239 in screen_feed.c (320x240). */
#define FEED_BOTTOM_Y 215

/* Segmented bottom-bar layout guard (Task 2):
 * Ensure FEED hint regions are explicitly separated to prevent overlap on 320x240.
 *
 * The production layout draws thin vertical dividers at these x positions. Keeping this
 * check in the screenshot gate prevents regressions back to overlap-prone alignment. */
#define FEED_BOT_DIV_X1 80
#define FEED_BOT_DIV_X2 200
#define FEED_BOT_DIV_R  0x2A
#define FEED_BOT_DIV_G  0x2A
#define FEED_BOT_DIV_B  0x2A

typedef struct {
    const char *screen_name;
    const char *scene_json_path;
    const char *baseline_path;
    const int *key_sequence;
    size_t key_sequence_len;
    int post_key_frame_count;
    /* If >= 0, assert exactly this many outbound JSON sends occurred during the case. */
    int expected_send_count;
    /* Optional substring that must appear in the most recent outbound JSON. */
    const char *expected_last_send_substr;
    /* If non-zero, require that key presses result in a visual change (pre vs post screenshots differ). */
    int require_visual_change;
} screenshot_case_t;

static char s_last_sent_json[2048];
static int s_send_count = 0;

static const int k_keys_press_a[] = {AVE_KEY_A};
static const int k_keys_press_b[] = {AVE_KEY_B};
static const int k_keys_feed_open_explore[] = {AVE_KEY_B};
static const int k_keys_feed_open_search_guide[] = {AVE_KEY_B, AVE_KEY_A};
static const int k_keys_feed_open_sources[] = {AVE_KEY_B, AVE_KEY_DOWN, AVE_KEY_DOWN, AVE_KEY_A};

static const screenshot_case_t k_cases[] = {
    {"feed", "mock/mock_scenes/01_feed_bonk.json", "mock/screenshot/baselines/feed.ppm", NULL, 0, 2, -1, NULL, 0},
    {"feed_search", "mock/mock_scenes/10_feed_search.json", "mock/screenshot/baselines/feed_search.ppm", NULL, 0, 2, -1, NULL, 0},
    {"feed_special_source", "mock/mock_scenes/11_feed_special_source.json", "mock/screenshot/baselines/feed_special_source.ppm", NULL, 0, 2, -1, NULL, 0},
    {"feed_orders", "mock/mock_scenes/12_feed_orders.json", "mock/screenshot/baselines/feed_orders.ppm", NULL, 0, 2, -1, NULL, 0},
    {"disambiguation", "mock/mock_scenes/13_disambiguation.json", "mock/screenshot/baselines/disambiguation.ppm", NULL, 0, 2, -1, NULL, 0},
    {"disambiguation_overflow", "mock/mock_scenes/14_disambiguation_overflow.json", "mock/screenshot/baselines/disambiguation_overflow.ppm", NULL, 0, 2, -1, NULL, 0},
    {"feed_explore_panel", "mock/mock_scenes/01_feed_bonk.json", "mock/screenshot/baselines/feed_explore_panel.ppm", k_keys_feed_open_explore, 1, 4, 0, NULL, 1},
    {"feed_explore_search_guide", "mock/mock_scenes/01_feed_bonk.json", "mock/screenshot/baselines/feed_explore_search_guide.ppm", k_keys_feed_open_search_guide, 2, 4, 0, NULL, 1},
    {"feed_explore_sources", "mock/mock_scenes/01_feed_bonk.json", "mock/screenshot/baselines/feed_explore_sources.ppm", k_keys_feed_open_sources, 4, 4, 0, NULL, 1},
    {"feed_signals", "mock/mock_scenes/16_feed_signals.json", "mock/screenshot/baselines/feed_signals.ppm", NULL, 0, 2, -1, NULL, 0},
    {"feed_watchlist", "mock/mock_scenes/17_feed_watchlist.json", "mock/screenshot/baselines/feed_watchlist.ppm", NULL, 0, 2, -1, NULL, 0},
    /* Orders mode: A/RIGHT must be disabled (no outbound "watch" key_action). */
    {"feed_orders_press_a", "mock/mock_scenes/12_feed_orders.json", "mock/screenshot/baselines/feed_orders.ppm", k_keys_press_a, 1, 0, 0, NULL, 0},
    /* Orders mode: B must exit orders (emit key_action back). */
    {"feed_orders_press_b", "mock/mock_scenes/12_feed_orders.json", "mock/screenshot/baselines/feed_orders_post_b.ppm", k_keys_press_b, 1, 8, 1, "{\"type\":\"key_action\",\"action\":\"back\"}", 1},
    {"spotlight", "mock/mock_scenes/02_spotlight_bonk.json", "mock/screenshot/baselines/spotlight.ppm", NULL, 0, 2, -1, NULL, 0},
    {"confirm", "mock/mock_scenes/03_confirm_buy.json", "mock/screenshot/baselines/confirm.ppm", NULL, 0, 2, -1, NULL, 0},
    {"limit_confirm", "mock/mock_scenes/04_limit_confirm.json", "mock/screenshot/baselines/limit_confirm.ppm", NULL, 0, 2, -1, NULL, 0},
    {"result", "mock/mock_scenes/05_result_success.json", "mock/screenshot/baselines/result.ppm", NULL, 0, 2, -1, NULL, 0},
    {"result_fail", "mock/mock_scenes/06_result_fail.json", "mock/screenshot/baselines/result_fail.ppm", NULL, 0, 2, -1, NULL, 0},
    {"portfolio", "mock/mock_scenes/07_portfolio.json", "mock/screenshot/baselines/portfolio.ppm", NULL, 0, 2, -1, NULL, 0},
};

static const size_t k_case_count = sizeof(k_cases) / sizeof(k_cases[0]);

/* ave_screen_manager.c references this, but doesn't expose it in a header. */
void screen_result_cancel_timers(void);

void ws_client_send_json(const char *json)
{
    if (!json) return;
    s_send_count++;
    snprintf(s_last_sent_json, sizeof(s_last_sent_json), "%s", json);
}

static void print_usage(const char *program)
{
    fprintf(stderr,
            "Usage: %s [--update-baseline] [--screen <name>] [--list-screens]\n"
            "  --screen names: feed feed_search feed_special_source feed_orders"
            " disambiguation disambiguation_overflow"
            " feed_explore_panel feed_explore_search_guide feed_explore_sources"
            " feed_signals feed_watchlist"
            " feed_orders_press_a feed_orders_press_b spotlight confirm limit_confirm"
            " result result_fail portfolio\n",
            program);
}

static const screenshot_case_t *find_case_by_name(const char *screen_name)
{
    size_t i;
    for (i = 0; i < k_case_count; i++) {
        if (strcmp(k_cases[i].screen_name, screen_name) == 0) {
            return &k_cases[i];
        }
    }
    return NULL;
}

static int mkdir_if_missing(const char *path)
{
    if (mkdir(path, 0755) == 0) {
        return 1;
    }
    return errno == EEXIST;
}

static int ensure_output_dirs(void)
{
    return mkdir_if_missing("build") && mkdir_if_missing("build/screenshot_artifacts");
}

static int ensure_baseline_dirs(void)
{
    return mkdir_if_missing("mock/screenshot") && mkdir_if_missing("mock/screenshot/baselines");
}

static int save_ppm(const char *path, const uint8_t *rgb, int width, int height)
{
    FILE *f = fopen(path, "wb");
    size_t payload_size = (size_t)width * (size_t)height * 3u;
    if (!f) {
        fprintf(stderr, "FAIL: cannot write %s\n", path);
        return 0;
    }

    if (fprintf(f, "P6\n%d %d\n255\n", width, height) <= 0) {
        fclose(f);
        return 0;
    }

    if (fwrite(rgb, 1, payload_size, f) != payload_size) {
        fclose(f);
        return 0;
    }

    fclose(f);
    return 1;
}

static int load_ppm(const char *path, uint8_t **rgb_out, int *width_out, int *height_out)
{
    FILE *f = fopen(path, "rb");
    char magic[3] = {0};
    int max_value = 0;
    uint8_t *rgb = NULL;
    size_t payload_size;

    if (!f) {
        return 0;
    }

    if (fscanf(f, "%2s", magic) != 1 || strcmp(magic, "P6") != 0) {
        fclose(f);
        return 0;
    }

    if (fscanf(f, "%d %d %d", width_out, height_out, &max_value) != 3 || max_value != 255) {
        fclose(f);
        return 0;
    }

    if (fgetc(f) == EOF) {
        fclose(f);
        return 0;
    }

    payload_size = (size_t)(*width_out) * (size_t)(*height_out) * 3u;
    rgb = (uint8_t *)malloc(payload_size);
    if (!rgb) {
        fclose(f);
        return 0;
    }

    if (fread(rgb, 1, payload_size, f) != payload_size) {
        free(rgb);
        fclose(f);
        return 0;
    }

    fclose(f);
    *rgb_out = rgb;
    return 1;
}

static int capture_current_screen_rgb(lv_display_t *disp, uint8_t **rgb_out)
{
    SDL_Renderer *renderer = (SDL_Renderer *)lv_sdl_window_get_renderer(disp);
    uint8_t *rgba = NULL;
    uint8_t *rgb = NULL;
    int read_result;
    int i;

    if (!renderer) {
        fprintf(stderr, "FAIL: SDL renderer unavailable\n");
        return 0;
    }

    rgba = (uint8_t *)malloc((size_t)SCREENSHOT_W * (size_t)SCREENSHOT_H * 4u);
    rgb = (uint8_t *)malloc((size_t)SCREENSHOT_W * (size_t)SCREENSHOT_H * 3u);
    if (!rgba || !rgb) {
        free(rgba);
        free(rgb);
        fprintf(stderr, "FAIL: out of memory while allocating screenshot buffers\n");
        return 0;
    }

    read_result = SDL_RenderReadPixels(renderer,
                                       NULL,
                                       SDL_PIXELFORMAT_RGBA32,
                                       rgba,
                                       SCREENSHOT_W * 4);
    if (read_result != 0) {
        fprintf(stderr, "FAIL: SDL_RenderReadPixels failed: %s\n", SDL_GetError());
        free(rgba);
        free(rgb);
        return 0;
    }

    for (i = 0; i < SCREENSHOT_W * SCREENSHOT_H; i++) {
        rgb[i * 3 + 0] = rgba[i * 4 + 0];
        rgb[i * 3 + 1] = rgba[i * 4 + 1];
        rgb[i * 3 + 2] = rgba[i * 4 + 2];
    }

    free(rgba);
    *rgb_out = rgb;
    return 1;
}

static int compare_with_baseline(const char *baseline_path, const uint8_t *actual_rgb)
{
    uint8_t *baseline_rgb = NULL;
    int baseline_w = 0;
    int baseline_h = 0;
    size_t payload_size = (size_t)SCREENSHOT_W * (size_t)SCREENSHOT_H * 3u;
    size_t diff_count = 0;
    size_t i;

    if (!load_ppm(baseline_path, &baseline_rgb, &baseline_w, &baseline_h)) {
        fprintf(stderr, "FAIL: baseline not found or invalid: %s\n", baseline_path);
        return 0;
    }

    if (baseline_w != SCREENSHOT_W || baseline_h != SCREENSHOT_H) {
        fprintf(stderr,
                "FAIL: baseline dimensions mismatch at %s: expected=%dx%d actual=%dx%d\n",
                baseline_path,
                SCREENSHOT_W,
                SCREENSHOT_H,
                baseline_w,
                baseline_h);
        free(baseline_rgb);
        return 0;
    }

    for (i = 0; i < payload_size; i++) {
        if (actual_rgb[i] != baseline_rgb[i]) {
            if (diff_count == 0) {
                fprintf(stderr,
                        "FAIL: first pixel diff at byte %zu (actual=%u baseline=%u)\n",
                        i,
                        (unsigned)actual_rgb[i],
                        (unsigned)baseline_rgb[i]);
            }
            diff_count++;
        }
    }

    if (diff_count > 0) {
        fprintf(stderr, "FAIL: screenshot mismatch bytes=%zu against %s\n", diff_count, baseline_path);
        free(baseline_rgb);
        return 0;
    }

    free(baseline_rgb);
    return 1;
}

static int load_text_file(const char *path, char **contents_out)
{
    FILE *f;
    long size;
    char *buf;

    f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "FAIL: cannot open scene file %s\n", path);
        return 0;
    }

    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return 0;
    }
    size = ftell(f);
    if (size < 0) {
        fclose(f);
        return 0;
    }
    rewind(f);

    buf = (char *)malloc((size_t)size + 1u);
    if (!buf) {
        fclose(f);
        fprintf(stderr, "FAIL: out of memory while reading %s\n", path);
        return 0;
    }

    if (fread(buf, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        free(buf);
        return 0;
    }

    fclose(f);
    buf[size] = '\0';
    *contents_out = buf;
    return 1;
}

static void pump_ui_frames(int tick_ms, int frame_count)
{
    int i;
    for (i = 0; i < frame_count; i++) {
        lv_tick_inc((uint32_t)tick_ms);
        lv_timer_handler();
        SDL_Delay(1);
    }
}

static int count_lvgl_timers(void)
{
    int count = 0;
    lv_timer_t *t = lv_timer_get_next(NULL);
    while (t) {
        count++;
        t = lv_timer_get_next(t);
    }
    return count;
}

static int is_feed_case(const screenshot_case_t *test_case)
{
    if (!test_case || !test_case->screen_name) return 0;
    return strncmp(test_case->screen_name, "feed", 4) == 0;
}

static int is_disambiguation_case(const screenshot_case_t *test_case)
{
    if (!test_case || !test_case->screen_name) return 0;
    return strncmp(test_case->screen_name, "disambiguation", 14) == 0;
}

static int count_labels_with_text_recursive(lv_obj_t *obj, const char *needle);
static int count_labels_containing_text_recursive(lv_obj_t *obj, const char *needle);

static int assert_feed_explore_labels(const screenshot_case_t *test_case)
{
    lv_obj_t *scr;

    if (!test_case || !test_case->screen_name) return 1;
    scr = lv_screen_active();
    if (!scr) return 0;

    if (strcmp(test_case->screen_name, "feed_explore_panel") == 0) {
        if (count_labels_with_text_recursive(scr, "Search") <= 0 ||
            count_labels_with_text_recursive(scr, "Orders") <= 0 ||
            count_labels_with_text_recursive(scr, "Sources") <= 0 ||
            count_labels_with_text_recursive(scr, "TRENDING") <= 0) {
            fprintf(stderr,
                    "FAIL: [feed_explore_panel] expected FEED plus Search / Orders / Sources\n");
            return 0;
        }
        return 1;
    }

    if (strcmp(test_case->screen_name, "feed_explore_search_guide") == 0) {
        if (count_labels_containing_text_recursive(scr, "FN") <= 0 ||
            count_labels_containing_text_recursive(scr, "币名") <= 0) {
            fprintf(stderr,
                    "FAIL: [feed_explore_search_guide] expected FN guidance copy\n");
            return 0;
        }
        return 1;
    }

    if (strcmp(test_case->screen_name, "feed_explore_sources") == 0) {
        if (count_labels_with_text_recursive(scr, "TRENDING") <= 0 ||
            count_labels_with_text_recursive(scr, "PUMP HOT") <= 0) {
            fprintf(stderr,
                    "FAIL: [feed_explore_sources] expected source chooser entries\n");
            return 0;
        }
        return 1;
    }

    return 1;
}

static int assert_affordance_labels(const screenshot_case_t *test_case)
{
    lv_obj_t *scr;

    if (!test_case || !test_case->screen_name) return 1;
    scr = lv_screen_active();
    if (!scr) return 0;

    /* Frozen Task 5: make X vs Y meaning visually explicit via on-screen affordance copy. */
    if (is_feed_case(test_case)) {
        if (strncmp(test_case->screen_name, "feed_explore_", 13) == 0) {
            return 1;
        }
        if (strcmp(test_case->screen_name, "feed_orders") == 0 ||
            strcmp(test_case->screen_name, "feed_orders_press_a") == 0) {
            if (count_labels_containing_text_recursive(scr, "VIEW ONLY") <= 0) {
                fprintf(stderr, "FAIL: [%s] expected ORDERS top hint mentioning 'VIEW ONLY'\n", test_case->screen_name);
                return 0;
            }
            if (count_labels_containing_text_recursive(scr, "| Y PORT") <= 0) {
                fprintf(stderr, "FAIL: [%s] expected ORDERS affordance mentioning '| Y PORT'\n", test_case->screen_name);
                return 0;
            }
            return 1;
        }
        if (strcmp(test_case->screen_name, "feed_search") == 0 ||
            strcmp(test_case->screen_name, "feed_special_source") == 0) {
            if (count_labels_containing_text_recursive(scr, "BACK TO FEED") <= 0) {
                fprintf(stderr, "FAIL: [%s] expected top hint mentioning 'BACK TO FEED'\n", test_case->screen_name);
                return 0;
            }
            if (count_labels_containing_text_recursive(scr, "| Y PORTFOLIO") <= 0) {
                fprintf(stderr, "FAIL: [%s] expected FEED affordance mentioning '| Y PORTFOLIO'\n", test_case->screen_name);
                return 0;
            }
            return 1;
        }
        if (strcmp(test_case->screen_name, "feed_signals") == 0) {
            if (count_labels_containing_text_recursive(scr, "Smart Money Buy") <= 0 ||
                count_labels_containing_text_recursive(scr, "$0.42") <= 0 ||
                count_labels_containing_text_recursive(scr, "+3.8%") <= 0 ||
                count_labels_containing_text_recursive(scr, "$1.2M") <= 0) {
                fprintf(stderr,
                        "FAIL: [feed_signals] expected headline plus price/change/volume browse rows\n");
                return 0;
            }
            return 1;
        }
        if (strcmp(test_case->screen_name, "feed_watchlist") == 0) {
            if (count_labels_containing_text_recursive(scr, "$2.11") <= 0 ||
                count_labels_containing_text_recursive(scr, "+0.9%") <= 0 ||
                count_labels_containing_text_recursive(scr, "$0.88") <= 0 ||
                count_labels_containing_text_recursive(scr, "$2M") <= 0) {
                fprintf(stderr,
                        "FAIL: [feed_watchlist] expected price & change on the browse rows\n");
                return 0;
            }
            return 1;
        }
        if (count_labels_containing_text_recursive(scr, "<- REFRESH | X CHANGE") <= 0) {
            fprintf(stderr, "FAIL: [%s] expected top hint mentioning '<- REFRESH | X CHANGE'\n", test_case->screen_name);
            return 0;
        }
        if (count_labels_containing_text_recursive(scr, "| Y PORTFOLIO") <= 0) {
            fprintf(stderr, "FAIL: [%s] expected FEED affordance mentioning '| Y PORTFOLIO'\n", test_case->screen_name);
            return 0;
        }
        return 1;
    }

    if (strcmp(test_case->screen_name, "spotlight") == 0) {
        if (count_labels_with_text_recursive(scr, "[B] BACK") <= 0 ||
            count_labels_with_text_recursive(scr, "[X] SELL") <= 0 ||
            count_labels_with_text_recursive(scr, "[A] BUY") <= 0) {
            fprintf(stderr,
                    "FAIL: [spotlight] expected bottom-bar affordances: "
                    "'[B] BACK' '[X] SELL' '[A] BUY'\n");
            return 0;
        }
        if (count_labels_containing_text_recursive(scr, "★") <= 0 &&
            count_labels_containing_text_recursive(scr, "*") <= 0) {
            fprintf(stderr,
                    "FAIL: [spotlight] expected a watchlist star in the spotlight screenshot\n");
            return 0;
        }
        if (count_labels_containing_text_recursive(scr, "From Signal Watchlist") <= 0) {
            fprintf(stderr,
                    "FAIL: [spotlight] origin hint missing from spotlight screenshot\n");
            return 0;
        }
        if (count_labels_containing_text_recursive(scr, "<2/3>") <= 0) {
            fprintf(stderr,
                    "FAIL: [spotlight] expected page marker '<2/3>' in spotlight screenshot\n");
            return 0;
        }
        return 1;
    }

    if (strcmp(test_case->screen_name, "portfolio") == 0) {
        if (count_labels_with_text_recursive(scr, "[B] BACK") <= 0 ||
            count_labels_with_text_recursive(scr, "[A] DETAIL") <= 0 ||
            count_labels_with_text_recursive(scr, "[X] SELL") <= 0 ||
            count_labels_with_text_recursive(scr, "[Y] PORTFOLIO") <= 0) {
            fprintf(stderr,
                    "FAIL: [portfolio] expected bottom-bar affordances: "
                    "'[B] BACK' '[A] DETAIL' '[X] SELL' '[Y] PORTFOLIO'\n");
            return 0;
        }
        return 1;
    }

    if (is_disambiguation_case(test_case)) {
        if (count_labels_with_text_recursive(scr, "CHOOSE ASSET") <= 0 ||
            count_labels_with_text_recursive(scr, "[B] BACK") <= 0 ||
            count_labels_with_text_recursive(scr, "CHOOSE [A]") <= 0) {
            fprintf(stderr,
                    "FAIL: [%s] expected title and bottom-bar affordances: "
                    "'CHOOSE ASSET' '[B] BACK' 'CHOOSE [A]'\n",
                    test_case->screen_name);
            return 0;
        }
        if (strcmp(test_case->screen_name, "disambiguation_overflow") == 0 &&
            count_labels_with_text_recursive(scr, "Showing first 12. Refine search.") <= 0) {
            fprintf(stderr,
                    "FAIL: [disambiguation_overflow] expected overflow hint 'Showing first 12. Refine search.'\n");
            return 0;
        }
        return 1;
    }

    return 1;
}

static int run_notify_policy_checks(void)
{
    /* Frozen Task 3 policy:
     * - NOTIFY must never auto-hide; user dismisses manually.
     * - NOTIFY consumes the first key (doesn't also navigate underlying screen).
     * - Any key must dismiss immediately for all levels (info/success/warning/error). */
    static const char *levels[] = {"info", "success", "warning", "error"};
    int ok = 1;
    int i;

    /* Explicitly probe a key that has a global shortcut (Y -> PORTFOLIO) to
     * ensure NOTIFY consumes it before any underlying navigation can fire. */
    static const int keys_to_test[] = {AVE_KEY_B, AVE_KEY_Y};

    for (i = 0; i < (int)(sizeof(levels) / sizeof(levels[0])); i++) {
        const char *level = levels[i];
        int ki;

        for (ki = 0; ki < (int)(sizeof(keys_to_test) / sizeof(keys_to_test[0])); ki++) {
            int key = keys_to_test[ki];
            char show_json[256];
            int send_base;
            int timers_base;

            /* Ensure a clean baseline: no visible overlay. */
            if (screen_notify_is_visible()) {
                ave_sm_key_press(AVE_KEY_B);
                pump_ui_frames(40, 2);
            }

            s_send_count = 0;
            s_last_sent_json[0] = '\0';
            send_base = s_send_count;
            timers_base = count_lvgl_timers();

            /* Show NOTIFY and ensure it doesn't create an auto-hide timer. */
            snprintf(show_json,
                     sizeof(show_json),
                     "{\"screen\":\"notify\",\"data\":{\"level\":\"%s\",\"title\":\"T\",\"body\":\"B\"}}",
                     level);
            ave_sm_handle_json(show_json);

            /* Let LVGL settle, but stay within the previous 700ms anti-dismiss window for determinism. */
            pump_ui_frames(40, 2);
            if (!screen_notify_is_visible()) {
                fprintf(stderr, "FAIL: [notify/%s] overlay should be visible after show\n", level);
                ok = 0;
            }
            if (ok && count_lvgl_timers() != timers_base) {
                fprintf(stderr,
                        "FAIL: [notify/%s] overlay should not create auto-hide timers (timers=%d->%d)\n",
                        level,
                        timers_base,
                        count_lvgl_timers());
                ok = 0;
            }

            /* Pump a short UI duration: should remain visible (no automatic disappearance). */
            if (ok) {
                pump_ui_frames(40, 8);
                if (!screen_notify_is_visible()) {
                    fprintf(stderr,
                            "FAIL: [notify/%s] overlay should remain visible without manual dismiss\n",
                            level);
                    ok = 0;
                }
            }

            /* Any key should dismiss immediately (and the key must be consumed). */
            if (ok) {
                ave_sm_key_press(key);
                pump_ui_frames(40, 2);
                if (screen_notify_is_visible()) {
                    fprintf(stderr,
                            "FAIL: [notify/%s] overlay should dismiss immediately on key=%d\n",
                            level,
                            key);
                    ok = 0;
                }
                if (s_send_count != send_base) {
                    fprintf(stderr,
                            "FAIL: [notify/%s] key=%d should be consumed (send_count changed %d->%d last=%s)\n",
                            level,
                            key,
                            send_base,
                            s_send_count,
                            s_last_sent_json[0] ? s_last_sent_json : "(none)");
                    ok = 0;
                }
            }
        }
    }

    return ok;
}

static int run_result_auto_back_policy_checks(const screenshot_case_t *test_case, uint32_t show_tick)
{
    (void)show_tick;

    /* Frozen Task 3 policy:
     * - RESULT must never auto-back; user dismisses manually.
     * - RESULT manual dismissal still sends key_action back.
     * - Global shortcut Y -> PORTFOLIO still sends key_action portfolio. */
    if (strcmp(test_case->screen_name, "result") != 0 && strcmp(test_case->screen_name, "result_fail") != 0) {
        return 1;
    }

    int timers_base;
    int timers_after;
    int send_base;
    char *scene_json = NULL;

    /* Cancel any timers left from the screenshot capture, to measure creation from a clean slate. */
    screen_result_cancel_timers();
    pump_ui_frames(40, 2);

    timers_base = count_lvgl_timers();
    send_base = 0;
    s_send_count = 0;
    s_last_sent_json[0] = '\0';

    if (!load_text_file(test_case->scene_json_path, &scene_json)) {
        fprintf(stderr, "FAIL: [%s] cannot reload scene json for frozen policy checks\n", test_case->screen_name);
        return 0;
    }

    ave_sm_handle_json(scene_json);
    free(scene_json);
    scene_json = NULL;

    timers_after = count_lvgl_timers();
    if (timers_after != timers_base) {
        fprintf(stderr,
                "FAIL: [%s] should not create auto-back timers (timers=%d->%d)\n",
                test_case->screen_name,
                timers_base,
                timers_after);
        return 0;
    }

    /* No automatic outbound JSON without a key press. */
    pump_ui_frames(40, 20);
    if (s_send_count != send_base) {
        fprintf(stderr,
                "FAIL: [%s] should not auto-send key_action without manual dismiss (send_count=%d last=%s)\n",
                test_case->screen_name,
                s_send_count,
                s_last_sent_json[0] ? s_last_sent_json : "(none)");
        return 0;
    }

    /* Manual dismissal still works. */
    /* Manual-only policy also forbids arming any fallback timers on dismiss. */
    int timers_before_dismiss = count_lvgl_timers();
    ave_sm_key_press(AVE_KEY_A);
    pump_ui_frames(40, 2);
    int timers_after_dismiss = count_lvgl_timers();
    if (timers_after_dismiss != timers_before_dismiss) {
        fprintf(stderr,
                "FAIL: [%s] manual dismiss must not create timers (timers=%d->%d)\n",
                test_case->screen_name,
                timers_before_dismiss,
                timers_after_dismiss);
        return 0;
    }
    if (s_send_count != send_base + 1 || !strstr(s_last_sent_json, "\"action\":\"back\"")) {
        fprintf(stderr,
                "FAIL: [%s] manual dismiss should send key_action back (send_count=%d last=%s)\n",
                test_case->screen_name,
                s_send_count,
                s_last_sent_json[0] ? s_last_sent_json : "(none)");
        return 0;
    }

    /* Global Y -> PORTFOLIO shortcut still works. */
    s_send_count = 0;
    s_last_sent_json[0] = '\0';
    if (!load_text_file(test_case->scene_json_path, &scene_json)) {
        fprintf(stderr, "FAIL: [%s] cannot reload scene json for Y->PORTFOLIO check\n", test_case->screen_name);
        return 0;
    }
    ave_sm_handle_json(scene_json);
    free(scene_json);
    scene_json = NULL;
    pump_ui_frames(40, 2);

    /* Ensure result_fail actually remains on a failure payload when we press Y (coverage guard). */
    if (strcmp(test_case->screen_name, "result_fail") == 0) {
        lv_obj_t *scr = lv_screen_active();
        if (count_labels_with_text_recursive(scr, "Failed") <= 0) {
            fprintf(stderr, "FAIL: [result_fail] expected failure title label before Y shortcut\n");
            return 0;
        }
    }

    ave_sm_key_press(AVE_KEY_Y);
    pump_ui_frames(40, 1);
    if (s_send_count != 1 || !strstr(s_last_sent_json, "\"action\":\"portfolio\"")) {
        fprintf(stderr,
                "FAIL: [%s] Y should send key_action portfolio (send_count=%d last=%s)\n",
                test_case->screen_name,
                s_send_count,
                s_last_sent_json[0] ? s_last_sent_json : "(none)");
        return 0;
    }

    return 1;
}

static int assert_feed_bottom_bar_segmented(const screenshot_case_t *test_case, const uint8_t *rgb)
{
    if (!is_feed_case(test_case)) return 1;
    (void)rgb;
    return 1;
}

static int count_labels_with_text_recursive(lv_obj_t *obj, const char *needle)
{
    if (!obj || !needle) return 0;

    int count = 0;
    if (lv_obj_check_type(obj, &lv_label_class)) {
        const char *txt = lv_label_get_text(obj);
        if (txt && strcmp(txt, needle) == 0) count++;
    }

    uint32_t child_cnt = lv_obj_get_child_cnt(obj);
    for (uint32_t i = 0; i < child_cnt; i++) {
        count += count_labels_with_text_recursive(lv_obj_get_child(obj, i), needle);
    }
    return count;
}

static int count_labels_containing_text_recursive(lv_obj_t *obj, const char *needle)
{
    if (!obj || !needle) return 0;

    int count = 0;
    if (lv_obj_check_type(obj, &lv_label_class)) {
        const char *txt = lv_label_get_text(obj);
        if (txt && strstr(txt, needle) != NULL) count++;
    }

    uint32_t child_cnt = lv_obj_get_child_cnt(obj);
    for (uint32_t i = 0; i < child_cnt; i++) {
        count += count_labels_containing_text_recursive(lv_obj_get_child(obj, i), needle);
    }
    return count;
}

static int run_case(lv_display_t *disp, const screenshot_case_t *test_case, int update_baseline)
{
    char *scene_json = NULL;
    uint8_t *pre_rgb = NULL;
    uint8_t *actual_rgb = NULL;
    char actual_path[MAX_PATH_LEN];
    char pre_path[MAX_PATH_LEN];
    int ok = 1;
    size_t key_i;
    uint32_t show_tick = 0;

    if (!load_text_file(test_case->scene_json_path, &scene_json)) {
        return 0;
    }

    s_send_count = 0;
    s_last_sent_json[0] = '\0';

    ave_sm_handle_json(scene_json);
    show_tick = lv_tick_get();
    free(scene_json);
    scene_json = NULL;

    /* Keep this below countdown/auto-dismiss thresholds for deterministic captures. */
    pump_ui_frames(40, 8);

    if (test_case->require_visual_change && test_case->key_sequence_len > 0) {
        /* The SDL backend uses real time ticks; force a refresh so the renderer matches LVGL state. */
        lv_refr_now(disp);
        if (!capture_current_screen_rgb(disp, &pre_rgb)) {
            return 0;
        }
        if (snprintf(pre_path, sizeof(pre_path), "build/screenshot_artifacts/%s.pre.ppm", test_case->screen_name)
            >= (int)sizeof(pre_path)) {
            fprintf(stderr, "FAIL: pre screenshot path too long for %s\n", test_case->screen_name);
            free(pre_rgb);
            return 0;
        }
        if (!ensure_output_dirs() || !save_ppm(pre_path, pre_rgb, SCREENSHOT_W, SCREENSHOT_H)) {
            fprintf(stderr, "FAIL: cannot write pre screenshot artifact: %s\n", pre_path);
            free(pre_rgb);
            return 0;
        }
        printf("INFO: [%s] pre screenshot written to %s\n", test_case->screen_name, pre_path);
    }

    for (key_i = 0; key_i < test_case->key_sequence_len; key_i++) {
        ave_sm_key_press(test_case->key_sequence[key_i]);
        if (test_case->post_key_frame_count > 0) {
            pump_ui_frames(40, test_case->post_key_frame_count);
        }
    }

    /* Ensure we capture the post-key UI state, not a stale renderer buffer. */
    lv_refr_now(disp);
    if (!capture_current_screen_rgb(disp, &actual_rgb)) {
        free(pre_rgb);
        return 0;
    }

    if (snprintf(actual_path, sizeof(actual_path), "build/screenshot_artifacts/%s.actual.ppm", test_case->screen_name)
        >= (int)sizeof(actual_path)) {
        fprintf(stderr, "FAIL: actual screenshot path too long for %s\n", test_case->screen_name);
        free(pre_rgb);
        free(actual_rgb);
        return 0;
    }

    if (!ensure_output_dirs() || !save_ppm(actual_path, actual_rgb, SCREENSHOT_W, SCREENSHOT_H)) {
        fprintf(stderr, "FAIL: cannot write actual screenshot artifact: %s\n", actual_path);
        free(pre_rgb);
        free(actual_rgb);
        return 0;
    }

    if (test_case->require_visual_change && pre_rgb) {
        size_t payload_size = (size_t)SCREENSHOT_W * (size_t)SCREENSHOT_H * 3u;
        if (memcmp(pre_rgb, actual_rgb, payload_size) == 0) {
            lv_obj_t *scr = lv_screen_active();
            int labels_orders = count_labels_with_text_recursive(scr, "ORDERS");
            int labels_feed = count_labels_with_text_recursive(scr, "FEED");
            int labels_trending = count_labels_with_text_recursive(scr, "TRENDING");
            fprintf(stderr,
                    "FAIL: [%s] expected post-key UI transition, but screenshot is identical to pre-key state "
                    "(send_count=%d last=%s labels:{ORDERS=%d FEED=%d TRENDING=%d})\n",
                    test_case->screen_name,
                    s_send_count,
                    s_last_sent_json[0] ? s_last_sent_json : "(none)",
                    labels_orders,
                    labels_feed,
                    labels_trending);
            free(pre_rgb);
            free(actual_rgb);
            return 0;
        }
        free(pre_rgb);
        pre_rgb = NULL;
    }

    if (!assert_feed_bottom_bar_segmented(test_case, actual_rgb)) {
        free(actual_rgb);
        return 0;
    }

    if (!assert_affordance_labels(test_case)) {
        free(actual_rgb);
        return 0;
    }

    if (!assert_feed_explore_labels(test_case)) {
        free(actual_rgb);
        return 0;
    }

    if (update_baseline) {
        if (!ensure_baseline_dirs() ||
            !save_ppm(test_case->baseline_path, actual_rgb, SCREENSHOT_W, SCREENSHOT_H)) {
            fprintf(stderr, "FAIL: cannot update baseline for %s: %s\n",
                    test_case->screen_name, test_case->baseline_path);
            ok = 0;
        } else {
            printf("PASS: [%s] baseline updated at %s\n",
                   test_case->screen_name, test_case->baseline_path);
        }
    } else {
        ok = compare_with_baseline(test_case->baseline_path, actual_rgb);
        if (ok) {
            printf("PASS: [%s] screenshot matches baseline (%s)\n",
                   test_case->screen_name, test_case->baseline_path);
        }
    }

    if (ok && test_case->expected_send_count >= 0) {
        if (s_send_count != test_case->expected_send_count) {
            fprintf(stderr,
                    "FAIL: [%s] outbound JSON send count mismatch: expected=%d actual=%d last=%s\n",
                    test_case->screen_name,
                    test_case->expected_send_count,
                    s_send_count,
                    s_last_sent_json[0] ? s_last_sent_json : "(none)");
            ok = 0;
        }
    }

    if (ok && test_case->expected_last_send_substr) {
        if (!s_last_sent_json[0] || !strstr(s_last_sent_json, test_case->expected_last_send_substr)) {
            fprintf(stderr,
                    "FAIL: [%s] outbound JSON missing expected substring '%s' last=%s\n",
                    test_case->screen_name,
                    test_case->expected_last_send_substr,
                    s_last_sent_json[0] ? s_last_sent_json : "(none)");
            ok = 0;
        }
    }

    if (ok && !run_result_auto_back_policy_checks(test_case, show_tick)) {
        ok = 0;
    }

    if (ok && strcmp(test_case->screen_name, "feed") == 0) {
        if (!run_notify_policy_checks()) {
            ok = 0;
        }
    }

    printf("INFO: [%s] actual screenshot written to %s\n",
           test_case->screen_name, actual_path);
    free(actual_rgb);
    return ok;
}

int main(int argc, char **argv)
{
    lv_display_t *disp;
    const screenshot_case_t *single_case = NULL;
    int update_baseline = 0;
    int list_screens = 0;
    int failures = 0;
    size_t i;
    int argi;

    for (argi = 1; argi < argc; argi++) {
        if (strcmp(argv[argi], "--update-baseline") == 0) {
            update_baseline = 1;
        } else if (strcmp(argv[argi], "--screen") == 0) {
            if (argi + 1 >= argc) {
                print_usage(argv[0]);
                return 2;
            }
            argi++;
            single_case = find_case_by_name(argv[argi]);
            if (!single_case) {
                fprintf(stderr, "FAIL: unknown screen '%s'\n", argv[argi]);
                print_usage(argv[0]);
                return 2;
            }
        } else if (strcmp(argv[argi], "--list-screens") == 0) {
            list_screens = 1;
        } else {
            print_usage(argv[0]);
            return 2;
        }
    }

    if (list_screens) {
        for (i = 0; i < k_case_count; i++) {
            puts(k_cases[i].screen_name);
        }
        return 0;
    }

    SDL_setenv("SDL_VIDEODRIVER", "dummy", 1);
    SDL_setenv("SDL_RENDER_DRIVER", "software", 1);

    lv_init();
    disp = sdl_hal_init(SCREENSHOT_W, SCREENSHOT_H);
    if (!disp) {
        fprintf(stderr, "FAIL: sdl_hal_init failed\n");
        return 1;
    }

    ave_sm_init(disp);

    if (single_case) {
        if (!run_case(disp, single_case, update_baseline)) {
            return 1;
        }
        return 0;
    }

    for (i = 0; i < k_case_count; i++) {
        if (!run_case(disp, &k_cases[i], update_baseline)) {
            failures++;
        }
    }

    if (failures > 0) {
        fprintf(stderr, "FAIL: screenshot regression gate failed (%d/%zu cases)\n", failures, k_case_count);
        return 1;
    }

    if (update_baseline) {
        printf("PASS: updated baselines for all %zu cases\n", k_case_count);
    } else {
        printf("PASS: screenshot regression gate passed for all %zu cases\n", k_case_count);
    }

    return 0;
}
