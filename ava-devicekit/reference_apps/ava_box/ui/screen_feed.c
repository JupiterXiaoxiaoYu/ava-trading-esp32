/**
 * @file screen_feed.c
 * @brief FEED screen - Solana token list view with FEED-local Explore/Search-guide overlays.
 *
 * Layout (320x240 landscape):
 *   y=  0..21   top bar (22px): [source label (left)] [context hint (mid)] [N/M counter (far right)]
 *              - ORDERS mode tints the top bar orange.
 *   y= 22..213  list (8 rows x 24px): [Symbol 6 chars] [Price] [Change] [Vol]
 *   y=214       divider
 *   y=215..239  bottom bar (25px): [navigation hint (left)] [action hint (right)]
 *
 * Navigation:
 *   Standard FEED home:
 *     LEFT     -> refresh current standard source
 *     X        -> cycle standard source
 *     A/RIGHT  -> enter detail (server-driven "watch")
 *     B        -> open local Explore panel (Search / Orders / Sources)
 *   FEED Explore panel:
 *     UP/DOWN  -> clamp within Search / Orders / Sources
 *     A/RIGHT  -> Search opens local Search guide; Orders reuses ORDERS flow; Sources opens local chooser
 *     LEFT/B   -> close Explore without emitting a server action
 *   FEED Search guide:
 *     LEFT/B   -> close guide back to standard FEED without emitting a server action
 *     Y        -> unchanged global shortcut handling in ave_screen_manager.c
 *   FEED Sources chooser:
 *     UP/DOWN  -> clamp within topic/platform entries
 *     A/RIGHT  -> reuse feed_source/feed_platform actions
 *     LEFT/B   -> close back to unchanged standard FEED
 *   SEARCH / SPECIAL mode:
 *     LEFT/X disabled
 *     A/RIGHT  -> enter detail (server-driven "watch")
 *     B        -> restore remembered standard source (or default), show local LOADING, and refresh
 *   ORDERS mode:
 *     browse-only list (no detail)
 *     LEFT/X/A/RIGHT disabled
 *     B        -> send key_action back and exit orders locally (go_to_feed placeholder)
 */
#include "ave_screen_manager.h"
#include "ave_font_provider.h"
#include "ave_json_utils.h"
#include "ave_transport.h"
#include "ave_price_fmt.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ─── Token data ──────────────────────────────────────────────────────────── */
#define MAX_FEED_TOKENS  20

typedef struct {
    char token_id[80];
    char chain[16];
    char symbol[24];
    char contract_tail[12];
    char source_tag[24];
    char price[24];
    char change_24h[16];
    int  change_positive;
    char volume_24h[16];
    char market_cap[16];
    char source[24];
} feed_token_t;

static feed_token_t s_tokens[MAX_FEED_TOKENS];
static int          s_token_count = 0;
static int          s_token_idx   = 0;   /* highlighted / selected */
static int          s_scroll_top  = 0;   /* first visible row */

/* Feed source cycling */
static int s_source_idx = 0;
static const char *SOURCE_NAMES[] = {"TRENDING", "GAINER", "LOSER", "NEW", "MEME", "AI", "DEPIN", "GAMEFI"};
static const char *SOURCE_KEYS[]  = {"trending", "gainer", "loser", "new", "meme", "ai", "depin", "gamefi"};
#define N_SOURCES 8

/* ─── Layout ──────────────────────────────────────────────────────────────── */
#define VISIBLE_ROWS  8
#define ROW_H        24
#define TOP_BAR_H    22
#define BOTTOM_Y     215
#define BOTTOM_BAR_H (240 - BOTTOM_Y)

/* Column x positions (within the row container, i.e. relative to x=0) */
#define COL_CHAIN_X    224
#define COL_SYM_X     4
#define COL_PRICE_X   72
#define COL_CHG_X     154
#define COL_VOL_X     COL_CHAIN_X
#define COL_OVERLAY_TITLE_X   24
#define COL_OVERLAY_TITLE_W   84
#define COL_OVERLAY_DETAIL_X  112
#define COL_OVERLAY_DETAIL_W  200

/* ─── Colors ──────────────────────────────────────────────────────────────── */
#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)
#define COLOR_SEL     lv_color_hex(0x0D2010)   /* selected row tint */
#define COLOR_ALT     lv_color_hex(0x0D0D0D)   /* alternating row */

/* Chain badge colors */
#define COLOR_SOL     lv_color_hex(0x9945FF)
#define COLOR_ETH     lv_color_hex(0x627EEA)
#define COLOR_BSC     lv_color_hex(0xF3BA2F)
#define COLOR_BASE    lv_color_hex(0x0052FF)

/* ─── LVGL objects ────────────────────────────────────────────────────────── */
static lv_obj_t *s_screen     = NULL;
static lv_obj_t *s_top_bar    = NULL;
static lv_obj_t *s_lbl_count  = NULL;
static lv_obj_t *s_lbl_source = NULL;
static lv_obj_t *s_lbl_src_hint = NULL;
static lv_obj_t *s_lbl_nav_hint = NULL;
static lv_obj_t *s_lbl_action_hint = NULL;
static int s_is_orders_mode = 0;
static int s_is_search_mode = 0;
static char s_feed_source_label[24] = "TRENDING";
static char s_active_source_label[24] = "TRENDING";
static char s_last_search_query[24] = "";
static int s_has_special_source_label = 0;
static int s_feed_session_id = 0;
static int s_feed_session_valid = 0;
static int s_cleanup_special_mode = 0;

typedef enum {
    FEED_SURFACE_STANDARD = 0,
    FEED_SURFACE_EXPLORE_PANEL,
    FEED_SURFACE_EXPLORE_SEARCH_GUIDE,
    FEED_SURFACE_EXPLORE_SOURCES,
} feed_surface_t;

typedef enum {
    FEED_MODE_STANDARD = 0,
    FEED_MODE_SEARCH,
    FEED_MODE_ORDERS,
} feed_mode_t;

static feed_mode_t s_feed_mode = FEED_MODE_STANDARD;

typedef enum {
    FEED_EXPLORE_ITEM_SEARCH = 0,
    FEED_EXPLORE_ITEM_ORDERS,
    FEED_EXPLORE_ITEM_SOURCES,
    FEED_EXPLORE_ITEM_COUNT,
} feed_explore_item_id_t;

typedef struct {
    feed_explore_item_id_t id;
    const char *title;
    const char *subtitle;
    feed_surface_t surface;
} feed_explore_item_t;

typedef enum {
    FEED_SOURCE_ENTRY_TOPIC = 0,
    FEED_SOURCE_ENTRY_PLATFORM,
} feed_source_entry_kind_t;

typedef struct {
    const char *label;
    const char *value;
    const char *subtitle;
    feed_source_entry_kind_t kind;
} feed_source_entry_t;

typedef struct {
    feed_surface_t surface;
    const char *nav_hint;
    const char *top_hint;
    const char *action_hint;
    int is_overlay_local;
} feed_surface_model_t;

static feed_surface_t s_feed_surface = FEED_SURFACE_STANDARD;
static int s_explore_idx = 0;
static int s_source_menu_idx = 0;

static void _update_rows(void);
static void _close_feed_overlay(void);

static const feed_explore_item_t EXPLORE_ITEMS[FEED_EXPLORE_ITEM_COUNT] = {
    {FEED_EXPLORE_ITEM_SEARCH,    "Search",    "Say token",                   FEED_SURFACE_EXPLORE_SEARCH_GUIDE},
    {FEED_EXPLORE_ITEM_ORDERS,    "Orders",    "Open current orders list",    FEED_SURFACE_STANDARD},
    {FEED_EXPLORE_ITEM_SOURCES,   "Sources",   "Choose topic or platform",    FEED_SURFACE_STANDARD},
};

static const feed_source_entry_t SOURCE_MENU[] = {
    {"TRENDING",    "trending",        "Topic",    FEED_SOURCE_ENTRY_TOPIC},
    {"GAINER",      "gainer",          "Topic",    FEED_SOURCE_ENTRY_TOPIC},
    {"LOSER",       "loser",           "Topic",    FEED_SOURCE_ENTRY_TOPIC},
    {"NEW",         "new",             "Topic",    FEED_SOURCE_ENTRY_TOPIC},
    {"PUMP HOT",    "pump_in_hot",     "Platform", FEED_SOURCE_ENTRY_PLATFORM},
    {"PUMP NEW",    "pump_in_new",     "Platform", FEED_SOURCE_ENTRY_PLATFORM},
};

static const feed_surface_model_t FEED_SURFACE_MODELS[] = {
    {FEED_SURFACE_STANDARD,             "^ v MOVE", " | < Refresh | X Change", "> Detail | Y Portfolio", 0},
    {FEED_SURFACE_EXPLORE_PANEL,        "^ v MOVE", " | B CLOSE",               "> OPEN | Y PORTFOLIO",   1},
    {FEED_SURFACE_EXPLORE_SEARCH_GUIDE, "Say token", " | B CLOSE",             "B Back | Y Port",        1},
    {FEED_SURFACE_EXPLORE_SOURCES,      "^ v MOVE", " | B CLOSE",               "> OPEN | Y PORTFOLIO",   1},
};


typedef struct {
    lv_obj_t *row;
    lv_obj_t *lbl_chain;
    lv_obj_t *lbl_sym;
    lv_obj_t *lbl_price;
    lv_obj_t *lbl_chg;
    lv_obj_t *lbl_subtitle;
    lv_obj_t *lbl_meta1;
    lv_obj_t *lbl_meta2;
    lv_obj_t *lbl_meta3;
    lv_obj_t *lbl_meta4;
} feed_row_ui_t;

static feed_row_ui_t s_rows[VISIBLE_ROWS];

static void _apply_overlay_row_layout(feed_row_ui_t *ui);
static void _apply_token_row_layout(feed_row_ui_t *ui);

static int _center_text_y(const lv_font_t *font)
{
    int y = (ROW_H - lv_font_get_line_height(font)) / 2;
    return (y < 0) ? 0 : y;
}

static int _source_index_from_label(const char *label)
{
    if (!label || !label[0]) return -1;
    for (int i = 0; i < N_SOURCES; i++) {
        if (strcmp(label, SOURCE_NAMES[i]) == 0) return i;
    }
    return -1;
}

static int _label_is_standard_source(const char *label)
{
    return _source_index_from_label(label) >= 0;
}

static int _is_empty_payload(const char *json)
{
    return (!json || strcmp(json, "{}") == 0);
}

static void _layout_top_bar_labels(void);

static void _apply_source_label(const char *label, int remember_as_feed_source)
{
    const char *effective = label;
    if (!effective || !effective[0]) {
        effective = s_feed_source_label[0] ? s_feed_source_label : SOURCE_NAMES[s_source_idx];
    }

    if (remember_as_feed_source && label && label[0]) {
        int idx = _source_index_from_label(label);
        if (idx >= 0) {
            snprintf(s_feed_source_label, sizeof(s_feed_source_label), "%s", label);
            s_source_idx = idx;
        }
    }

    snprintf(s_active_source_label, sizeof(s_active_source_label), "%s", effective);
    s_has_special_source_label = !_label_is_standard_source(s_active_source_label);

    if (s_lbl_source) {
        char rendered[48];
        snprintf(rendered, sizeof(rendered), "#9945FF SOL# %s", s_active_source_label);
        lv_label_set_recolor(s_lbl_source, true);
        lv_label_set_text(s_lbl_source, rendered);
        _layout_top_bar_labels();
    }
}

static void _layout_top_bar_labels(void)
{
    lv_coord_t count_w;
    lv_coord_t source_w;
    lv_coord_t hint_x;
    lv_coord_t hint_w;

    if (!s_top_bar || !s_lbl_source || !s_lbl_count || !s_lbl_src_hint) return;

    lv_obj_align(s_lbl_count, LV_ALIGN_RIGHT_MID, -8, 0);
    lv_obj_set_pos(s_lbl_source, 8, 4);
    lv_obj_update_layout(s_top_bar);

    count_w = lv_obj_get_width(s_lbl_count);
    source_w = lv_obj_get_width(s_lbl_source);
    hint_x = 8 + source_w + 6;
    hint_w = 320 - 8 - count_w - 8 - hint_x;
    if (hint_w < 0) hint_w = 0;

    lv_obj_set_pos(s_lbl_src_hint, hint_x, 6);
    lv_obj_set_width(s_lbl_src_hint, hint_w);
}

static feed_mode_t _feed_mode_from_mode_string(const char *mode_str)
{
    if (!mode_str) return FEED_MODE_STANDARD;
    if (strcmp(mode_str, "orders") == 0) return FEED_MODE_ORDERS;
    if (strcmp(mode_str, "search") == 0) return FEED_MODE_SEARCH;
    return FEED_MODE_STANDARD;
}

static feed_mode_t _feed_mode_from_source_label(const char *label)
{
    if (!label) return FEED_MODE_STANDARD;
    if (strcmp(label, "ORDERS") == 0) return FEED_MODE_ORDERS;
    if (strcmp(label, "SEARCH") == 0) return FEED_MODE_SEARCH;
    return FEED_MODE_STANDARD;
}

static void _set_feed_mode(feed_mode_t mode)
{
    s_feed_mode = mode;
    s_is_orders_mode = (mode == FEED_MODE_ORDERS);
    s_is_search_mode = (mode == FEED_MODE_SEARCH);
}

static void _load_local_placeholder(void)
{
    memset(s_tokens, 0, sizeof(s_tokens));
    s_token_count = 1;
    s_token_idx = 0;
    s_scroll_top = 0;
    strcpy(s_tokens[0].symbol, "LOADING");
    strcpy(s_tokens[0].price, "--");
    strcpy(s_tokens[0].change_24h, "--");
    s_tokens[0].change_positive = 1;
}

static int _clamp_explore_idx(int idx)
{
    if (idx < 0) return 0;
    if (idx >= FEED_EXPLORE_ITEM_COUNT) return FEED_EXPLORE_ITEM_COUNT - 1;
    return idx;
}

static const feed_explore_item_t *_current_explore_item(void)
{
    return &EXPLORE_ITEMS[_clamp_explore_idx(s_explore_idx)];
}

static int _source_menu_count(void)
{
    return (int)(sizeof(SOURCE_MENU) / sizeof(SOURCE_MENU[0]));
}

static int _clamp_source_menu_idx(int idx)
{
    if (idx < 0) return 0;
    if (idx >= _source_menu_count()) return _source_menu_count() - 1;
    return idx;
}

static const feed_source_entry_t *_current_source_entry(void)
{
    return &SOURCE_MENU[_clamp_source_menu_idx(s_source_menu_idx)];
}

static const feed_surface_model_t *_surface_model_for(feed_surface_t surface)
{
    int idx = (int)surface;

    if (idx < 0 || idx >= (int)(sizeof(FEED_SURFACE_MODELS) / sizeof(FEED_SURFACE_MODELS[0]))) {
        return &FEED_SURFACE_MODELS[0];
    }
    return &FEED_SURFACE_MODELS[idx];
}

static const feed_surface_model_t *_current_surface_model(void)
{
    if (s_is_orders_mode) {
        static const feed_surface_model_t orders_model = {
            FEED_SURFACE_STANDARD,
            "^ v MOVE",
            "",
            "B Back | Y Port",
            0,
        };
        return &orders_model;
    }
    if (s_is_search_mode) {
        static const feed_surface_model_t search_model = {
            FEED_SURFACE_STANDARD,
            "^ v MOVE",
            " | B BACK TO FEED",
            "> Detail | Y Portfolio",
            0,
        };
        return &search_model;
    }
    if (s_feed_surface != FEED_SURFACE_STANDARD) {
        return _surface_model_for(s_feed_surface);
    }
    if (s_has_special_source_label) {
        static const feed_surface_model_t special_model = {
            FEED_SURFACE_STANDARD,
            "^ v MOVE",
            " | B BACK TO FEED",
            "> Detail | Y Portfolio",
            0,
        };
        return &special_model;
    }
    return _surface_model_for(s_feed_surface);
}

static void _update_mode_hint(const feed_surface_model_t *surface_model)
{
    if (!s_lbl_src_hint || !s_lbl_action_hint || !s_lbl_nav_hint) return;

    lv_label_set_text(s_lbl_nav_hint, surface_model->nav_hint);
    lv_label_set_text(s_lbl_src_hint, surface_model->top_hint);
    lv_label_set_text(s_lbl_action_hint, surface_model->action_hint);
    _layout_top_bar_labels();
}

static int _feed_overlay_active(void)
{
    return _current_surface_model()->is_overlay_local;
}

static int _is_standard_feed_home(void)
{
    return !s_is_orders_mode &&
           !s_is_search_mode &&
           !s_has_special_source_label &&
           s_feed_surface == FEED_SURFACE_STANDARD;
}

static void _render_feed_surface(void)
{
    const feed_surface_model_t *surface_model = _current_surface_model();

    /* Clamp the panel cursor through the shared Explore item model. */
    s_explore_idx = _clamp_explore_idx(s_explore_idx);
    s_source_menu_idx = _clamp_source_menu_idx(s_source_menu_idx);

    _update_mode_hint(surface_model);
    _update_rows();
}

static void _sync_remote_browse_mode(feed_mode_t mode, const char *source_label)
{
    _set_feed_mode(mode);
    _apply_source_label(source_label, 0);
    if (s_top_bar) {
        lv_obj_set_style_bg_color(s_top_bar, s_is_orders_mode ? COLOR_ORANGE : COLOR_BAR, 0);
    }
}

static void _activate_current_explore_item(void)
{
    const feed_explore_item_t *item = _current_explore_item();

    if (item->id == FEED_EXPLORE_ITEM_ORDERS) {
        _sync_remote_browse_mode(FEED_MODE_ORDERS, "ORDERS");
        ave_send_json("{\"type\":\"key_action\",\"action\":\"orders\"}");
        s_cleanup_special_mode = 0;
        _close_feed_overlay();
        return;
    }

    if (item->id == FEED_EXPLORE_ITEM_SOURCES) {
        s_feed_surface = FEED_SURFACE_EXPLORE_SOURCES;
        s_source_menu_idx = 0;
        _render_feed_surface();
        return;
    }


    if (item->surface == FEED_SURFACE_STANDARD) {
        return;
    }

    s_feed_surface = item->surface;
    _render_feed_surface();
}

static void _activate_current_source_entry(void)
{
    const feed_source_entry_t *entry = _current_source_entry();
    char cmd[256];

    if (entry->kind == FEED_SOURCE_ENTRY_TOPIC) {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                 entry->value);
    } else {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_platform\",\"platform\":\"%s\"}",
                 entry->value);
    }

    ave_send_json(cmd);
    _close_feed_overlay();
}

static void _request_current_feed_source(void)
{
    int idx = s_source_idx;
    if (idx < 0 || idx >= N_SOURCES) idx = 0;
    char cmd[256];
    snprintf(cmd, sizeof(cmd),
             "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
             SOURCE_KEYS[idx]);
    ave_send_json(cmd);
}

static void _open_explore_panel(void)
{
    s_feed_surface = FEED_SURFACE_EXPLORE_PANEL;
    s_explore_idx = 0;
    _set_feed_mode(FEED_MODE_STANDARD);
    _render_feed_surface();
}

static void _close_feed_overlay(void)
{
    s_feed_surface = FEED_SURFACE_STANDARD;
    int refresh_requested = 0;

    if (s_cleanup_special_mode) {
        s_cleanup_special_mode = 0;
        s_has_special_source_label = 0;
        _set_feed_mode(FEED_MODE_STANDARD);
        _apply_source_label(NULL, 0);
        _load_local_placeholder();
        refresh_requested = 1;
    }

    _render_feed_surface();
    if (refresh_requested) {
        _request_current_feed_source();
    }
}

/* ─── Chain helpers ───────────────────────────────────────────────────────── */
static const char *_chain_short(const char *chain)
{
    if (!chain || !chain[0]) return "???";
    if (strncmp(chain, "solana", 6) == 0) return "SOL";
    if (strncmp(chain, "eth",    3) == 0) return "ETH";
    if (strncmp(chain, "bsc",    3) == 0) return "BSC";
    if (strncmp(chain, "base",   4) == 0) return "BASE";
    /* Generic: first 4 chars uppercased */
    static char buf[8];
    int i = 0;
    while (chain[i] && i < 4) {
        char c = chain[i];
        buf[i++] = (c >= 'a' && c <= 'z') ? c - 32 : c;
    }
    buf[i] = '\0';
    return buf;
}

static lv_color_t _chain_color(const char *chain)
{
    if (!chain) return COLOR_GRAY;
    if (strncmp(chain, "solana", 6) == 0) return COLOR_SOL;
    if (strncmp(chain, "eth",    3) == 0) return COLOR_ETH;
    if (strncmp(chain, "bsc",    3) == 0) return COLOR_BSC;
    if (strncmp(chain, "base",   4) == 0) return COLOR_BASE;
    return COLOR_GRAY;
}


/* ─── JSON parsing ────────────────────────────────────────────────────────── */
static int _get_json_str_field(const char *obj, const char *key, char *out, int n)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(obj, needle);
    if (!p) return 0;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, out, (size_t)n, NULL);
}

static int _get_json_int_field(const char *obj, const char *key, int def)
{
    char val[32] = {0};
    if (_get_json_str_field(obj, key, val, sizeof(val)))
        return atoi(val);
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(obj, needle);
    if (!p) return def;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p >= '0' && *p <= '9') return atoi(p);
    if (*p == '-') return atoi(p);
    if (*p == 't') return 1;
    if (*p == 'f') return 0;
    return def;
}

static int _get_json_tristate_field(const char *obj, const char *key, int def)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(obj, needle);
    if (!p) return def;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p >= '0' && *p <= '9') return atoi(p);
    if (*p == '-') return atoi(p);
    if (*p == 't') return 1;
    if (*p == 'f') return 0;
    if (*p == 'n') return -1;
    return def;
}

static void _parse_tokens_from_json(const char *json)
{
    s_token_count = 0;

    const char *arr = strstr(json, "\"tokens\"");
    if (!arr) {
        /* No tokens array — show placeholder */
        s_token_count = 1;
        strcpy(s_tokens[0].symbol,    "---");
        strcpy(s_tokens[0].price,     "$0");
        strcpy(s_tokens[0].change_24h,"N/A");
        strcpy(s_tokens[0].source,    "loading");
        return;
    }
    arr = strchr(arr, '[');
    if (!arr) return;
    arr++;

    const char *p = arr;
    while (*p && s_token_count < MAX_FEED_TOKENS) {
        p = strchr(p, '{');
        if (!p) break;
        int depth = 1;
        const char *obj_start = p++;
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
            if (*p == '{') depth++;
            if (*p == '}') depth--;
            p++;
        }
        size_t obj_len = (size_t)(p - obj_start);
        char  *obj = (char *)malloc(obj_len + 1);
        if (!obj) break;
        memcpy(obj, obj_start, obj_len);
        obj[obj_len] = '\0';

        feed_token_t *t = &s_tokens[s_token_count];
        memset(t, 0, sizeof(*t));
        _get_json_str_field(obj, "token_id",   t->token_id,   sizeof(t->token_id));
        _get_json_str_field(obj, "chain",      t->chain,      sizeof(t->chain));
        _get_json_str_field(obj, "symbol",     t->symbol,     sizeof(t->symbol));
        _get_json_str_field(obj, "contract_tail", t->contract_tail, sizeof(t->contract_tail));
        _get_json_str_field(obj, "source_tag", t->source_tag, sizeof(t->source_tag));
        _get_json_str_field(obj, "price",      t->price,      sizeof(t->price));
        _get_json_str_field(obj, "change_24h", t->change_24h, sizeof(t->change_24h));
        _get_json_str_field(obj, "volume_24h", t->volume_24h, sizeof(t->volume_24h));
        _get_json_str_field(obj, "market_cap", t->market_cap, sizeof(t->market_cap));
        _get_json_str_field(obj, "source",     t->source,     sizeof(t->source));
        t->change_positive = _get_json_tristate_field(obj, "change_positive", -1);
        if (!t->symbol[0]) strcpy(t->symbol, "???");
        free(obj);
        s_token_count++;
    }
}

static void _feed_symbol_text(const feed_token_t *t, char *out, size_t out_n)
{
    if (!out || out_n == 0) return;
    if (!t) {
        out[0] = '\0';
        return;
    }
    snprintf(out, out_n, "%s", t->symbol[0] ? t->symbol : "???");
}

/* ─── Update visible rows ─────────────────────────────────────────────────── */
static void _set_row_text(feed_row_ui_t *ui,
                          lv_color_t row_bg,
                          lv_color_t chain_color,
                          lv_color_t chg_color,
                          const char *chain,
                          const char *sym,
                          const char *price,
                          const char *chg)
{
    lv_obj_set_style_bg_color(ui->row, row_bg, 0);
    lv_label_set_text(ui->lbl_chain, chain ? chain : "");
    lv_obj_set_style_text_color(ui->lbl_chain, chain_color, 0);
    lv_label_set_text(ui->lbl_sym, sym ? sym : "");
    lv_label_set_text(ui->lbl_price, price ? price : "");
    lv_label_set_text(ui->lbl_chg, chg ? chg : "");
    lv_obj_set_style_text_color(ui->lbl_chg, chg_color, 0);
    lv_label_set_text(ui->lbl_subtitle, "");
    lv_label_set_text(ui->lbl_meta1, "");
    lv_label_set_text(ui->lbl_meta2, "");
    lv_label_set_text(ui->lbl_meta3, "");
    lv_label_set_text(ui->lbl_meta4, "");
}

static void _clear_row(feed_row_ui_t *ui)
{
    _set_row_text(ui, COLOR_BG, COLOR_GRAY, COLOR_GRAY, "", "", "", "");
}

static void _apply_overlay_row_layout(feed_row_ui_t *ui)
{
    if (!ui) return;
    lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
    lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_font(ui->lbl_chg, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_subtitle, &lv_font_montserrat_12, 0);
    lv_obj_set_pos(ui->lbl_sym, COL_OVERLAY_TITLE_X, _center_text_y(ave_font_cjk_16()));
    lv_obj_set_width(ui->lbl_sym, COL_OVERLAY_TITLE_W);
    lv_obj_set_pos(ui->lbl_price, COL_OVERLAY_DETAIL_X, _center_text_y(&lv_font_montserrat_14));
    lv_obj_set_width(ui->lbl_price, COL_OVERLAY_DETAIL_W);
    lv_obj_set_style_text_align(ui->lbl_price, LV_TEXT_ALIGN_LEFT, 0);
}

static void _apply_token_row_layout(feed_row_ui_t *ui)
{
    if (!ui) return;
    lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
    lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_font(ui->lbl_chg, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_subtitle, &lv_font_montserrat_12, 0);
    lv_obj_set_pos(ui->lbl_sym, COL_SYM_X, _center_text_y(ave_font_cjk_16()));
    lv_obj_set_width(ui->lbl_sym, 62);
    lv_obj_set_pos(ui->lbl_price, COL_PRICE_X, _center_text_y(&lv_font_montserrat_14));
    lv_obj_set_width(ui->lbl_price, 76);
    lv_obj_set_style_text_align(ui->lbl_price, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(ui->lbl_chg, COL_CHG_X, _center_text_y(&lv_font_montserrat_12));
    lv_obj_set_width(ui->lbl_chg, 64);
    lv_obj_set_style_text_align(ui->lbl_chg, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_set_pos(ui->lbl_chain, COL_VOL_X, _center_text_y(&lv_font_montserrat_12));
    lv_obj_set_width(ui->lbl_chain, 88);
    lv_obj_set_style_text_align(ui->lbl_chain, LV_TEXT_ALIGN_RIGHT, 0);
}


static void _update_overlay_rows(void)
{
    int total = 0;
    int cursor = 0;

    if (s_feed_surface == FEED_SURFACE_EXPLORE_PANEL) {
        total = FEED_EXPLORE_ITEM_COUNT;
        cursor = _clamp_explore_idx(s_explore_idx);
    } else if (s_feed_surface == FEED_SURFACE_EXPLORE_SOURCES) {
        total = _source_menu_count();
        cursor = _clamp_source_menu_idx(s_source_menu_idx);
    }

    if (s_lbl_count) {
        if (total > 0) {
            char buf[32];
            snprintf(buf, sizeof(buf), "%d/%d", cursor + 1, total);
            lv_label_set_text(s_lbl_count, buf);
        } else {
            lv_label_set_text(s_lbl_count, "");
        }
    }

    for (int r = 0; r < VISIBLE_ROWS; r++) {
        feed_row_ui_t *ui = &s_rows[r];
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        _apply_overlay_row_layout(ui);
        if (s_feed_surface == FEED_SURFACE_EXPLORE_PANEL) {
            if (r >= FEED_EXPLORE_ITEM_COUNT) {
                _clear_row(ui);
                continue;
            }

            const feed_explore_item_t *item = &EXPLORE_ITEMS[r];
            int selected = (r == cursor);
            _set_row_text(ui,
                          selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                          selected ? COLOR_WHITE : COLOR_GRAY,
                          COLOR_GRAY,
                          selected ? ">" : "",
                          item->title,
                          item->subtitle,
                          "");
            continue;
        }

        if (s_feed_surface == FEED_SURFACE_EXPLORE_SEARCH_GUIDE) {
            char last_search_line[40];
            static const char *guide_sym[VISIBLE_ROWS] = {
                "Search",
                "Hold FN",
                "Example",
                "Last search",
                "Voice",
                "",
                "",
                "",
            };
            snprintf(last_search_line, sizeof(last_search_line), "%s",
                     s_last_search_query[0] ? s_last_search_query : "No recent search");
            const char *guide_price[VISIBLE_ROWS] = {
                "Guided entry",
                "Say token",
                "BONK / PEPE / DOGE",
                last_search_line,
                "Y stays global",
                "",
                "",
                "",
            };
            _set_row_text(ui,
                          (r == 0) ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                          (r == 0) ? COLOR_WHITE : COLOR_GRAY,
                          COLOR_GRAY,
                          "",
                          guide_sym[r],
                          guide_price[r],
                          "");
            continue;
        }

        if (s_feed_surface == FEED_SURFACE_EXPLORE_SOURCES) {
            if (r >= _source_menu_count()) {
                _clear_row(ui);
                continue;
            }

            const feed_source_entry_t *entry = &SOURCE_MENU[r];
            int selected = (r == cursor);
            _set_row_text(ui,
                          selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                          selected ? COLOR_WHITE : COLOR_GRAY,
                          COLOR_GRAY,
                          selected ? ">" : "",
                          entry->label,
                          entry->subtitle,
                          "");
            continue;
        }

        _clear_row(ui);
    }
}

static void _refresh_count_hint(void)
{
    if (!s_lbl_count) return;
    if (s_token_count > 0) {
        char buf[24];
        snprintf(buf, sizeof(buf), "%d/%d", s_token_idx + 1, s_token_count);
        lv_label_set_text(s_lbl_count, buf);
    } else {
        lv_label_set_text(s_lbl_count, "");
    }
    _layout_top_bar_labels();
}

static int _visible_row_count(void)
{
    return VISIBLE_ROWS;
}

static void _update_token_rows(void)
{
    for (int r = 0; r < VISIBLE_ROWS; r++) {
        int tok_idx = s_scroll_top + r;
        feed_row_ui_t *ui = &s_rows[r];
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        _apply_token_row_layout(ui);
        if (tok_idx >= s_token_count) {
            lv_obj_set_style_bg_color(ui->row, COLOR_BG, 0);
            lv_label_set_text(ui->lbl_chain, "");
            lv_label_set_text(ui->lbl_sym,   "");
            lv_label_set_text(ui->lbl_price, "");
            lv_label_set_text(ui->lbl_chg,   "");
            continue;
        }

        const feed_token_t *t = &s_tokens[tok_idx];
        char sym_buf[48];
        char price_buf[32];
        lv_color_t row_bg;
        if (tok_idx == s_token_idx)
            row_bg = COLOR_SEL;
        else
            row_bg = (r & 1) ? COLOR_ALT : COLOR_BG;
        lv_obj_set_style_bg_color(ui->row, row_bg, 0);

        lv_label_set_text(ui->lbl_chain, t->volume_24h[0] ? t->volume_24h : "Vol --");
        lv_obj_set_style_text_color(ui->lbl_chain, COLOR_GRAY, 0);

        _feed_symbol_text(t, sym_buf, sizeof(sym_buf));
        lv_label_set_text(ui->lbl_sym, sym_buf);
        lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
        ave_fmt_price_text(price_buf, sizeof(price_buf), t->price[0] ? t->price : "$0");
        lv_label_set_text(ui->lbl_price, price_buf);
        lv_label_set_text(ui->lbl_subtitle, "");

        lv_label_set_text(ui->lbl_chg, t->change_24h[0] ? t->change_24h : "N/A");
        if (!t->change_24h[0] ||
            strcmp(t->change_24h, "N/A") == 0 ||
            strcmp(t->change_24h, "--") == 0 ||
            t->change_positive < 0) {
            lv_obj_set_style_text_color(ui->lbl_chg, COLOR_GRAY, 0);
        } else {
            lv_obj_set_style_text_color(ui->lbl_chg,
                t->change_positive ? COLOR_GREEN : COLOR_RED, 0);
        }
    }

    _refresh_count_hint();
}

static void _update_rows(void)
{
    if (_feed_overlay_active()) {
        _update_overlay_rows();
        return;
    }
    _update_token_rows();
}

/* ─── Build screen ────────────────────────────────────────────────────────── */
static void _build_screen(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_size(s_screen, 320, 240);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_clear_flag(s_screen, LV_OBJ_FLAG_SCROLLABLE);

    /* ── Top bar ─────────────────────────────────────────────────────────── */
    s_top_bar = lv_obj_create(s_screen);
    lv_obj_set_size(s_top_bar, 320, TOP_BAR_H);
    lv_obj_set_pos(s_top_bar, 0, 0);
    lv_obj_set_style_bg_color(s_top_bar, COLOR_BAR, 0);
    lv_obj_set_style_bg_opa(s_top_bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_top_bar, 0, 0);
    lv_obj_set_style_pad_all(s_top_bar, 0, 0);
    lv_obj_clear_flag(s_top_bar, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_source = lv_label_create(s_top_bar);
    lv_obj_set_pos(s_lbl_source, 8, 4);
    lv_label_set_recolor(s_lbl_source, true);
    lv_label_set_text(s_lbl_source, "#9945FF SOL# TRENDING");
    lv_obj_set_style_text_color(s_lbl_source, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_source, &lv_font_montserrat_12, 0);

    s_lbl_count = lv_label_create(s_top_bar);
    lv_obj_align(s_lbl_count, LV_ALIGN_RIGHT_MID, -8, 0);
    lv_obj_set_style_text_color(s_lbl_count, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_count, &lv_font_montserrat_12, 0);
    lv_label_set_text(s_lbl_count, "");

    s_lbl_src_hint = lv_label_create(s_top_bar);
    lv_obj_set_pos(s_lbl_src_hint, 76, 6);
    lv_obj_set_width(s_lbl_src_hint, 164);
    lv_label_set_long_mode(s_lbl_src_hint, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_src_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_src_hint, &lv_font_montserrat_12, 0);
    lv_label_set_text(s_lbl_src_hint, " | < Refresh | X Change");

    /* ── List rows ───────────────────────────────────────────────────────── */
    for (int r = 0; r < VISIBLE_ROWS; r++) {
        feed_row_ui_t *ui = &s_rows[r];
        int row_y = TOP_BAR_H + r * ROW_H;

        ui->row = lv_obj_create(s_screen);
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, row_y);
        lv_obj_set_style_bg_color(ui->row, COLOR_BG, 0);
        lv_obj_set_style_bg_opa(ui->row, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(ui->row, 0, 0);
        lv_obj_set_style_pad_all(ui->row, 0, 0);
        lv_obj_clear_flag(ui->row, LV_OBJ_FLAG_SCROLLABLE);

        /* Volume column (row-level chain is omitted on the Solana-only build). */
        ui->lbl_chain = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
        lv_obj_set_pos(ui->lbl_chain, COL_VOL_X, _center_text_y(&lv_font_montserrat_12));
        lv_obj_set_style_text_color(ui->lbl_chain, COLOR_GRAY, 0);
        lv_label_set_long_mode(ui->lbl_chain, LV_LABEL_LONG_CLIP);
        lv_obj_set_width(ui->lbl_chain, 88);
        lv_obj_set_style_text_align(ui->lbl_chain, LV_TEXT_ALIGN_RIGHT, 0);

        /* Symbol */
        ui->lbl_sym = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
        lv_obj_set_pos(ui->lbl_sym, COL_SYM_X, _center_text_y(ave_font_cjk_16()));
        lv_obj_set_style_text_color(ui->lbl_sym, COLOR_WHITE, 0);
        lv_label_set_long_mode(ui->lbl_sym, LV_LABEL_LONG_SCROLL_CIRCULAR);
        lv_obj_set_width(ui->lbl_sym, 62);

        /* Price */
        ui->lbl_price = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_14, 0);
        lv_obj_set_pos(ui->lbl_price, COL_PRICE_X, _center_text_y(&lv_font_montserrat_14));
        lv_obj_set_style_text_color(ui->lbl_price, COLOR_GRAY, 0);
        lv_label_set_long_mode(ui->lbl_price, LV_LABEL_LONG_CLIP);
        lv_obj_set_width(ui->lbl_price, 76);
        lv_obj_set_style_text_align(ui->lbl_price, LV_TEXT_ALIGN_RIGHT, 0);

        /* Change % */
        ui->lbl_chg = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_chg, &lv_font_montserrat_12, 0);
        lv_obj_set_pos(ui->lbl_chg, COL_CHG_X, _center_text_y(&lv_font_montserrat_12));
        lv_obj_set_style_text_color(ui->lbl_chg, COLOR_GRAY, 0);
        lv_label_set_long_mode(ui->lbl_chg, LV_LABEL_LONG_SCROLL_CIRCULAR);
        lv_obj_set_width(ui->lbl_chg, 64);
        lv_obj_set_style_text_align(ui->lbl_chg, LV_TEXT_ALIGN_RIGHT, 0);

        ui->lbl_subtitle = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_subtitle, &lv_font_montserrat_12, 0);
        lv_label_set_long_mode(ui->lbl_subtitle, LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_color(ui->lbl_subtitle, COLOR_GRAY, 0);
        lv_label_set_text(ui->lbl_subtitle, "");

        ui->lbl_meta1 = lv_label_create(ui->row);
        ui->lbl_meta2 = lv_label_create(ui->row);
        ui->lbl_meta3 = lv_label_create(ui->row);
        ui->lbl_meta4 = lv_label_create(ui->row);
        lv_label_set_long_mode(ui->lbl_meta1, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta2, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta3, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta4, LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_color(ui->lbl_meta1, COLOR_GRAY, 0);
        lv_obj_set_style_text_color(ui->lbl_meta2, COLOR_GRAY, 0);
        lv_obj_set_style_text_color(ui->lbl_meta3, COLOR_GRAY, 0);
        lv_obj_set_style_text_color(ui->lbl_meta4, COLOR_GRAY, 0);
        lv_label_set_text(ui->lbl_meta1, "");
        lv_label_set_text(ui->lbl_meta2, "");
        lv_label_set_text(ui->lbl_meta3, "");
        lv_label_set_text(ui->lbl_meta4, "");
    }

    /* ── Divider ─────────────────────────────────────────────────────────── */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_set_pos(div, 0, BOTTOM_Y - 1);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_bg_opa(div, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* ── Bottom bar ──────────────────────────────────────────────────────── */
    lv_obj_t *bot = lv_obj_create(s_screen);
    lv_obj_set_size(bot, 320, 240 - BOTTOM_Y);
    lv_obj_set_pos(bot, 0, BOTTOM_Y);
    lv_obj_set_style_bg_color(bot, COLOR_BAR, 0);
    lv_obj_set_style_bg_opa(bot, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bot, 0, 0);
    lv_obj_set_style_pad_all(bot, 0, 0);
    lv_obj_clear_flag(bot, LV_OBJ_FLAG_SCROLLABLE);

    s_lbl_nav_hint = lv_label_create(bot);
    lv_label_set_long_mode(s_lbl_nav_hint, LV_LABEL_LONG_CLIP);
    lv_obj_set_width(s_lbl_nav_hint, 88);
    lv_obj_align(s_lbl_nav_hint, LV_ALIGN_LEFT_MID, 8, 0);
    lv_label_set_text(s_lbl_nav_hint, "^ v MOVE");
    lv_obj_set_style_text_color(s_lbl_nav_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_nav_hint, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_nav_hint, LV_TEXT_ALIGN_LEFT, 0);

    s_lbl_action_hint = lv_label_create(bot);
    lv_label_set_long_mode(s_lbl_action_hint, LV_LABEL_LONG_CLIP);
    lv_obj_set_width(s_lbl_action_hint, 200);
    lv_obj_align(s_lbl_action_hint, LV_ALIGN_RIGHT_MID, -8, 0);
    lv_label_set_text(s_lbl_action_hint, "> Detail | Y Portfolio");
    lv_obj_set_style_text_color(s_lbl_action_hint, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_action_hint, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_action_hint, LV_TEXT_ALIGN_RIGHT, 0);
}

/* ─── Public screen API ───────────────────────────────────────────────────── */

void screen_feed_show(const char *json_data)
{
    char prev_selected_token_id[80] = {0};
    int prev_token_idx = s_token_idx;
    int prev_scroll_top = s_scroll_top;

    if (!s_screen) _build_screen();
    lv_screen_load(s_screen);

    s_cleanup_special_mode = 0;
    if (_is_empty_payload(json_data)) {
        _set_feed_mode(FEED_MODE_STANDARD);
        s_is_orders_mode = 0;
        s_is_search_mode = 0;
        s_feed_surface = FEED_SURFACE_STANDARD;
        _apply_source_label(NULL, 0);
        if (s_top_bar) lv_obj_set_style_bg_color(s_top_bar, COLOR_BAR, 0);
        _render_feed_surface();
        _load_local_placeholder();
        _render_feed_surface();
        return;
    }

    int has_tokens = (json_data && strstr(json_data, "\"tokens\"") != NULL);
    int is_live_push = _get_json_int_field(json_data, "live", 0);
    int incoming_feed_session = _get_json_int_field(json_data, "feed_session", -1);
    int has_feed_session = (incoming_feed_session >= 0);
    char source_label[24] = {0};
    char search_query[24] = {0};
    char mode[16] = {0};
    char prev_label[24];
    int has_source_label = _get_json_str_field(json_data, "source_label", source_label, sizeof(source_label));
    int has_search_query = _get_json_str_field(json_data, "search_query", search_query, sizeof(search_query));
    int has_mode = _get_json_str_field(json_data, "mode", mode, sizeof(mode));
    feed_mode_t incoming_mode = FEED_MODE_STANDARD;
    int prev_orders_mode = s_is_orders_mode;

    if (is_live_push) {
        /* Live pushes are only valid for the current feed session. */
        if (s_feed_session_valid) {
            if (!has_feed_session) return;
            if (incoming_feed_session != s_feed_session_id) return;
        }
    } else if (has_tokens && has_feed_session) {
        s_feed_session_id = incoming_feed_session;
        s_feed_session_valid = 1;
    } else if (has_tokens) {
        s_feed_session_id = 0;
        s_feed_session_valid = 0;
    }

    snprintf(prev_label, sizeof(prev_label), "%s", s_active_source_label);

    if (has_search_query) {
        snprintf(s_last_search_query, sizeof(s_last_search_query), "%s", search_query);
    }

    if (has_mode) {
        incoming_mode = _feed_mode_from_mode_string(mode);
    } else if (has_source_label) {
        incoming_mode = _feed_mode_from_source_label(source_label);
    } else if (has_tokens) {
        incoming_mode = FEED_MODE_STANDARD;
    }
    _set_feed_mode(incoming_mode);

    if (s_lbl_source) {
        if (has_source_label && source_label[0]) {
            _apply_source_label(source_label, s_feed_mode == FEED_MODE_STANDARD);
        } else if (s_feed_mode == FEED_MODE_ORDERS) {
            _apply_source_label("ORDERS", 0);
        } else if (s_feed_mode == FEED_MODE_SEARCH) {
            _apply_source_label("SEARCH", 0);
        } else if (!s_is_orders_mode && has_tokens) {
            _apply_source_label(NULL, 0);
        }
    }

    if ((has_tokens && !is_live_push) ||
        s_is_orders_mode ||
        s_is_search_mode ||
        s_has_special_source_label) {
        s_feed_surface = FEED_SURFACE_STANDARD;
    }

    if (s_top_bar) {
        lv_obj_set_style_bg_color(s_top_bar, s_is_orders_mode ? COLOR_ORANGE : COLOR_BAR, 0);
    }
    _render_feed_surface();

    if (!has_tokens &&
        ((has_mode && prev_orders_mode != s_is_orders_mode) ||
         (has_source_label && strcmp(prev_label, s_active_source_label) != 0))) {
        _load_local_placeholder();
    }

    if (has_tokens || s_token_count == 0) {
        int requested_cursor = _get_json_int_field(json_data, "cursor", -1);
        int max_scroll_top = 0;

        if (is_live_push &&
            requested_cursor < 0 &&
            prev_token_idx >= 0 &&
            prev_token_idx < s_token_count &&
            s_tokens[prev_token_idx].token_id[0]) {
            snprintf(prev_selected_token_id,
                     sizeof(prev_selected_token_id),
                     "%s",
                     s_tokens[prev_token_idx].token_id);
        }

        _parse_tokens_from_json(json_data);
        if (has_tokens) {
            /* Non-live list payloads reset to top unless a restore cursor is supplied.
             * Live refreshes preserve the user's current selection/viewport when possible. */
            if (requested_cursor >= 0 && requested_cursor < s_token_count) {
                s_token_idx = requested_cursor;
            } else if (is_live_push && prev_selected_token_id[0]) {
                int matched_idx = -1;
                int i;
                for (i = 0; i < s_token_count; i++) {
                    if (strcmp(s_tokens[i].token_id, prev_selected_token_id) == 0) {
                        matched_idx = i;
                        break;
                    }
                }
                if (matched_idx >= 0) {
                    s_token_idx = matched_idx;
                } else if (s_token_count > 0) {
                    if (prev_token_idx < 0) prev_token_idx = 0;
                    if (prev_token_idx >= s_token_count) prev_token_idx = s_token_count - 1;
                    s_token_idx = prev_token_idx;
                } else {
                    s_token_idx = 0;
                }
            } else {
                s_token_idx = 0;
            }

            int visible_rows = _visible_row_count();
            max_scroll_top = (s_token_count > visible_rows) ? (s_token_count - visible_rows) : 0;
            if (is_live_push && requested_cursor < 0) {
                s_scroll_top = prev_scroll_top;
                if (s_scroll_top < 0) s_scroll_top = 0;
                if (s_scroll_top > max_scroll_top) s_scroll_top = max_scroll_top;
                if (s_token_idx < s_scroll_top) {
                    s_scroll_top = s_token_idx;
                } else if (s_token_idx >= s_scroll_top + visible_rows) {
                    s_scroll_top = s_token_idx - visible_rows + 1;
                }
            } else {
                s_scroll_top = (s_token_idx >= visible_rows) ? (s_token_idx - visible_rows + 1) : 0;
            }
        }
    }

    _update_rows();
}

void screen_feed_reveal(void)
{
    if (!s_screen) {
        screen_feed_show("{}");
        return;
    }
    lv_screen_load(s_screen);
    _render_feed_surface();
}

static void _move_selection(int delta)
{
    if (s_token_count < 1) return;
    s_token_idx = (s_token_idx + delta + s_token_count) % s_token_count;
    /* Scroll window to keep selection visible */
    int visible_rows = _visible_row_count();
    if (s_token_idx < s_scroll_top)
        s_scroll_top = s_token_idx;
    else if (s_token_idx >= s_scroll_top + visible_rows)
        s_scroll_top = s_token_idx - visible_rows + 1;
    int max_scroll = (s_token_count > visible_rows) ? (s_token_count - visible_rows) : 0;
    if (s_scroll_top > max_scroll) s_scroll_top = max_scroll;
    _update_rows();
}

static void _enter_selected_detail(void)
{
    char cmd[384];
    char cursor_buf[16];
    ave_sm_json_field_t fields[] = {
        {"token_id", ""},
        {"chain", ""},
        {"cursor", cursor_buf},
        {"origin", "feed"},
    };

    if (s_token_count < 1) return;
    const feed_token_t *t = &s_tokens[s_token_idx];
    if (!t->token_id[0] || !t->chain[0]) return;

    snprintf(cursor_buf, sizeof(cursor_buf), "%d", s_token_idx);
    fields[0].value = t->token_id;
    fields[1].value = t->chain;
    if (!ave_sm_build_key_action_json("watch", fields, 4, cmd, sizeof(cmd))) return;
    ave_send_json(cmd);
    printf("[FEED] WATCH -> %s (%s)\n", t->symbol, t->chain);
}

void screen_feed_key(int key)
{
    if (_feed_overlay_active()) {
        if (key == AVE_KEY_B || key == AVE_KEY_LEFT) {
            _close_feed_overlay();
            return;
        }
        if (s_feed_surface == FEED_SURFACE_EXPLORE_PANEL) {
            if (key == AVE_KEY_UP) {
                if (s_explore_idx > 0) s_explore_idx--;
                _render_feed_surface();
                return;
            }
            if (key == AVE_KEY_DOWN) {
                if (s_explore_idx < FEED_EXPLORE_ITEM_COUNT - 1) s_explore_idx++;
                _render_feed_surface();
                return;
            }
            if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
                _activate_current_explore_item();
                return;
            }
        }
        if (s_feed_surface == FEED_SURFACE_EXPLORE_SOURCES) {
            if (key == AVE_KEY_UP) {
                if (s_source_menu_idx > 0) s_source_menu_idx--;
                _render_feed_surface();
                return;
            }
            if (key == AVE_KEY_DOWN) {
                if (s_source_menu_idx < _source_menu_count() - 1) s_source_menu_idx++;
                _render_feed_surface();
                return;
            }
            if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
                _activate_current_source_entry();
                return;
            }
        }
        return;
    }

    if (key == AVE_KEY_B && _is_standard_feed_home()) {
        ave_sm_open_explorer();
        return;
    }

    if (key == AVE_KEY_UP) {
        _move_selection(-1);

    } else if (key == AVE_KEY_DOWN) {
        _move_selection(+1);

    } else if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
        if (s_is_orders_mode) {
            /* ORDERS is browse-only: do not enter detail / emit watch actions. */
            return;
        }
        _enter_selected_detail();

    } else if (key == AVE_KEY_LEFT) {
        if (s_is_orders_mode) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"订单模式不支持刷新，请按 B 返回\"}");
            return;
        }
        if (s_is_search_mode) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"SEARCH 模式不支持刷新/切换来源，请按 B 回到 FEED\"}");
            return;
        }
        if (s_has_special_source_label) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"当前列表不支持切换来源，请按 B 回到 FEED\"}");
            return;
        }
        /* Refresh current source (no index change) */
        char cmd[256];
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                 SOURCE_KEYS[s_source_idx]);
        ave_send_json(cmd);

    } else if (key == AVE_KEY_X) {
        if (s_is_orders_mode) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"订单模式暂不支持 X 操作，请按 B 返回\"}");
            return;
        }
        if (s_is_search_mode) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"SEARCH 模式不支持刷新/切换来源，请按 B 回到 FEED\"}");
            return;
        }
        if (s_has_special_source_label) {
            screen_notify_show("{\"level\":\"info\",\"title\":\"提示\",\"body\":\"当前列表不支持切换来源，请按 B 回到 FEED\"}");
            return;
        }
        s_source_idx = (s_source_idx + 1) % N_SOURCES;
        _apply_source_label(SOURCE_NAMES[s_source_idx], 1);
        char cmd[256];
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                 SOURCE_KEYS[s_source_idx]);
        ave_send_json(cmd);
    } else if (key == AVE_KEY_B) {
        if (s_is_orders_mode) {
            ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
            ave_sm_go_to_feed();
            return;
        }
        if (s_is_search_mode || s_has_special_source_label) {
            int idx = s_source_idx;
            if (idx < 0 || idx >= N_SOURCES) idx = 0;

            s_is_search_mode = 0;
            _apply_source_label(SOURCE_NAMES[idx], 0);
            _load_local_placeholder();
            _render_feed_surface();

            char cmd[256];
            snprintf(cmd, sizeof(cmd),
                     "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                     SOURCE_KEYS[idx]);
            ave_send_json(cmd);
            return;
        }
        screen_notify_show("{\"level\":\"warning\",\"title\":\"提示\",\"body\":\"已在首页\"}");
    }
}

bool screen_feed_should_ignore_live_push(void)
{
    return s_is_orders_mode ||
           s_is_search_mode ||
           s_has_special_source_label ||
           _feed_overlay_active();
}

const char *screen_feed_get_last_search_query(void)
{
    return s_last_search_query;
}

int screen_feed_get_selected_context_json(char *out, size_t out_n)
{
    char addr_esc[256];
    char chain_esc[64];
    char symbol_esc[64];

    if (!out || out_n == 0) return 0;
    /* ORDERS is browse-only across all input surfaces: never emit a trusted
     * deictic selection context for listen/text commands in this mode. */
    if (s_is_orders_mode) return 0;
    if (_feed_overlay_active()) return 0;
    if (s_token_count < 1 || s_token_idx < 0 || s_token_idx >= s_token_count) return 0;

    const feed_token_t *t = &s_tokens[s_token_idx];
    if (!t->token_id[0]) return 0;
    if (!t->chain[0]) return 0;
    if (!ave_sm_json_escape_string(t->token_id, addr_esc, sizeof(addr_esc))) return 0;
    if (!ave_sm_json_escape_string(t->chain, chain_esc, sizeof(chain_esc))) return 0;
    if (!ave_sm_json_escape_string(t->symbol, symbol_esc, sizeof(symbol_esc))) return 0;

    int n = snprintf(
        out, out_n,
        "{\"screen\":\"feed\",\"cursor\":%d,\"token\":{\"addr\":\"%s\",\"chain\":\"%s\",\"symbol\":\"%s\"}}",
        s_token_idx,
        addr_esc,
        chain_esc,
        symbol_esc
    );
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
