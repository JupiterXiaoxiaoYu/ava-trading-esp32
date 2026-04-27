#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ave_screen_manager.h"
#include "ave_transport.h"
#include "lvgl/lvgl.h"

/* verify_p3_5_minimal is compiled as a standalone probe without linking real LVGL.
 * Provide missing LVGL stubs/constants needed by the production FEED implementation. */
#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif

#ifndef LV_TEXT_ALIGN_LEFT
#define LV_TEXT_ALIGN_LEFT   0
#define LV_TEXT_ALIGN_CENTER 1
#define LV_TEXT_ALIGN_RIGHT  2
#endif

/* ---- Fake LVGL runtime --------------------------------------------------
 * verify_p3_5_minimal is linked without real LVGL. Provide no-op stubs for the
 * subset of LVGL that screen_feed.c pulls in, so this probe can be compiled
 * and run standalone. */
static char *label_text_slot(lv_obj_t *obj);
static void set_screen(int id);

lv_color_t lv_color_hex(uint32_t value)
{
    lv_color_t c;
    c.red   = (uint8_t)((value >> 16) & 0xFFu);
    c.green = (uint8_t)((value >> 8) & 0xFFu);
    c.blue  = (uint8_t)(value & 0xFFu);
    return c;
}

lv_obj_t *lv_obj_create(lv_obj_t *parent)
{
    (void)parent;
    /* lv_obj_t is an opaque type in the public headers; allocate a non-NULL
     * placeholder and never dereference it. */
    return (lv_obj_t *)calloc(1, 1u);
}

void lv_obj_remove_flag(lv_obj_t *obj, lv_obj_flag_t f)
{
    (void)obj;
    (void)f;
}

void lv_obj_set_style_bg_color(lv_obj_t *obj, lv_color_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_bg_opa(lv_obj_t *obj, lv_opa_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_border_width(lv_obj_t *obj, int32_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_pad_left(lv_obj_t *obj, int32_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_pad_right(lv_obj_t *obj, int32_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_pad_top(lv_obj_t *obj, int32_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_pad_bottom(lv_obj_t *obj, int32_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_text_color(lv_obj_t *obj, lv_color_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

void lv_obj_set_width(lv_obj_t *obj, int32_t w)
{
    (void)obj;
    (void)w;
}

void lv_obj_set_size(lv_obj_t *obj, int32_t w, int32_t h)
{
    (void)obj;
    (void)w;
    (void)h;
}

void lv_obj_set_pos(lv_obj_t *obj, int32_t x, int32_t y)
{
    (void)obj;
    (void)x;
    (void)y;
}

void lv_obj_align(lv_obj_t *obj, lv_align_t align, int32_t x_ofs, int32_t y_ofs)
{
    (void)obj;
    (void)align;
    (void)x_ofs;
    (void)y_ofs;
}

void lv_obj_update_layout(const lv_obj_t *obj)
{
    (void)obj;
}

int32_t lv_obj_get_width(const lv_obj_t *obj)
{
    (void)obj;
    return 0;
}

lv_obj_t *lv_label_create(lv_obj_t *parent)
{
    return lv_obj_create(parent);
}

void lv_label_set_text(lv_obj_t *obj, const char *text)
{
    char *slot = label_text_slot(obj);
    if (!slot) return;
    snprintf(slot, 160, "%s", text ? text : "");
}

void lv_label_set_long_mode(lv_obj_t *obj, lv_label_long_mode_t long_mode)
{
    (void)obj;
    (void)long_mode;
}

void lv_screen_load(struct _lv_obj_t *scr)
{
    (void)scr;
}

void lv_obj_set_style_text_align(lv_obj_t *obj, lv_text_align_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

/* Pull in the real FEED implementation under test-only symbol names. */
#define screen_feed_show feed_under_test_show
#define screen_feed_key feed_under_test_key
#define screen_feed_should_ignore_live_push feed_under_test_should_ignore_live_push
#define screen_feed_get_selected_context_json feed_under_test_get_selected_context_json
#include "../../ava-devicekit/reference_apps/ava_box/ui/screen_feed.c"
#undef screen_feed_show
#undef screen_feed_key
#undef screen_feed_should_ignore_live_push
#undef screen_feed_get_selected_context_json

void screen_explorer_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_EXPLORER);
}

void screen_explorer_key(int key)
{
    (void)key;
}

int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_browse_show(const char *json_data)
{
    (void)json_data;
}

void screen_browse_show_placeholder(const char *mode)
{
    (void)mode;
}

void screen_browse_reveal(void)
{
}

void screen_browse_key(int key)
{
    (void)key;
}

int screen_browse_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

const lv_font_t lv_font_montserrat_12 = {0};
const lv_font_t lv_font_montserrat_14 = {0};

static int g_current_screen = -1;
static char g_last_sent[512];
static char g_last_notify[512];
static struct {
    lv_obj_t *obj;
    char text[160];
} g_label_text[256];
static int g_label_text_count = 0;

static char *label_text_slot(lv_obj_t *obj)
{
    int i;

    if (!obj) return NULL;
    for (i = 0; i < g_label_text_count; i++) {
        if (g_label_text[i].obj == obj) return g_label_text[i].text;
    }
    if (g_label_text_count >= (int)(sizeof(g_label_text) / sizeof(g_label_text[0]))) {
        return NULL;
    }
    g_label_text[g_label_text_count].obj = obj;
    g_label_text[g_label_text_count].text[0] = '\0';
    g_label_text_count++;
    return g_label_text[g_label_text_count - 1].text;
}

static const char *label_text(lv_obj_t *obj)
{
    char *slot = label_text_slot(obj);
    return slot ? slot : "";
}

static void set_screen(int id)
{
    g_current_screen = id;
}

static int load_file(const char *path, char **out_buf)
{
    FILE *f = fopen(path, "rb");
    long sz;
    size_t rd;
    char *buf;

    if (!f) return 0;
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return 0;
    }
    sz = ftell(f);
    if (sz < 0) {
        fclose(f);
        return 0;
    }
    rewind(f);

    buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return 0;
    }
    rd = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    if (rd != (size_t)sz) {
        free(buf);
        return 0;
    }
    buf[sz] = '\0';
    *out_buf = buf;
    return 1;
}

static int expect_screen(int expected, const char *msg)
{
    if (g_current_screen != expected) {
        fprintf(stderr,
                "FAIL: %s (expected screen=%d, got=%d)\n",
                msg,
                expected,
                g_current_screen);
        return 0;
    }
    return 1;
}

static int expect_json_contains(const char *needle, const char *msg)
{
    if (!strstr(g_last_sent, needle)) {
        fprintf(stderr,
                "FAIL: %s (last sent=%s)\n",
                msg,
                g_last_sent[0] ? g_last_sent : "<empty>");
        return 0;
    }
    return 1;
}

static int expect_json_empty(const char *msg)
{
    if (g_last_sent[0]) {
        fprintf(stderr,
                "FAIL: %s (last sent=%s)\n",
                msg,
                g_last_sent);
        return 0;
    }
    return 1;
}

static int expect_notify_contains(const char *needle, const char *msg)
{
    if (!strstr(g_last_notify, needle)) {
        fprintf(stderr,
                "FAIL: %s (last notify=%s)\n",
                msg,
                g_last_notify[0] ? g_last_notify : "<empty>");
        return 0;
    }
    return 1;
}

static int expect_notify_empty(const char *msg)
{
    if (g_last_notify[0]) {
        fprintf(stderr,
                "FAIL: %s (last notify=%s)\n",
                msg,
                g_last_notify);
        return 0;
    }
    return 1;
}

static void clear_last_io(void)
{
    g_last_sent[0] = '\0';
    g_last_notify[0] = '\0';
}

static int expect_equal_int(int actual, int expected, const char *msg)
{
    if (actual != expected) {
        fprintf(stderr,
                "FAIL: %s (actual=%d expected=%d)\n",
                msg,
                actual,
                expected);
        return 0;
    }
    return 1;
}

static int expect_string_equal(const char *actual, const char *expected, const char *msg)
{
    if (strcmp(actual ? actual : "", expected ? expected : "") != 0) {
        fprintf(stderr,
                "FAIL: %s (actual=\"%s\" expected=\"%s\")\n",
                msg,
                actual ? actual : "",
                expected ? expected : "");
        return 0;
    }
    return 1;
}

static int expect_string_not_contains(const char *actual, const char *needle, const char *msg)
{
    if ((actual && needle) && strstr(actual, needle)) {
        fprintf(stderr,
                "FAIL: %s (actual=\"%s\" contains \"%s\")\n",
                msg,
                actual,
                needle);
        return 0;
    }
    return 1;
}

static int expect_string_contains(const char *actual, const char *needle, const char *msg)
{
    if (!(actual && needle) || !strstr(actual, needle)) {
        fprintf(stderr,
                "FAIL: %s (actual=\"%s\" missing \"%s\")\n",
                msg,
                actual ? actual : "",
                needle ? needle : "");
        return 0;
    }
    return 1;
}

static const char *k_standard_feed_json =
    "{"
    "\"source_label\":\"TRENDING\","
    "\"tokens\":[{"
    "\"token_id\":\"token-1\","
    "\"chain\":\"solana\","
    "\"symbol\":\"BONK\","
    "\"price\":\"$1\","
    "\"change_24h\":\"+1%\","
    "\"change_positive\":1"
    "}]}";

/* ---- Stubs needed by ave_screen_manager.c and screen_feed.c ------------- */
void ave_send_json(const char *json)
{
    snprintf(g_last_sent, sizeof(g_last_sent), "%s", json ? json : "");
}

/* Keep screen-manager tests isolated with lightweight FEED stubs. */
void screen_feed_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_FEED);
}

void screen_feed_key(int key)
{
    (void)key;
}

bool screen_feed_should_ignore_live_push(void)
{
    return false;
}

void screen_spotlight_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_SPOTLIGHT);
}

void screen_spotlight_key(int key)
{
    if (key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
    }
}

void screen_spotlight_cancel_back_timer(void) {}

void screen_confirm_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_CONFIRM);
}

void screen_confirm_key(int key)
{
    (void)key;
}

void screen_confirm_cancel_timers(void) {}

void screen_limit_confirm_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_LIMIT_CONFIRM);
}

void screen_limit_confirm_key(int key)
{
    (void)key;
}

void screen_limit_confirm_cancel_timers(void) {}

void screen_result_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_RESULT);
}

void screen_result_key(int key)
{
    (void)key;
    ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
}

void screen_result_cancel_timers(void)
{
}

void screen_portfolio_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_PORTFOLIO);
}

void screen_portfolio_key(int key)
{
    if (key == AVE_KEY_X) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"portfolio_sell\"}");
    } else if (key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
    }
}

void screen_portfolio_cancel_back_timer(void) {}

void screen_notify_show(const char *json_data)
{
    snprintf(g_last_notify, sizeof(g_last_notify), "%s", json_data ? json_data : "");
}

bool screen_notify_is_visible(void)
{
    return false;
}

void screen_notify_key(int key)
{
    (void)key;
}

/* Selection context is not exercised by this probe; provide link-time stubs. */
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_result_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_portfolio_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_disambiguation_show(const char *json_data)
{
    (void)json_data;
    set_screen(AVE_SCREEN_DISAMBIGUATION);
}

void screen_disambiguation_key(int key)
{
    (void)key;
}

void screen_disambiguation_cancel_timers(void) {}

int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

static int run_case_portfolio_spotlight_back(void)
{
    char *portfolio = NULL;
    char *spotlight = NULL;
    int ok = 1;

    if (!load_file("mock/mock_scenes/07_portfolio.json", &portfolio)) {
        fprintf(stderr, "FAIL: cannot read 07_portfolio.json\n");
        return 0;
    }
    if (!load_file("mock/mock_scenes/02_spotlight_bonk.json", &spotlight)) {
        fprintf(stderr, "FAIL: cannot read 02_spotlight_bonk.json\n");
        free(portfolio);
        return 0;
    }

    ave_sm_init(NULL);
    ok &= expect_screen(AVE_SCREEN_FEED, "init should start at FEED");

    ave_sm_handle_json(portfolio);
    ok &= expect_screen(AVE_SCREEN_PORTFOLIO, "portfolio scene should enter PORTFOLIO");

    ave_sm_handle_json(spotlight);
    ok &= expect_screen(AVE_SCREEN_SPOTLIGHT, "spotlight scene should enter SPOTLIGHT");

    g_last_sent[0] = '\0';
    ave_sm_key_press(AVE_KEY_B);
    ok &= expect_json_contains("\"action\":\"back\"", "SPOTLIGHT B should request back");

    /* Emulate server-timeout fallback after SPOTLIGHT sends key_action back. */
    ave_sm_go_back_fallback();
    ok &= expect_screen(AVE_SCREEN_PORTFOLIO,
                        "fallback from SPOTLIGHT should prefer PORTFOLIO");

    free(portfolio);
    free(spotlight);
    return ok;
}

static int run_case_portfolio_sell_result_back(void)
{
    char *portfolio = NULL;
    char *result_ok = NULL;
    int ok = 1;

    if (!load_file("mock/mock_scenes/07_portfolio.json", &portfolio)) {
        fprintf(stderr, "FAIL: cannot read 07_portfolio.json\n");
        return 0;
    }
    if (!load_file("mock/mock_scenes/05_result_success.json", &result_ok)) {
        fprintf(stderr, "FAIL: cannot read 05_result_success.json\n");
        free(portfolio);
        return 0;
    }

    ave_sm_init(NULL);
    ave_sm_handle_json(portfolio);
    ok &= expect_screen(AVE_SCREEN_PORTFOLIO, "portfolio scene should enter PORTFOLIO");

    g_last_sent[0] = '\0';
    ave_sm_key_press(AVE_KEY_X);
    ok &= expect_json_contains("\"action\":\"portfolio_sell\"",
                               "PORTFOLIO X should trigger sell action");

    ave_sm_handle_json(result_ok);
    ok &= expect_screen(AVE_SCREEN_RESULT, "result scene should enter RESULT");

    /* Any-key back fallback path from RESULT. */
    ave_sm_handle_json(result_ok);
    ok &= expect_screen(AVE_SCREEN_RESULT, "result re-entry should enter RESULT");

    g_last_sent[0] = '\0';
    ave_sm_key_press(AVE_KEY_A);
    ok &= expect_json_contains("\"action\":\"back\"",
                               "RESULT any key should request back");

    ave_sm_go_back_fallback();
    ok &= expect_screen(AVE_SCREEN_PORTFOLIO,
                        "RESULT key-back fallback should prefer PORTFOLIO");

    free(portfolio);
    free(result_ok);
    return ok;
}

static int run_case_feed_home_b_opens_explore_without_side_effects(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    s_token_idx = 0;
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);

    ok &= expect_json_contains("\"action\":\"explorer_sync\"",
                               "standard FEED B should request explorer sync");
    ok &= expect_notify_empty("standard FEED B should no longer show already-on-home notify");
    ok &= expect_screen(AVE_SCREEN_EXPLORER,
                        "standard FEED B should enter Explorer screen");
    ok &= expect_equal_int(s_token_idx, 0,
                           "opening Explore should preserve FEED cursor");
    return ok;
}

static int run_case_feed_explore_navigation_clamps_and_closes_losslessly(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_UP);
    ok &= expect_equal_int(s_explore_idx, 0, "Explore UP should clamp at Search");

    for (int i = 0; i < FEED_EXPLORE_ITEM_COUNT + 1; i++) {
        feed_under_test_key(AVE_KEY_DOWN);
    }
    ok &= expect_equal_int(s_explore_idx, FEED_EXPLORE_ITEM_COUNT - 1,
                           "Explore DOWN should clamp at Sources");
    ok &= expect_equal_int(_current_explore_item()->surface, FEED_SURFACE_STANDARD,
                           "Orders/Sources entries should stay inside Explore until activated");

    clear_last_io();
    feed_under_test_key(AVE_KEY_X);
    ok &= expect_equal_int(s_explore_idx, FEED_EXPLORE_ITEM_COUNT - 1,
                           "Explore X should stay inert in Task 1");
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_EXPLORE_PANEL,
                           "Explore X should not close or activate anything");
    ok &= expect_json_empty("Explore X should not emit a server action");

    feed_under_test_key(AVE_KEY_LEFT);
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_STANDARD,
                           "Explore LEFT should close back to standard FEED");
    ok &= expect_equal_int(s_token_idx, 0,
                           "closing Explore should preserve FEED cursor");
    ok &= expect_json_empty("closing Explore should not emit a server action");
    return ok;
}

static int run_case_feed_explore_search_entry_is_local(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_EXPLORE_SEARCH_GUIDE,
                           "Search should open the local guidance surface");
    ok &= expect_equal_int(_current_surface_model()->is_overlay_local, 1,
                           "Search guide should remain a local FEED overlay");
    ok &= expect_json_empty("Search guide entry should not send a server action");

    clear_last_io();
    feed_under_test_key(AVE_KEY_LEFT);
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_STANDARD,
                           "Search guide LEFT should close back to standard FEED");
    ok &= expect_equal_int(s_token_idx, 0,
                           "Search guide close should preserve FEED cursor");
    ok &= expect_json_empty("Search guide close should not emit a server action");
    return ok;
}

static int run_case_feed_explore_orders_activation_reuses_orders_flow(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_json_contains("\"action\":\"orders\"",
                               "Explore Orders should emit orders key_action");
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_STANDARD,
                           "Explore Orders should close back to standard FEED after dispatch");
    ok &= expect_equal_int(s_token_idx, 0,
                           "Explore Orders dispatch should preserve FEED cursor");
    return ok;
}

static int run_case_feed_explore_sources_platform_activation_reuses_platform_feed(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_EXPLORE_SOURCES,
                           "Explore Sources should first open the local sources chooser");
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_json_contains("\"action\":\"feed_platform\"",
                               "Explore Sources should reuse the platform feed action");
    ok &= expect_json_contains("\"platform\":\"pump_in_hot\"",
                               "Explore Sources should use the existing platform tag values");
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_STANDARD,
                           "Sources selection should close back to standard FEED after dispatch");
    ok &= expect_equal_int(s_token_idx, 0,
                           "Sources selection should preserve FEED cursor");
    return ok;
}

static int run_case_feed_special_back_exits_to_standard_source(void)
{
    int ok = 1;

    const char *gainer_feed =
        "{"
        "\"source_label\":\"GAINER\"," 
        "\"tokens\":[{"
        "\"token_id\":\"token-gainer\"," 
        "\"chain\":\"solana\"," 
        "\"symbol\":\"GAIN\"," 
        "\"price\":\"$1\"," 
        "\"change_24h\":\"+1%\"," 
        "\"change_positive\":1"
        "}]}";

    const char *search_feed =
        "{"
        "\"source_label\":\"SEARCH\"," 
        "\"tokens\":[{"
        "\"token_id\":\"token-search\"," 
        "\"chain\":\"solana\"," 
        "\"symbol\":\"SRCH\"," 
        "\"price\":\"$2\"," 
        "\"change_24h\":\"+2%\"," 
        "\"change_positive\":1"
        "}]}";

    feed_under_test_show(gainer_feed);
    feed_under_test_show(search_feed);

    clear_last_io();
    feed_under_test_key(AVE_KEY_B);

    ok &= expect_json_contains("\"action\":\"feed_source\"",
                               "special source B should request return to main feed source");
    ok &= expect_json_contains("\"source\":\"gainer\"",
                               "special source B should restore remembered standard source");
    ok &= expect_notify_empty("special source B should not show 'already on home' notify");
    return ok;
}

static int run_case_feed_a_enters_detail_like_right(void)
{
    int ok = 1;

    const char *feed =
        "{"
        "\"source_label\":\"TRENDING\"," 
        "\"tokens\":[{"
        "\"token_id\":\"token-a-watch\"," 
        "\"chain\":\"solana\"," 
        "\"symbol\":\"AWATCH\"," 
        "\"price\":\"$3\"," 
        "\"change_24h\":\"+3%\"," 
        "\"change_positive\":1"
        "}]}";

    feed_under_test_show(feed);

    clear_last_io();
    feed_under_test_key(AVE_KEY_A);
    ok &= expect_json_contains("\"action\":\"watch\"", "FEED A should enter detail");
    ok &= expect_json_contains("\"token_id\":\"token-a-watch\"", "FEED A should pass selected token id");

    clear_last_io();
    feed_under_test_key(AVE_KEY_RIGHT);
    ok &= expect_json_contains("\"action\":\"watch\"", "FEED RIGHT should still enter detail");
    ok &= expect_json_contains("\"token_id\":\"token-a-watch\"", "FEED RIGHT should keep selected token id");
    return ok;
}

static int run_case_feed_special_left_stays_disabled(void)
{
    int ok = 1;

    const char *search_feed =
        "{"
        "\"source_label\":\"SEARCH\"," 
        "\"tokens\":[{"
        "\"token_id\":\"token-special\"," 
        "\"chain\":\"solana\"," 
        "\"symbol\":\"NOLEFT\"," 
        "\"price\":\"$4\"," 
        "\"change_24h\":\"+4%\"," 
        "\"change_positive\":1"
        "}]}";

    feed_under_test_show(search_feed);

    clear_last_io();
    feed_under_test_key(AVE_KEY_LEFT);

    ok &= expect_json_empty("special source LEFT should stay disabled");
    ok &= expect_notify_contains("切换来源",
                                 "special source LEFT should continue to explain disabled source switching");
    return ok;
}

static int run_case_feed_orders_back_unchanged(void)
{
    int ok = 1;

    const char *orders_feed =
        "{"
        "\"mode\":\"orders\"," 
        "\"source_label\":\"ORDERS\"," 
        "\"tokens\":[{"
        "\"token_id\":\"order-1\"," 
        "\"chain\":\"solana\"," 
        "\"symbol\":\"ORD\"," 
        "\"price\":\"$5\"," 
        "\"change_24h\":\"0%\"," 
        "\"change_positive\":1"
        "}]}";

    feed_under_test_show(orders_feed);

    clear_last_io();
    feed_under_test_key(AVE_KEY_B);

    ok &= expect_json_contains("\"action\":\"back\"", "orders mode B should still request back");
    return ok;
}


static int run_case_feed_symbol_hides_contract_tail_suffix(void)
{
    int ok = 1;
    const char *feed =
        "{"
        "\"source_label\":\"TRENDING\","
        "\"tokens\":[{"
        "\"token_id\":\"token-tail-1\","
        "\"chain\":\"solana\","
        "\"symbol\":\"CRCLx\","
        "\"contract_tail\":\"3b\","
        "\"price\":\"$86.7846\","
        "\"change_24h\":\"-6.87%\","
        "\"change_positive\":0"
        "}]}";
    const char *sym_text;

    feed_under_test_show(feed);
    sym_text = label_text(s_rows[0].lbl_sym);

    ok &= expect_string_equal(sym_text, "CRCLx",
                              "FEED symbol column should not append contract tail");
    ok &= expect_string_not_contains(sym_text, "*",
                                     "FEED symbol column should stay clean without suffix markers");
    return ok;
}

static int run_case_feed_symbol_hides_source_tag_suffix(void)
{
    int ok = 1;
    const char *feed =
        "{"
        "\"source_label\":\"TRENDING\","
        "\"tokens\":[{"
        "\"token_id\":\"token-source-1\","
        "\"chain\":\"solana\","
        "\"symbol\":\"MOODENG\","
        "\"source_tag\":\"solana\","
        "\"price\":\"$0.42\","
        "\"change_24h\":\"+8.10%\","
        "\"change_positive\":1"
        "}]}";
    const char *sym_text;

    feed_under_test_show(feed);
    sym_text = label_text(s_rows[0].lbl_sym);

    ok &= expect_string_equal(sym_text, "MOODENG",
                              "FEED symbol column should not append source/platform suffixes");
    ok &= expect_string_not_contains(sym_text, "solana",
                                     "FEED symbol column should hide source_tag text");
    return ok;
}

static int run_case_feed_live_update_preserves_cursor(void)
{
    int ok = 1;
    char selection_json[256];
    const char *initial_feed =
        "{"
        "\"source_label\":\"TRENDING\","
        "\"tokens\":["
        "{"
        "\"token_id\":\"token-1\","
        "\"chain\":\"solana\","
        "\"symbol\":\"FIRST\","
        "\"price\":\"$1\","
        "\"change_24h\":\"+1%\","
        "\"change_positive\":1"
        "},"
        "{"
        "\"token_id\":\"token-2\","
        "\"chain\":\"base\","
        "\"symbol\":\"SECOND\","
        "\"price\":\"$2\","
        "\"change_24h\":\"+2%\","
        "\"change_positive\":1"
        "}]}";
    const char *live_feed =
        "{"
        "\"source_label\":\"TRENDING\","
        "\"live\": true,"
        "\"tokens\":["
        "{"
        "\"token_id\":\"token-1\","
        "\"chain\":\"solana\","
        "\"symbol\":\"FIRST\","
        "\"price\":\"$1.1\","
        "\"change_24h\":\"+1.1%\","
        "\"change_positive\":1"
        "},"
        "{"
        "\"token_id\":\"token-2\","
        "\"chain\":\"base\","
        "\"symbol\":\"SECOND\","
        "\"price\":\"$2.2\","
        "\"change_24h\":\"+2.2%\","
        "\"change_positive\":1"
        "}]}";

    feed_under_test_show(initial_feed);
    feed_under_test_key(AVE_KEY_DOWN);
    ok &= expect_equal_int(s_token_idx, 1, "sanity: DOWN should move FEED cursor to second token");

    feed_under_test_show(live_feed);
    ok &= expect_equal_int(s_token_idx, 1,
                           "live FEED refresh should preserve the current cursor");
    ok &= expect_equal_int(feed_under_test_get_selected_context_json(selection_json, sizeof(selection_json)), 1,
                           "selection JSON should still be available after a live refresh");
    ok &= expect_string_contains(selection_json, "\"cursor\":1",
                                 "selection JSON after live refresh should keep cursor=1");
    ok &= expect_string_contains(selection_json, "\"addr\":\"token-2\"",
                                 "selection JSON after live refresh should keep the selected token");
    return ok;
}

static int run_case_result_y_portfolio_shortcut_variant(const char *scene_path)
{
    char *scene = NULL;
    int ok = 1;

    if (!load_file(scene_path, &scene)) {
        fprintf(stderr, "FAIL: cannot read %s\n", scene_path);
        return 0;
    }

    ave_sm_init(NULL);
    ave_sm_handle_json(scene);
    ok &= expect_screen(AVE_SCREEN_RESULT, "result scene should enter RESULT");

    clear_last_io();
    ave_sm_key_press(AVE_KEY_Y);
    ok &= expect_json_contains("\"action\":\"portfolio\"",
                               "RESULT Y should request portfolio");

    free(scene);
    return ok;
}

int main(void)
{
    int ok1 = run_case_portfolio_spotlight_back();
    int ok2 = run_case_portfolio_sell_result_back();
    int ok3 = run_case_feed_home_b_opens_explore_without_side_effects();
    int ok6 = run_case_feed_special_back_exits_to_standard_source();
    int ok7 = run_case_feed_a_enters_detail_like_right();
    int ok8 = run_case_feed_special_left_stays_disabled();
    int ok9 = run_case_feed_orders_back_unchanged();
    int ok10 = run_case_result_y_portfolio_shortcut_variant("mock/mock_scenes/05_result_success.json");
    int ok11 = run_case_result_y_portfolio_shortcut_variant("mock/mock_scenes/06_result_fail.json");
    int ok14 = run_case_feed_symbol_hides_contract_tail_suffix();
    int ok15 = run_case_feed_symbol_hides_source_tag_suffix();
    int ok16 = run_case_feed_live_update_preserves_cursor();
    if (ok1 && ok2 && ok3 && ok6 && ok7 && ok8 && ok9 && ok10 && ok11 &&
        ok14 && ok15 && ok16) {
        printf("PASS: P3-5 minimal simulator fallback verification succeeded.\n");
        return 0;
    }
    return 1;
}
