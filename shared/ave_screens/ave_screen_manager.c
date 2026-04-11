/**
 * @file ave_screen_manager.c
 * @brief Routes display JSON messages to individual LVGL screens.
 *
 * Depends on cJSON (included with LVGL extras or standalone).
 * If cJSON is not available, link against cJSON.c separately.
 */
#include "ave_screen_manager.h"
#include "ave_json_utils.h"
#include "ave_transport.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Screen implementations (forward declarations) */
void screen_feed_show(const char *json_data);
void screen_feed_reveal(void);
void screen_feed_key(int key);
bool screen_feed_should_ignore_live_push(void);
int screen_feed_get_selected_context_json(char *out, size_t out_n);

void screen_explorer_show(const char *json_data);
void screen_explorer_key(int key);
int screen_explorer_get_selected_context_json(char *out, size_t out_n);

void screen_browse_show(const char *json_data);
void screen_browse_show_placeholder(const char *mode);
void screen_browse_reveal(void);
void screen_browse_key(int key);
int screen_browse_get_selected_context_json(char *out, size_t out_n);

void screen_spotlight_show(const char *json_data);
void screen_spotlight_key(int key);
void screen_spotlight_cancel_back_timer(void);
int screen_spotlight_get_selected_context_json(char *out, size_t out_n);

void screen_confirm_show(const char *json_data);
void screen_confirm_key(int key);
void screen_confirm_cancel_timers(void);
int screen_confirm_get_selected_context_json(char *out, size_t out_n);

void screen_limit_confirm_show(const char *json_data);
void screen_limit_confirm_key(int key);
void screen_limit_confirm_cancel_timers(void);
int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n);

void screen_result_show(const char *json_data);
void screen_result_key(int key);
void screen_result_cancel_timers(void);
int screen_result_get_selected_context_json(char *out, size_t out_n);

void screen_portfolio_show(const char *json_data);
void screen_portfolio_key(int key);
void screen_portfolio_cancel_back_timer(void);
int screen_portfolio_get_selected_context_json(char *out, size_t out_n);

void screen_disambiguation_show(const char *json_data);
void screen_disambiguation_key(int key);
void screen_disambiguation_cancel_timers(void);
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n);

void screen_notify_show(const char *json_data);  /* overlay */

/* ─── State ──────────────────────────────────────────────────────────────── */
static ave_screen_id_t s_current = AVE_SCREEN_FEED;
static ave_screen_id_t s_back_target = AVE_SCREEN_FEED;

static int _json_str(const char *json, const char *key, char *out, size_t out_n);

static void _remember_back_target(ave_screen_id_t current_screen)
{
    if (current_screen == AVE_SCREEN_PORTFOLIO) {
        s_back_target = AVE_SCREEN_PORTFOLIO;
        return;
    }
    if (current_screen == AVE_SCREEN_BROWSE) {
        s_back_target = AVE_SCREEN_BROWSE;
        return;
    }
    if (current_screen == AVE_SCREEN_FEED) {
        s_back_target = AVE_SCREEN_FEED;
    }
}

static void _cancel_pending_navigation_timers(void)
{
    screen_confirm_cancel_timers();
    screen_limit_confirm_cancel_timers();
    screen_spotlight_cancel_back_timer();
    screen_result_cancel_timers();
    screen_portfolio_cancel_back_timer();
    screen_disambiguation_cancel_timers();
}

static void _prepare_primary_screen_transition(ave_screen_id_t next_screen)
{
    if (next_screen != s_current) {
        _cancel_pending_navigation_timers();
    }
}

/* ─── Simple JSON field extractor (no external cJSON dependency) ─────────── */
/**
 * Extract the value of a top-level string field from a flat JSON object.
 * e.g. _json_str(json, "screen", buf, sizeof(buf))
 * Returns 1 on success, 0 if not found.
 */
static int _json_str(const char *json, const char *key, char *out, size_t out_n)
{
    if (!json || !key || !out) return 0;
    /* Find "key" : */
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return 0;
    p += strlen(needle);
    /* Skip whitespace and colon */
    while (*p == ' ' || *p == ':' || *p == '\t') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, out, out_n, NULL);
}

/**
 * Extract the "data" sub-object as a raw JSON string.
 * Returns pointer into json (NOT a copy) and sets *len.
 */
static const char *_json_data_ptr(const char *json, size_t *len)
{
    const char *p = strstr(json, "\"data\"");
    if (!p) { *len = 2; return "{}"; }
    p += 6;
    while (*p == ' ' || *p == ':') p++;
    if (*p != '{' && *p != '[') { *len = 2; return "{}"; }
    const char *start = p;
    char open = *p;
    char close = (open == '{') ? '}' : ']';
    int depth = 1;
    p++;
    while (*p && depth > 0) {
        if (*p == '"') {
            p++;
            while (*p && *p != '"') {
                if (*p == '\\') p++;
                if (*p) p++;
            }
            if (*p) p++;
            continue;
        }
        if (*p == open)  depth++;
        if (*p == close) depth--;
        p++;
    }
    *len = (size_t)(p - start);
    return start;
}

/* ─── Public API ──────────────────────────────────────────────────────────── */

void ave_sm_init(lv_display_t *disp)
{
    (void)disp;
    /* Show initial FEED screen with empty data */
    screen_feed_show("{}");
    s_current = AVE_SCREEN_FEED;
    s_back_target = AVE_SCREEN_FEED;
}

void ave_sm_handle_json(const char *json_str)
{
    if (!json_str) return;

    char screen_id[32] = {0};
    if (!_json_str(json_str, "screen", screen_id, sizeof(screen_id))) {
        return;  /* Not a display message */
    }

    /* Extract data sub-object as raw JSON */
    size_t data_len = 0;
    const char *data_start = _json_data_ptr(json_str, &data_len);

    /* Make a null-terminated copy of data */
    char *data = (char *)malloc(data_len + 1);
    if (!data) return;
    memcpy(data, data_start, data_len);
    data[data_len] = '\0';

    /* Route to screen */
    if (strcmp(screen_id, "feed") == 0) {
        /* Live price refreshes (from WSS) must not yank the user away from
         * spotlight/confirm/etc.  Check for bare boolean "live":true in data. */
        int is_live = 0;
        const char *lp = strstr(data, "\"live\"");
        if (lp) {
            lp += 6;
            while (*lp == ' ' || *lp == ':') lp++;
            if (*lp == 't') is_live = 1;
        }
        if (!is_live ||
            (s_current == AVE_SCREEN_FEED && !screen_feed_should_ignore_live_push())) {
            _prepare_primary_screen_transition(AVE_SCREEN_FEED);
            screen_feed_show(data);
            s_current = AVE_SCREEN_FEED;
            s_back_target = AVE_SCREEN_FEED;
        }
        /* else: live price refresh while user is on another screen — discard.
         * The next WSS push (≤2s) will update feed when they return. */
    } else if (strcmp(screen_id, "spotlight") == 0) {
        /* Same live-update guard as feed: don't yank user back to spotlight. */
        int is_live_sp = 0;
        const char *lsp = strstr(data, "\"live\"");
        if (lsp) { lsp += 6; while (*lsp == ' ' || *lsp == ':') lsp++; if (*lsp == 't') is_live_sp = 1; }
        if (!is_live_sp || s_current == AVE_SCREEN_SPOTLIGHT) {
            _prepare_primary_screen_transition(AVE_SCREEN_SPOTLIGHT);
            _remember_back_target(s_current);
            screen_spotlight_show(data);
            s_current = AVE_SCREEN_SPOTLIGHT;
        }
    } else if (strcmp(screen_id, "confirm") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_CONFIRM);
        _remember_back_target(s_current);
        screen_confirm_show(data);
        s_current = AVE_SCREEN_CONFIRM;
    } else if (strcmp(screen_id, "limit_confirm") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_LIMIT_CONFIRM);
        _remember_back_target(s_current);
        screen_limit_confirm_show(data);
        s_current = AVE_SCREEN_LIMIT_CONFIRM;
    } else if (strcmp(screen_id, "result") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_RESULT);
        _remember_back_target(s_current);
        screen_result_show(data);
        s_current = AVE_SCREEN_RESULT;
    } else if (strcmp(screen_id, "portfolio") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_PORTFOLIO);
        screen_portfolio_show(data);
        s_current = AVE_SCREEN_PORTFOLIO;
        s_back_target = AVE_SCREEN_PORTFOLIO;
    } else if (strcmp(screen_id, "explorer") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_EXPLORER);
        screen_explorer_show(data);
        s_current = AVE_SCREEN_EXPLORER;
    } else if (strcmp(screen_id, "browse") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_BROWSE);
        screen_browse_show(data);
        s_current = AVE_SCREEN_BROWSE;
    } else if (strcmp(screen_id, "disambiguation") == 0) {
        _prepare_primary_screen_transition(AVE_SCREEN_DISAMBIGUATION);
        screen_disambiguation_show(data);
        s_current = AVE_SCREEN_DISAMBIGUATION;
    } else if (strcmp(screen_id, "notify") == 0) {
        screen_notify_show(data);
        /* Notify does NOT change s_current — it's an overlay */
    }

    free(data);
}

ave_screen_id_t ave_sm_get_current_screen_id(void)
{
    return s_current;
}

void ave_sm_key_press(int key)
{
    int is_confirm_waiting_ack = 0;

    /* If NOTIFY overlay is visible, any key dismisses it first */
    if (screen_notify_is_visible()) {
        screen_notify_key(key);
        return;   /* consume the key — don't also navigate */
    }

    if (s_current == AVE_SCREEN_CONFIRM || s_current == AVE_SCREEN_LIMIT_CONFIRM) {
        char context_json[96] = {0};
        int has_context = (s_current == AVE_SCREEN_CONFIRM)
            ? screen_confirm_get_selected_context_json(context_json, sizeof(context_json))
            : screen_limit_confirm_get_selected_context_json(context_json, sizeof(context_json));
        if (has_context && strstr(context_json, "\"awaiting_ack\":true")) {
            is_confirm_waiting_ack = 1;
        }
    }

    /* Global shortcut: Y button → portfolio (works from any screen) */
    if (key == AVE_KEY_Y && s_current != AVE_SCREEN_PORTFOLIO) {
        if (is_confirm_waiting_ack) {
            return;
        }
        if (s_current == AVE_SCREEN_CONFIRM || s_current == AVE_SCREEN_LIMIT_CONFIRM) {
            ave_send_json("{\"type\":\"key_action\",\"action\":\"cancel_trade\"}");
        }
        ave_send_json("{\"type\":\"key_action\",\"action\":\"portfolio\"}");
        printf("[AVE sm] key_action portfolio\n");
        return;
    }

    switch (s_current) {
        case AVE_SCREEN_FEED:          screen_feed_key(key);          break;
        case AVE_SCREEN_EXPLORER:      screen_explorer_key(key);      break;
        case AVE_SCREEN_BROWSE:        screen_browse_key(key);        break;
        case AVE_SCREEN_SPOTLIGHT:     screen_spotlight_key(key);     break;
        case AVE_SCREEN_CONFIRM:       screen_confirm_key(key);       break;
        case AVE_SCREEN_LIMIT_CONFIRM: screen_limit_confirm_key(key); break;
        case AVE_SCREEN_RESULT:        screen_result_key(key);        break;
        case AVE_SCREEN_PORTFOLIO:     screen_portfolio_key(key);     break;
        case AVE_SCREEN_DISAMBIGUATION: screen_disambiguation_key(key); break;
        default: break;
    }
}

void ave_sm_go_to_feed(void)
{
    _cancel_pending_navigation_timers();
    screen_feed_show("{}");
    s_current = AVE_SCREEN_FEED;
    s_back_target = AVE_SCREEN_FEED;
}

void ave_sm_open_feed_cached(void)
{
    _prepare_primary_screen_transition(AVE_SCREEN_FEED);
    screen_feed_reveal();
    s_current = AVE_SCREEN_FEED;
    s_back_target = AVE_SCREEN_FEED;
}

void ave_sm_open_explorer(void)
{
    _prepare_primary_screen_transition(AVE_SCREEN_EXPLORER);
    screen_explorer_show("{}");
    s_current = AVE_SCREEN_EXPLORER;
    ave_send_json("{\"type\":\"key_action\",\"action\":\"explorer_sync\"}");
}

void ave_sm_open_browse(const char *mode)
{
    _prepare_primary_screen_transition(AVE_SCREEN_BROWSE);
    screen_browse_show_placeholder(mode);
    s_current = AVE_SCREEN_BROWSE;
}

void ave_sm_go_back_fallback(void)
{
    _cancel_pending_navigation_timers();
    if (s_back_target == AVE_SCREEN_PORTFOLIO) {
        screen_portfolio_show("{}");
        s_current = AVE_SCREEN_PORTFOLIO;
        return;
    }
    if (s_back_target == AVE_SCREEN_BROWSE) {
        screen_browse_reveal();
        s_current = AVE_SCREEN_BROWSE;
        return;
    }
    screen_feed_reveal();
    s_current = AVE_SCREEN_FEED;
}

int ave_sm_get_selection_context_json(char *out, size_t out_n)
{
    if (!out || out_n == 0) return 0;

    switch (s_current) {
        case AVE_SCREEN_FEED:
            return screen_feed_get_selected_context_json(out, out_n);
        case AVE_SCREEN_EXPLORER:
            return screen_explorer_get_selected_context_json(out, out_n);
        case AVE_SCREEN_BROWSE:
            return screen_browse_get_selected_context_json(out, out_n);
        case AVE_SCREEN_PORTFOLIO:
            return screen_portfolio_get_selected_context_json(out, out_n);
        case AVE_SCREEN_SPOTLIGHT:
            return screen_spotlight_get_selected_context_json(out, out_n);
        case AVE_SCREEN_CONFIRM:
            return screen_confirm_get_selected_context_json(out, out_n);
        case AVE_SCREEN_LIMIT_CONFIRM:
            return screen_limit_confirm_get_selected_context_json(out, out_n);
        case AVE_SCREEN_RESULT:
            return screen_result_get_selected_context_json(out, out_n);
        case AVE_SCREEN_DISAMBIGUATION:
            return screen_disambiguation_get_selected_context_json(out, out_n);
        default:
            return 0;
    }
}

int ave_sm_json_escape_string(const char *src, char *out, size_t out_n)
{
    if (!out || out_n == 0) return 0;

    if (!src) src = "";

    size_t j = 0;
    for (size_t i = 0; src[i]; i++) {
        unsigned char c = (unsigned char)src[i];
        const char *esc = NULL;
        char unicode_buf[7];

        switch (c) {
            case '"':  esc = "\\\""; break;
            case '\\': esc = "\\\\"; break;
            case '\b': esc = "\\b"; break;
            case '\f': esc = "\\f"; break;
            case '\n': esc = "\\n"; break;
            case '\r': esc = "\\r"; break;
            case '\t': esc = "\\t"; break;
            default:
                if (c < 0x20) {
                    snprintf(unicode_buf, sizeof(unicode_buf), "\\u%04x", c);
                    esc = unicode_buf;
                }
                break;
        }

        if (esc) {
            size_t esc_len = strlen(esc);
            if (j + esc_len >= out_n) return 0;
            memcpy(out + j, esc, esc_len);
            j += esc_len;
            continue;
        }

        if (j + 1 >= out_n) return 0;
        out[j++] = (char)c;
    }

    out[j] = '\0';
    return 1;
}

int ave_sm_build_key_action_json(
    const char *action,
    const ave_sm_json_field_t *fields,
    size_t field_count,
    char *out,
    size_t out_n
)
{
    char action_esc[128];
    size_t used = 0;
    int n;

    if (!out || out_n == 0) return 0;
    if (!ave_sm_json_escape_string(action, action_esc, sizeof(action_esc))) return 0;

    n = snprintf(
        out,
        out_n,
        "{\"type\":\"key_action\",\"action\":\"%s\"",
        action_esc
    );
    if (n <= 0 || (size_t)n >= out_n) return 0;
    used = (size_t)n;

    for (size_t i = 0; i < field_count; i++) {
        char key_esc[64];
        char value_esc[384];

        if (!fields || !fields[i].key) return 0;
        if (!ave_sm_json_escape_string(fields[i].key, key_esc, sizeof(key_esc))) return 0;
        if (!ave_sm_json_escape_string(fields[i].value, value_esc, sizeof(value_esc))) return 0;

        n = snprintf(
            out + used,
            out_n - used,
            ",\"%s\":\"%s\"",
            key_esc,
            value_esc
        );
        if (n <= 0 || (size_t)n >= out_n - used) return 0;
        used += (size_t)n;
    }

    n = snprintf(out + used, out_n - used, "}");
    return (n > 0 && (size_t)n < out_n - used) ? 1 : 0;
}

int ave_sm_build_listen_detect_json(const char *text, char *out, size_t out_n)
{
    if (!out || out_n == 0) return 0;

    char escaped_text[512];
    char selection[384];
    int has_selection;
    int n;

    if (!ave_sm_json_escape_string(text, escaped_text, sizeof(escaped_text))) return 0;

    has_selection = ave_sm_get_selection_context_json(selection, sizeof(selection));
    if (has_selection) {
        n = snprintf(
            out,
            out_n,
            "{\"type\":\"listen\",\"state\":\"detect\",\"text\":\"%s\",\"selection\":%s}",
            escaped_text,
            selection
        );
    } else {
        n = snprintf(
            out,
            out_n,
            "{\"type\":\"listen\",\"state\":\"detect\",\"text\":\"%s\"}",
            escaped_text
        );
    }

    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

/* ─── Simulator mock ─────────────────────────────────────────────────────── */
#ifdef LV_SIMULATOR  /* defined in simulator CMakeLists.txt */

#include <dirent.h>

#define MOCK_SCENES_DIR  "mock/mock_scenes"
#define MAX_MOCK_FILES   32

static char s_mock_files[MAX_MOCK_FILES][256];
static int  s_mock_count = 0;
static int  s_mock_idx   = 0;

static void _load_mock_file(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    char *buf = (char *)malloc(sz + 1);
    if (!buf) { fclose(f); return; }
    fread(buf, 1, sz, f);
    buf[sz] = '\0';
    fclose(f);
    ave_sm_handle_json(buf);
    free(buf);
}

static void _scan_mock_scenes(void)
{
    DIR *d = opendir(MOCK_SCENES_DIR);
    if (!d) {
        printf("[AVE mock] Cannot open %s\n", MOCK_SCENES_DIR);
        return;
    }
    struct dirent *ent;
    s_mock_count = 0;
    while ((ent = readdir(d)) && s_mock_count < MAX_MOCK_FILES) {
        if (strstr(ent->d_name, ".json")) {
            snprintf(s_mock_files[s_mock_count], 256,
                     "%s/%s", MOCK_SCENES_DIR, ent->d_name);
            s_mock_count++;
        }
    }
    closedir(d);
    /* Sort by filename so scenes appear in order (01_, 02_, ...) */
    for (int i = 0; i < s_mock_count - 1; i++)
        for (int j = i + 1; j < s_mock_count; j++)
            if (strcmp(s_mock_files[i], s_mock_files[j]) > 0) {
                char tmp[256];
                strcpy(tmp, s_mock_files[i]);
                strcpy(s_mock_files[i], s_mock_files[j]);
                strcpy(s_mock_files[j], tmp);
            }
    printf("[AVE mock] Found %d mock scenes (P = next scene)\n", s_mock_count);
}

void ave_sm_mock_start(void)
{
    _scan_mock_scenes();
    if (s_mock_count > 0)
        _load_mock_file(s_mock_files[0]);
}

void ave_sm_mock_next_scene(void)
{
    if (s_mock_count == 0) return;
    s_mock_idx = (s_mock_idx + 1) % s_mock_count;
    printf("[AVE mock] Scene %d: %s\n", s_mock_idx, s_mock_files[s_mock_idx]);
    _load_mock_file(s_mock_files[s_mock_idx]);
}

#else
/* Non-simulator build — mock functions are no-ops */
void ave_sm_mock_start(void) {}
void ave_sm_mock_next_scene(void) {}
#endif /* LV_SIMULATOR */
