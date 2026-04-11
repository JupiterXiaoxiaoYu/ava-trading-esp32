/**
 * @file screen_explorer.c
 * @brief EXPLORER screen - button-driven entry point for search, sources, orders, signals, and watchlist.
 */
#include "ave_screen_manager.h"
#include "ave_font_provider.h"
#include "ave_transport.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdio.h>
#include <string.h>

#define TOP_BAR_H     22
#define BOTTOM_Y      215
#define ROW_H         24
#define VISIBLE_ROWS  8

#define COL_CHAIN_X    4
#define COL_OVERLAY_TITLE_X   16
#define COL_OVERLAY_TITLE_W   106
#define COL_OVERLAY_DETAIL_X  128
#define COL_OVERLAY_DETAIL_W  186

#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)
#define COLOR_SEL     lv_color_hex(0x0D2010)
#define COLOR_ALT     lv_color_hex(0x0D0D0D)

typedef enum {
    EXPLORER_SURFACE_MENU = 0,
    EXPLORER_SURFACE_SEARCH_GUIDE,
    EXPLORER_SURFACE_SOURCES,
    EXPLORER_SURFACE_TRADE_MODE,
} explorer_surface_t;

typedef enum {
    EXPLORER_ITEM_SEARCH = 0,
    EXPLORER_ITEM_ORDERS,
    EXPLORER_ITEM_TRADE_MODE,
    EXPLORER_ITEM_SOURCES,
    EXPLORER_ITEM_SIGNALS,
    EXPLORER_ITEM_WATCHLIST,
    EXPLORER_ITEM_COUNT,
} explorer_item_id_t;

typedef enum {
    EXPLORER_SOURCE_TOPIC = 0,
    EXPLORER_SOURCE_PLATFORM,
} explorer_source_kind_t;

typedef struct {
    explorer_item_id_t id;
    const char *title;
    const char *subtitle;
} explorer_item_t;

typedef struct {
    const char *label;
    const char *value;
    const char *subtitle;
    explorer_source_kind_t kind;
} explorer_source_entry_t;

typedef struct {
    const char *nav_hint;
    const char *top_hint;
    const char *action_hint;
} explorer_surface_model_t;

typedef struct {
    lv_obj_t *row;
    lv_obj_t *lbl_chain;
    lv_obj_t *lbl_sym;
    lv_obj_t *lbl_price;
} explorer_row_ui_t;

static const explorer_item_t MENU_ITEMS[EXPLORER_ITEM_COUNT] = {
    {EXPLORER_ITEM_SEARCH,    "Search",    "Say token"},
    {EXPLORER_ITEM_ORDERS,    "Orders",    "Open current orders list"},
    {EXPLORER_ITEM_TRADE_MODE,"Trading Mode", "Current: Real"},
    {EXPLORER_ITEM_SOURCES,   "Sources",   "Choose topic or platform"},
    {EXPLORER_ITEM_SIGNALS,   "Signals",   "Browse public signal flow"},
    {EXPLORER_ITEM_WATCHLIST, "Watchlist", "Open saved tokens"},
};

static const explorer_source_entry_t SOURCE_MENU[] = {
    {"TRENDING",    "trending",        "Topic",    EXPLORER_SOURCE_TOPIC},
    {"GAINER",      "gainer",          "Topic",    EXPLORER_SOURCE_TOPIC},
    {"LOSER",       "loser",           "Topic",    EXPLORER_SOURCE_TOPIC},
    {"NEW",         "new",             "Topic",    EXPLORER_SOURCE_TOPIC},
    {"PUMP HOT",    "pump_in_hot",     "Platform", EXPLORER_SOURCE_PLATFORM},
    {"PUMP NEW",    "pump_in_new",     "Platform", EXPLORER_SOURCE_PLATFORM},
    {"4MEME HOT",   "fourmeme_in_hot", "Platform", EXPLORER_SOURCE_PLATFORM},
    {"4MEME NEW",   "fourmeme_in_new", "Platform", EXPLORER_SOURCE_PLATFORM},
};

static const explorer_surface_model_t MENU_MODEL = {
    "^ v MOVE",
    " | B CLOSE",
    "> OPEN | Y PORTFOLIO",
};

static const explorer_surface_model_t SEARCH_MODEL = {
    "Say token",
    " | B CLOSE",
    "B Back | Y Port",
};

static const explorer_surface_model_t SOURCES_MODEL = {
    "^ v MOVE",
    " | B CLOSE",
    "> OPEN | Y PORTFOLIO",
};

static const explorer_surface_model_t TRADE_MODE_MODEL = {
    "^ v MOVE",
    "Mode picker",
    "> APPLY | B BACK",
};

static lv_obj_t *s_screen = NULL;
static lv_obj_t *s_top_bar = NULL;
static lv_obj_t *s_lbl_source = NULL;
static lv_obj_t *s_lbl_count = NULL;
static lv_obj_t *s_lbl_src_hint = NULL;
static lv_obj_t *s_lbl_nav_hint = NULL;
static lv_obj_t *s_lbl_action_hint = NULL;
static explorer_row_ui_t s_rows[VISIBLE_ROWS];
static explorer_surface_t s_surface = EXPLORER_SURFACE_MENU;
static int s_menu_idx = 0;
static int s_source_idx = 0;
static int s_trade_mode_idx = 0;
static char s_trade_mode[8] = "real";

#if defined(__GNUC__)
extern const char *screen_feed_get_last_search_query(void) __attribute__((weak));
#else
extern const char *screen_feed_get_last_search_query(void);
#endif

static int _center_text_y(const lv_font_t *font)
{
    int y = (ROW_H - lv_font_get_line_height(font)) / 2;
    return (y < 0) ? 0 : y;
}

static int _clamp_menu_idx(int idx)
{
    if (idx < 0) return 0;
    if (idx >= EXPLORER_ITEM_COUNT) return EXPLORER_ITEM_COUNT - 1;
    return idx;
}

static int _source_count(void)
{
    return (int)(sizeof(SOURCE_MENU) / sizeof(SOURCE_MENU[0]));
}

static int _trade_mode_count(void)
{
    return 2;
}

static int _clamp_source_idx(int idx)
{
    if (idx < 0) return 0;
    if (idx >= _source_count()) return _source_count() - 1;
    return idx;
}

static int _clamp_trade_mode_idx(int idx)
{
    if (idx < 0) return 0;
    if (idx >= _trade_mode_count()) return _trade_mode_count() - 1;
    return idx;
}

static const explorer_surface_model_t *_current_surface_model(void)
{
    if (s_surface == EXPLORER_SURFACE_SEARCH_GUIDE) return &SEARCH_MODEL;
    if (s_surface == EXPLORER_SURFACE_SOURCES) return &SOURCES_MODEL;
    if (s_surface == EXPLORER_SURFACE_TRADE_MODE) return &TRADE_MODE_MODEL;
    return &MENU_MODEL;
}

static const char *_trade_mode_subtitle(void)
{
    return (strcmp(s_trade_mode, "paper") == 0) ? "Current: Paper" : "Current: Real";
}

static void _set_trade_mode_local(const char *mode)
{
    if (mode && strcmp(mode, "paper") == 0) {
        snprintf(s_trade_mode, sizeof(s_trade_mode), "%s", "paper");
        s_trade_mode_idx = 1;
        return;
    }
    snprintf(s_trade_mode, sizeof(s_trade_mode), "%s", "real");
    s_trade_mode_idx = 0;
}

static void _sync_trade_mode_from_json(const char *json)
{
    const char *p;
    if (!json) return;
    p = strstr(json, "\"trade_mode\"");
    if (!p) return;
    p = strchr(p, ':');
    if (!p) return;
    p++;
    while (*p == ' ' || *p == '\t') p++;
    if (*p != '"') return;
    if (strncmp(p, "\"paper\"", 7) == 0) {
        _set_trade_mode_local("paper");
    } else if (strncmp(p, "\"real\"", 6) == 0) {
        _set_trade_mode_local("real");
    }
}

static void _apply_row_layout(explorer_row_ui_t *ui)
{
    if (!ui) return;
    lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
    lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_14, 0);
    lv_obj_set_pos(ui->lbl_sym, COL_OVERLAY_TITLE_X, _center_text_y(ave_font_cjk_16()));
    lv_obj_set_width(ui->lbl_sym, COL_OVERLAY_TITLE_W);
    lv_obj_set_pos(ui->lbl_price, COL_OVERLAY_DETAIL_X, _center_text_y(&lv_font_montserrat_14));
    lv_obj_set_width(ui->lbl_price, COL_OVERLAY_DETAIL_W);
    lv_obj_set_style_text_align(ui->lbl_price, LV_TEXT_ALIGN_LEFT, 0);
}

static void _set_row(explorer_row_ui_t *ui,
                     lv_color_t row_bg,
                     lv_color_t chain_color,
                     const char *chain,
                     const char *title,
                     const char *detail)
{
    lv_obj_set_style_bg_color(ui->row, row_bg, 0);
    lv_label_set_text(ui->lbl_chain, chain ? chain : "");
    lv_obj_set_style_text_color(ui->lbl_chain, chain_color, 0);
    lv_label_set_text(ui->lbl_sym, title ? title : "");
    lv_obj_set_style_text_color(ui->lbl_sym, COLOR_WHITE, 0);
    lv_label_set_text(ui->lbl_price, detail ? detail : "");
    lv_obj_set_style_text_color(ui->lbl_price, COLOR_GRAY, 0);
}

static void _clear_row(explorer_row_ui_t *ui)
{
    _set_row(ui, COLOR_BG, COLOR_GRAY, "", "", "");
}

static void _update_hints(void)
{
    const explorer_surface_model_t *model = _current_surface_model();
    if (!s_lbl_nav_hint || !s_lbl_src_hint || !s_lbl_action_hint) return;
    lv_label_set_text(s_lbl_nav_hint, model->nav_hint);
    lv_label_set_text(s_lbl_src_hint, model->top_hint);
    lv_label_set_text(s_lbl_action_hint, model->action_hint);
}

static void _refresh_count(void)
{
    if (!s_lbl_count) return;
    if (s_surface == EXPLORER_SURFACE_MENU) {
        char buf[24];
        snprintf(buf, sizeof(buf), "%d/%d", s_menu_idx + 1, EXPLORER_ITEM_COUNT);
        lv_label_set_text(s_lbl_count, buf);
        return;
    }
    if (s_surface == EXPLORER_SURFACE_SOURCES) {
        char buf[24];
        snprintf(buf, sizeof(buf), "%d/%d", s_source_idx + 1, _source_count());
        lv_label_set_text(s_lbl_count, buf);
        return;
    }
    if (s_surface == EXPLORER_SURFACE_TRADE_MODE) {
        char buf[24];
        snprintf(buf, sizeof(buf), "%d/%d", s_trade_mode_idx + 1, _trade_mode_count());
        lv_label_set_text(s_lbl_count, buf);
        return;
    }
    lv_label_set_text(s_lbl_count, "");
}

static void _render_rows(void)
{
    char last_search_line[40];
    const char *last_search = screen_feed_get_last_search_query ? screen_feed_get_last_search_query() : "";
    static const char *guide_title[VISIBLE_ROWS] = {
        "Search",
        "Hold FN",
        "Example",
        "Last search",
        "Voice",
        "",
        "",
        "",
    };
    const char *guide_detail[VISIBLE_ROWS] = {
        "Guided entry",
        "Say token",
        "BONK / PEPE / DOGE",
        last_search_line,
        "Y stays global",
        "",
        "",
        "",
    };

    snprintf(last_search_line, sizeof(last_search_line), "%s",
             (last_search && last_search[0]) ? last_search : "No recent search");

    _update_hints();
    _refresh_count();

    for (int r = 0; r < VISIBLE_ROWS; r++) {
        explorer_row_ui_t *ui = &s_rows[r];
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        _apply_row_layout(ui);

        if (s_surface == EXPLORER_SURFACE_MENU) {
            if (r >= EXPLORER_ITEM_COUNT) {
                _clear_row(ui);
                continue;
            }
            const char *detail = MENU_ITEMS[r].subtitle;
            if (MENU_ITEMS[r].id == EXPLORER_ITEM_TRADE_MODE) {
                detail = _trade_mode_subtitle();
            }
            int selected = (r == s_menu_idx);
            _set_row(ui,
                     selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                     selected ? COLOR_WHITE : COLOR_GRAY,
                     selected ? ">" : "",
                     MENU_ITEMS[r].title,
                     detail);
            continue;
        }

        if (s_surface == EXPLORER_SURFACE_SOURCES) {
            if (r >= _source_count()) {
                _clear_row(ui);
                continue;
            }
            int selected = (r == s_source_idx);
            _set_row(ui,
                     selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                     selected ? COLOR_WHITE : COLOR_GRAY,
                     selected ? ">" : "",
                     SOURCE_MENU[r].label,
                     SOURCE_MENU[r].subtitle);
            continue;
        }

        if (s_surface == EXPLORER_SURFACE_TRADE_MODE) {
            static const char *mode_title[2] = {"Real Trading", "Paper Trading"};
            static const char *mode_detail[2] = {
                "Live wallet and orders",
                "Simulated funds and fills",
            };
            if (r >= _trade_mode_count()) {
                _clear_row(ui);
                continue;
            }
            int selected = (r == s_trade_mode_idx);
            _set_row(ui,
                     selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                     selected ? COLOR_WHITE : COLOR_GRAY,
                     selected ? ">" : "",
                     mode_title[r],
                     mode_detail[r]);
            continue;
        }

        _set_row(ui,
                 (r == 0) ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG),
                 (r == 0) ? COLOR_WHITE : COLOR_GRAY,
                 "",
                 guide_title[r],
                 guide_detail[r]);
    }
}

static void _show_feed_and_send(const char *cmd)
{
    ave_sm_open_feed_cached();
    if (cmd && cmd[0]) ave_send_json(cmd);
}

static void _apply_trade_mode_selection(void)
{
    s_trade_mode_idx = _clamp_trade_mode_idx(s_trade_mode_idx);
    if (s_trade_mode_idx <= 0) {
        _set_trade_mode_local("real");
        ave_send_json("{\"type\":\"key_action\",\"action\":\"trade_mode_set\",\"mode\":\"real\"}");
    } else {
        _set_trade_mode_local("paper");
        ave_send_json("{\"type\":\"key_action\",\"action\":\"trade_mode_set\",\"mode\":\"paper\"}");
    }
    s_surface = EXPLORER_SURFACE_MENU;
    if (s_lbl_source) lv_label_set_text(s_lbl_source, "EXPLORER");
    _render_rows();
}

static void _activate_menu_item(void)
{
    const explorer_item_t *item = &MENU_ITEMS[_clamp_menu_idx(s_menu_idx)];

    if (item->id == EXPLORER_ITEM_SEARCH) {
        s_surface = EXPLORER_SURFACE_SEARCH_GUIDE;
        _render_rows();
        return;
    }

    if (item->id == EXPLORER_ITEM_SOURCES) {
        s_surface = EXPLORER_SURFACE_SOURCES;
        s_source_idx = 0;
        _render_rows();
        return;
    }

    if (item->id == EXPLORER_ITEM_ORDERS) {
        _show_feed_and_send("{\"type\":\"key_action\",\"action\":\"orders\"}");
        return;
    }

    if (item->id == EXPLORER_ITEM_TRADE_MODE) {
        s_surface = EXPLORER_SURFACE_TRADE_MODE;
        s_trade_mode_idx = (strcmp(s_trade_mode, "paper") == 0) ? 1 : 0;
        if (s_lbl_source) lv_label_set_text(s_lbl_source, "MODE");
        _render_rows();
        return;
    }

    if (item->id == EXPLORER_ITEM_SIGNALS) {
        ave_sm_open_browse("signals");
        ave_send_json("{\"type\":\"key_action\",\"action\":\"signals\"}");
        return;
    }

    if (item->id == EXPLORER_ITEM_WATCHLIST) {
        ave_sm_open_browse("watchlist");
        ave_send_json("{\"type\":\"key_action\",\"action\":\"watchlist\"}");
    }
}

static void _activate_source_item(void)
{
    char cmd[256];
    const explorer_source_entry_t *entry = &SOURCE_MENU[_clamp_source_idx(s_source_idx)];

    if (entry->kind == EXPLORER_SOURCE_TOPIC) {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                 entry->value);
    } else {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_platform\",\"platform\":\"%s\"}",
                 entry->value);
    }

    _show_feed_and_send(cmd);
}

static void _build_screen(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_size(s_screen, 320, 240);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_clear_flag(s_screen, LV_OBJ_FLAG_SCROLLABLE);

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
    lv_label_set_text(s_lbl_source, "EXPLORER");
    lv_obj_set_style_text_color(s_lbl_source, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_source, &lv_font_montserrat_12, 0);

    s_lbl_count = lv_label_create(s_top_bar);
    lv_obj_align(s_lbl_count, LV_ALIGN_RIGHT_MID, -8, 0);
    lv_obj_set_style_text_color(s_lbl_count, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_count, &lv_font_montserrat_12, 0);

    s_lbl_src_hint = lv_label_create(s_top_bar);
    lv_obj_set_pos(s_lbl_src_hint, 76, 6);
    lv_obj_set_width(s_lbl_src_hint, 164);
    lv_label_set_long_mode(s_lbl_src_hint, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_src_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_src_hint, &lv_font_montserrat_12, 0);

    for (int r = 0; r < VISIBLE_ROWS; r++) {
        explorer_row_ui_t *ui = &s_rows[r];
        ui->row = lv_obj_create(s_screen);
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        lv_obj_set_style_bg_color(ui->row, COLOR_BG, 0);
        lv_obj_set_style_bg_opa(ui->row, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(ui->row, 0, 0);
        lv_obj_set_style_pad_all(ui->row, 0, 0);
        lv_obj_clear_flag(ui->row, LV_OBJ_FLAG_SCROLLABLE);

        ui->lbl_chain = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
        lv_obj_set_style_text_color(ui->lbl_chain, COLOR_GRAY, 0);
        lv_obj_set_pos(ui->lbl_chain, COL_CHAIN_X, _center_text_y(&lv_font_montserrat_12));
        lv_obj_set_width(ui->lbl_chain, 32);
        lv_label_set_long_mode(ui->lbl_chain, LV_LABEL_LONG_CLIP);

        ui->lbl_sym = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
        lv_obj_set_style_text_color(ui->lbl_sym, COLOR_WHITE, 0);
        lv_label_set_long_mode(ui->lbl_sym, LV_LABEL_LONG_CLIP);

        ui->lbl_price = lv_label_create(ui->row);
        lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_14, 0);
        lv_obj_set_style_text_color(ui->lbl_price, COLOR_GRAY, 0);
        lv_label_set_long_mode(ui->lbl_price, LV_LABEL_LONG_CLIP);
    }

    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_set_pos(div, 0, BOTTOM_Y - 1);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_bg_opa(div, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

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
    lv_obj_set_style_text_color(s_lbl_nav_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_nav_hint, &lv_font_montserrat_12, 0);

    s_lbl_action_hint = lv_label_create(bot);
    lv_label_set_long_mode(s_lbl_action_hint, LV_LABEL_LONG_CLIP);
    lv_obj_set_width(s_lbl_action_hint, 200);
    lv_obj_align(s_lbl_action_hint, LV_ALIGN_RIGHT_MID, -8, 0);
    lv_obj_set_style_text_color(s_lbl_action_hint, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_action_hint, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_action_hint, LV_TEXT_ALIGN_RIGHT, 0);
}

void screen_explorer_show(const char *json_data)
{
    _sync_trade_mode_from_json(json_data);
    if (!s_screen) _build_screen();
    lv_screen_load(s_screen);
    s_surface = EXPLORER_SURFACE_MENU;
    s_menu_idx = 0;
    s_source_idx = 0;
    s_trade_mode_idx = (strcmp(s_trade_mode, "paper") == 0) ? 1 : 0;
    if (s_lbl_source) lv_label_set_text(s_lbl_source, "EXPLORER");
    _render_rows();
}

void screen_explorer_key(int key)
{
    if (s_surface == EXPLORER_SURFACE_MENU) {
        if (key == AVE_KEY_UP) {
            if (s_menu_idx > 0) s_menu_idx--;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_DOWN) {
            if (s_menu_idx < EXPLORER_ITEM_COUNT - 1) s_menu_idx++;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
            _activate_menu_item();
            return;
        }
        if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
            ave_sm_open_feed_cached();
            return;
        }
        return;
    }

    if (s_surface == EXPLORER_SURFACE_SOURCES) {
        if (key == AVE_KEY_UP) {
            if (s_source_idx > 0) s_source_idx--;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_DOWN) {
            if (s_source_idx < _source_count() - 1) s_source_idx++;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
            _activate_source_item();
            return;
        }
        if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
            s_surface = EXPLORER_SURFACE_MENU;
            _render_rows();
            return;
        }
        return;
    }

    if (s_surface == EXPLORER_SURFACE_TRADE_MODE) {
        if (key == AVE_KEY_UP) {
            if (s_trade_mode_idx > 0) s_trade_mode_idx--;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_DOWN) {
            if (s_trade_mode_idx < _trade_mode_count() - 1) s_trade_mode_idx++;
            _render_rows();
            return;
        }
        if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
            _apply_trade_mode_selection();
            return;
        }
        if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
            s_surface = EXPLORER_SURFACE_MENU;
            if (s_lbl_source) lv_label_set_text(s_lbl_source, "EXPLORER");
            _render_rows();
            return;
        }
        return;
    }

    if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
        s_surface = EXPLORER_SURFACE_MENU;
        if (s_lbl_source) lv_label_set_text(s_lbl_source, "EXPLORER");
        _render_rows();
    }
}

int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
