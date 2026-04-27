/**
 * @file screen_browse.c
 * @brief Dedicated browse list screen shared by Signals and Watchlist.
 */
#include "ave_screen_manager.h"
#include "ave_font_provider.h"
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

#define MAX_BROWSE_TOKENS 20
#define VISIBLE_ROWS      6
#define ROW_H             32
#define TOP_BAR_H         22
#define BOTTOM_Y          215

#define COL_CHAIN_X  4
#define COL_SYM_X    42
#define COL_PRICE_X  154
#define COL_CHG_X    252

#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)
#define COLOR_SEL     lv_color_hex(0x0D2010)
#define COLOR_ALT     lv_color_hex(0x0D0D0D)
#define COLOR_SOL     lv_color_hex(0x9945FF)
#define COLOR_ETH     lv_color_hex(0x627EEA)
#define COLOR_BSC     lv_color_hex(0xF3BA2F)
#define COLOR_BASE    lv_color_hex(0x0052FF)

typedef enum {
    BROWSE_MODE_SIGNALS = 0,
    BROWSE_MODE_WATCHLIST,
} browse_mode_t;

typedef struct {
    char token_id[80];
    char chain[16];
    char symbol[24];
    char price[24];
    char change_24h[16];
    int  change_positive;
    char signal_label[8];
    char signal_value[32];
    char signal_first[20];
    char signal_last[20];
    char signal_count[20];
    char signal_vol[20];
    char signal_type[32];
    char signal_summary[64];
    char headline[64];
} browse_token_t;

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
} browse_row_ui_t;

static browse_token_t s_tokens[MAX_BROWSE_TOKENS];
static int s_token_count = 0;
static int s_token_idx = 0;
static int s_scroll_top = 0;
static browse_mode_t s_mode = BROWSE_MODE_SIGNALS;
static char s_source_label[24] = "SIGNALS";

static lv_obj_t *s_screen = NULL;
static lv_obj_t *s_top_bar = NULL;
static lv_obj_t *s_lbl_source = NULL;
static lv_obj_t *s_lbl_count = NULL;
static lv_obj_t *s_lbl_src_hint = NULL;
static lv_obj_t *s_lbl_nav_hint = NULL;
static lv_obj_t *s_lbl_action_hint = NULL;
static browse_row_ui_t s_rows[VISIBLE_ROWS];

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

static const char *_chain_short(const char *chain)
{
    if (!chain || !chain[0]) return "???";
    if (strncmp(chain, "solana", 6) == 0) return "SOL";
    if (strncmp(chain, "eth", 3) == 0) return "ETH";
    if (strncmp(chain, "bsc", 3) == 0) return "BSC";
    if (strncmp(chain, "base", 4) == 0) return "BASE";
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
    if (strncmp(chain, "eth", 3) == 0) return COLOR_ETH;
    if (strncmp(chain, "bsc", 3) == 0) return COLOR_BSC;
    if (strncmp(chain, "base", 4) == 0) return COLOR_BASE;
    return COLOR_GRAY;
}

static const char *_chain_hex_from_short(const char *chain_short)
{
    if (!chain_short || !chain_short[0]) return NULL;
    if (strcmp(chain_short, "SOL") == 0) return "9945FF";
    if (strcmp(chain_short, "ETH") == 0) return "627EEA";
    if (strcmp(chain_short, "BSC") == 0) return "F3BA2F";
    if (strcmp(chain_short, "BASE") == 0) return "0052FF";
    return NULL;
}

static void _set_source_label_text(const char *source_label)
{
    char rendered[48];
    const char *label = (source_label && source_label[0]) ? source_label : "SIGNALS";
    const char *space = strrchr(label, ' ');
    const char *chain_hex = NULL;

    if (!s_lbl_source) return;

    if (space && *(space + 1)) {
        chain_hex = _chain_hex_from_short(space + 1);
    }

    if (chain_hex && space) {
        size_t prefix_len = (size_t)(space - label);
        snprintf(rendered, sizeof(rendered), "%.*s #%s %s#",
                 (int)prefix_len, label, chain_hex, space + 1);
        lv_label_set_recolor(s_lbl_source, true);
        lv_label_set_text(s_lbl_source, rendered);
        return;
    }

    lv_label_set_recolor(s_lbl_source, false);
    lv_label_set_text(s_lbl_source, label);
}

static const char *_signal_label(const browse_token_t *t)
{
    if (strcmp(t->signal_label, "BUY") == 0 || strcmp(t->signal_label, "SELL") == 0) {
        return t->signal_label;
    }
    if (strncmp(t->signal_value, "BUY", 3) == 0) return "BUY";
    if (strncmp(t->signal_value, "SELL", 4) == 0) return "SELL";
    if (strncmp(t->signal_summary, "Total bought", strlen("Total bought")) == 0) return "BUY";
    if (strncmp(t->signal_summary, "Total sold", strlen("Total sold")) == 0) return "SELL";
    return "";
}

static const char *_signal_value(const browse_token_t *t)
{
    if (t->signal_value[0]) return t->signal_value;
    if (strcmp(_signal_label(t), "BUY") == 0) return "BUY";
    if (strcmp(_signal_label(t), "SELL") == 0) return "SELL";
    return "SIGNAL";
}

static const char *_signal_summary(const browse_token_t *t)
{
    if (t->signal_summary[0]) return t->signal_summary;
    if (strcmp(_signal_label(t), "BUY") == 0) return "Buy signal";
    if (strcmp(_signal_label(t), "SELL") == 0) return "Sell signal";
    return "Signal updating";
}

static const char *_signal_first(const browse_token_t *t)
{
    return t->signal_first[0] ? t->signal_first : "First -";
}

static const char *_signal_last(const browse_token_t *t)
{
    return t->signal_last[0] ? t->signal_last : "Last -";
}

static const char *_signal_count(const browse_token_t *t)
{
    return t->signal_count[0] ? t->signal_count : "Count -";
}

static const char *_signal_vol(const browse_token_t *t)
{
    return t->signal_vol[0] ? t->signal_vol : "Vol -";
}

static int _browse_first_line_y(void)
{
    return 1;
}

static int _browse_second_line_y(void)
{
    int line_height = lv_font_get_line_height(&lv_font_montserrat_12);
    int y = ROW_H - line_height;
    return (y < 0) ? 0 : y;
}

static void _apply_row_layout(browse_row_ui_t *ui)
{
    int first_line_y = _browse_first_line_y();
    int second_line_y = _browse_second_line_y();
    int meta_x = COL_SYM_X;
    int meta_w = (320 - COL_SYM_X - 4) / 4;
    lv_obj_set_style_text_font(ui->lbl_chain, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_sym, ave_font_cjk_16(), 0);
    lv_obj_set_style_text_font(ui->lbl_price, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_chg, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_subtitle, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_meta1, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_meta2, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_meta3, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_font(ui->lbl_meta4, &lv_font_montserrat_12, 0);

    lv_obj_set_pos(ui->lbl_chain, COL_CHAIN_X, first_line_y);
    lv_obj_set_pos(ui->lbl_sym, COL_SYM_X, first_line_y);
    lv_obj_set_width(ui->lbl_sym, 120);
    lv_obj_set_style_text_align(ui->lbl_sym, LV_TEXT_ALIGN_LEFT, 0);

    lv_obj_set_pos(ui->lbl_price, COL_PRICE_X, first_line_y);
    lv_obj_set_width(ui->lbl_price, 90);
    lv_obj_set_style_text_align(ui->lbl_price, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_set_pos(ui->lbl_subtitle, COL_SYM_X, second_line_y);
    lv_obj_set_width(ui->lbl_subtitle, COL_CHG_X - COL_SYM_X);
    lv_obj_set_style_text_align(ui->lbl_subtitle, LV_TEXT_ALIGN_LEFT, 0);

    lv_obj_set_pos(ui->lbl_chg, COL_CHG_X, second_line_y);
    lv_obj_set_width(ui->lbl_chg, 60);
    lv_obj_set_style_text_align(ui->lbl_chg, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_set_pos(ui->lbl_meta1, meta_x, second_line_y);
    lv_obj_set_width(ui->lbl_meta1, meta_w);
    lv_obj_set_style_text_align(ui->lbl_meta1, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_set_pos(ui->lbl_meta2, meta_x + meta_w, second_line_y);
    lv_obj_set_width(ui->lbl_meta2, meta_w);
    lv_obj_set_style_text_align(ui->lbl_meta2, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_set_pos(ui->lbl_meta3, meta_x + meta_w * 2, second_line_y);
    lv_obj_set_width(ui->lbl_meta3, meta_w);
    lv_obj_set_style_text_align(ui->lbl_meta3, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_set_pos(ui->lbl_meta4, meta_x + meta_w * 3, second_line_y);
    lv_obj_set_width(ui->lbl_meta4, meta_w);
    lv_obj_set_style_text_align(ui->lbl_meta4, LV_TEXT_ALIGN_CENTER, 0);
}

static void _set_mode_from_string(const char *mode)
{
    if (mode && strcmp(mode, "watchlist") == 0) {
        s_mode = BROWSE_MODE_WATCHLIST;
        snprintf(s_source_label, sizeof(s_source_label), "%s", "WATCHLIST");
    } else {
        s_mode = BROWSE_MODE_SIGNALS;
        snprintf(s_source_label, sizeof(s_source_label), "%s", "SIGNALS");
    }
    _set_source_label_text(s_source_label);
}

static void _load_placeholder(void)
{
    memset(s_tokens, 0, sizeof(s_tokens));
    s_token_count = 1;
    s_token_idx = 0;
    s_scroll_top = 0;
    snprintf(s_tokens[0].symbol, sizeof(s_tokens[0].symbol), "%s", "LOADING");
    snprintf(s_tokens[0].price, sizeof(s_tokens[0].price), "%s", "--");
    snprintf(
        s_tokens[0].signal_summary,
        sizeof(s_tokens[0].signal_summary),
        "%s",
        s_mode == BROWSE_MODE_SIGNALS ? "Signal updating" : "Fetching latest rows"
    );
    snprintf(s_tokens[0].signal_label, sizeof(s_tokens[0].signal_label), "%s", "");
    snprintf(s_tokens[0].signal_value, sizeof(s_tokens[0].signal_value), "%s", "SIGNAL");
    snprintf(s_tokens[0].signal_first, sizeof(s_tokens[0].signal_first), "%s", "First -");
    snprintf(s_tokens[0].signal_last, sizeof(s_tokens[0].signal_last), "%s", "Last -");
    snprintf(s_tokens[0].signal_count, sizeof(s_tokens[0].signal_count), "%s", "Count -");
    snprintf(s_tokens[0].signal_vol, sizeof(s_tokens[0].signal_vol), "%s", "Vol -");
    snprintf(s_tokens[0].signal_type, sizeof(s_tokens[0].signal_type), "%s", "");
    s_tokens[0].change_positive = -1;
}

static void _refresh_count(void)
{
    if (!s_lbl_count) return;
    if (s_token_count > 0) {
        char buf[24];
        snprintf(buf, sizeof(buf), "%d/%d", s_token_idx + 1, s_token_count);
        lv_label_set_text(s_lbl_count, buf);
    } else {
        lv_label_set_text(s_lbl_count, "");
    }
}

static void _update_hints(void)
{
    if (!s_lbl_nav_hint || !s_lbl_src_hint || !s_lbl_action_hint) return;
    lv_label_set_text(s_lbl_nav_hint, "^ v MOVE");
    lv_label_set_text(s_lbl_src_hint, "");
    lv_label_set_text(s_lbl_action_hint, "> Detail | X Chain | B Back");
}

static void _clear_row(browse_row_ui_t *ui)
{
    lv_obj_set_style_bg_color(ui->row, COLOR_BG, 0);
    lv_label_set_text(ui->lbl_chain, "");
    lv_label_set_text(ui->lbl_sym, "");
    lv_label_set_text(ui->lbl_price, "");
    lv_label_set_text(ui->lbl_subtitle, "");
    lv_label_set_text(ui->lbl_chg, "");
    lv_label_set_text(ui->lbl_meta1, "");
    lv_label_set_text(ui->lbl_meta2, "");
    lv_label_set_text(ui->lbl_meta3, "");
    lv_label_set_text(ui->lbl_meta4, "");
}

static void _render_rows(void)
{
    _update_hints();
    _refresh_count();

    for (int r = 0; r < VISIBLE_ROWS; r++) {
        browse_row_ui_t *ui = &s_rows[r];
        int tok_idx = s_scroll_top + r;
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        _apply_row_layout(ui);

        if (tok_idx >= s_token_count) {
            _clear_row(ui);
            continue;
        }

        const browse_token_t *t = &s_tokens[tok_idx];
        int selected = (tok_idx == s_token_idx);
        lv_color_t text_color = selected ? COLOR_WHITE : COLOR_GRAY;
        lv_color_t row_bg = selected ? COLOR_SEL : ((r & 1) ? COLOR_ALT : COLOR_BG);
        lv_obj_set_style_bg_color(ui->row, row_bg, 0);

        lv_label_set_text(ui->lbl_chain, _chain_short(t->chain));
        lv_obj_set_style_text_color(ui->lbl_chain, _chain_color(t->chain), 0);
        lv_label_set_text(ui->lbl_sym, t->symbol[0] ? t->symbol : "???");
        lv_obj_set_style_text_color(ui->lbl_sym, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_price, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_subtitle, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_meta1, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_meta2, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_meta3, text_color, 0);
        lv_obj_set_style_text_color(ui->lbl_meta4, text_color, 0);

        if (s_mode == BROWSE_MODE_SIGNALS) {
            lv_label_set_text(ui->lbl_price, _signal_value(t));
            lv_label_set_text(ui->lbl_subtitle, "");
            lv_label_set_text(ui->lbl_chg, "");
            lv_label_set_text(ui->lbl_meta1, _signal_first(t));
            lv_label_set_text(ui->lbl_meta2, _signal_last(t));
            lv_label_set_text(ui->lbl_meta3, _signal_count(t));
            lv_label_set_text(ui->lbl_meta4, _signal_vol(t));
        } else {
            lv_obj_set_style_text_font(ui->lbl_subtitle, &lv_font_montserrat_12, 0);
            const char *chg_text = t->change_24h[0] ? t->change_24h : "--";
            lv_color_t chg_color = COLOR_GRAY;
            lv_label_set_text(ui->lbl_price, t->price[0] ? t->price : "--");
            lv_label_set_text(ui->lbl_subtitle, t->headline[0] ? t->headline : "Saved token");
            lv_label_set_text(ui->lbl_chg, chg_text);
            lv_label_set_text(ui->lbl_meta1, "");
            lv_label_set_text(ui->lbl_meta2, "");
            lv_label_set_text(ui->lbl_meta3, "");
            lv_label_set_text(ui->lbl_meta4, "");
            if (t->change_24h[0]) {
                if (t->change_positive > 0) chg_color = COLOR_GREEN;
                else if (t->change_positive == 0) chg_color = COLOR_RED;
            }
            lv_obj_set_style_text_color(ui->lbl_chg, chg_color, 0);
        }
    }
}

static void _parse_tokens_from_json(const char *json)
{
    s_token_count = 0;
    const char *arr = strstr(json, "\"tokens\"");
    if (!arr) {
        _load_placeholder();
        return;
    }
    arr = strchr(arr, '[');
    if (!arr) {
        _load_placeholder();
        return;
    }
    arr++;

    const char *p = arr;
    while (*p && s_token_count < MAX_BROWSE_TOKENS) {
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
        char *obj = (char *)malloc(obj_len + 1);
        if (!obj) break;
        memcpy(obj, obj_start, obj_len);
        obj[obj_len] = '\0';

        browse_token_t *t = &s_tokens[s_token_count];
        memset(t, 0, sizeof(*t));
        _get_json_str_field(obj, "token_id", t->token_id, sizeof(t->token_id));
        _get_json_str_field(obj, "chain", t->chain, sizeof(t->chain));
        _get_json_str_field(obj, "symbol", t->symbol, sizeof(t->symbol));
        _get_json_str_field(obj, "price", t->price, sizeof(t->price));
        _get_json_str_field(obj, "change_24h", t->change_24h, sizeof(t->change_24h));
        _get_json_str_field(obj, "signal_label", t->signal_label, sizeof(t->signal_label));
        _get_json_str_field(obj, "signal_value", t->signal_value, sizeof(t->signal_value));
        _get_json_str_field(obj, "signal_first", t->signal_first, sizeof(t->signal_first));
        _get_json_str_field(obj, "signal_last", t->signal_last, sizeof(t->signal_last));
        _get_json_str_field(obj, "signal_count", t->signal_count, sizeof(t->signal_count));
        _get_json_str_field(obj, "signal_vol", t->signal_vol, sizeof(t->signal_vol));
        _get_json_str_field(obj, "signal_type", t->signal_type, sizeof(t->signal_type));
        _get_json_str_field(obj, "signal_summary", t->signal_summary, sizeof(t->signal_summary));
        _get_json_str_field(obj, "headline", t->headline, sizeof(t->headline));
        t->change_positive = _get_json_int_field(obj, "change_positive", -1);
        if (!t->symbol[0]) snprintf(t->symbol, sizeof(t->symbol), "%s", "???");
        free(obj);
        s_token_count++;
    }

    if (s_token_count == 0) {
        _load_placeholder();
    }
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
    lv_obj_set_style_text_color(s_lbl_source, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_source, &lv_font_montserrat_12, 0);
    _set_source_label_text(s_source_label);

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
        browse_row_ui_t *ui = &s_rows[r];
        ui->row = lv_obj_create(s_screen);
        lv_obj_set_size(ui->row, 320, ROW_H);
        lv_obj_set_pos(ui->row, 0, TOP_BAR_H + r * ROW_H);
        lv_obj_set_style_bg_color(ui->row, COLOR_BG, 0);
        lv_obj_set_style_bg_opa(ui->row, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(ui->row, 0, 0);
        lv_obj_set_style_pad_all(ui->row, 0, 0);
        lv_obj_clear_flag(ui->row, LV_OBJ_FLAG_SCROLLABLE);

        ui->lbl_chain = lv_label_create(ui->row);
        ui->lbl_sym = lv_label_create(ui->row);
        ui->lbl_price = lv_label_create(ui->row);
        ui->lbl_chg = lv_label_create(ui->row);
        ui->lbl_subtitle = lv_label_create(ui->row);
        ui->lbl_meta1 = lv_label_create(ui->row);
        ui->lbl_meta2 = lv_label_create(ui->row);
        ui->lbl_meta3 = lv_label_create(ui->row);
        ui->lbl_meta4 = lv_label_create(ui->row);
        lv_label_set_long_mode(ui->lbl_chain, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_sym, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_price, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_chg, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_subtitle, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta1, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta2, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta3, LV_LABEL_LONG_CLIP);
        lv_label_set_long_mode(ui->lbl_meta4, LV_LABEL_LONG_CLIP);
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

void screen_browse_show_placeholder(const char *mode)
{
    if (!s_screen) _build_screen();
    _set_mode_from_string(mode);
    _load_placeholder();
    lv_screen_load(s_screen);
    _render_rows();
}

void screen_browse_reveal(void)
{
    if (!s_screen) {
        screen_browse_show_placeholder("signals");
        return;
    }
    lv_screen_load(s_screen);
    _render_rows();
}

void screen_browse_show(const char *json_data)
{
    char mode[16] = {0};
    char source_label[24] = {0};
    int requested_cursor;
    int max_scroll_top;

    if (!s_screen) _build_screen();
    lv_screen_load(s_screen);

    if (json_data && _get_json_str_field(json_data, "mode", mode, sizeof(mode))) {
        _set_mode_from_string(mode);
    }
    if (json_data && _get_json_str_field(json_data, "source_label", source_label, sizeof(source_label)) && source_label[0]) {
        snprintf(s_source_label, sizeof(s_source_label), "%s", source_label);
        _set_source_label_text(s_source_label);
    }

    if (!json_data || strcmp(json_data, "{}") == 0) {
        _render_rows();
        return;
    }

    _parse_tokens_from_json(json_data);
    requested_cursor = _get_json_int_field(json_data, "cursor", -1);
    if (requested_cursor >= 0 && requested_cursor < s_token_count) {
        s_token_idx = requested_cursor;
    } else {
        s_token_idx = 0;
    }
    max_scroll_top = (s_token_count > VISIBLE_ROWS) ? (s_token_count - VISIBLE_ROWS) : 0;
    s_scroll_top = (s_token_idx >= VISIBLE_ROWS) ? (s_token_idx - VISIBLE_ROWS + 1) : 0;
    if (s_scroll_top > max_scroll_top) s_scroll_top = max_scroll_top;
    _render_rows();
}

static void _move_selection(int delta)
{
    int max_scroll;
    if (s_token_count < 1) return;
    s_token_idx = (s_token_idx + delta + s_token_count) % s_token_count;
    if (s_token_idx < s_scroll_top) s_scroll_top = s_token_idx;
    else if (s_token_idx >= s_scroll_top + VISIBLE_ROWS) s_scroll_top = s_token_idx - VISIBLE_ROWS + 1;
    max_scroll = (s_token_count > VISIBLE_ROWS) ? (s_token_count - VISIBLE_ROWS) : 0;
    if (s_scroll_top > max_scroll) s_scroll_top = max_scroll;
    _render_rows();
}

static void _enter_selected_detail(void)
{
    char cmd[384];
    char cursor_buf[16];
    const char *origin = (s_mode == BROWSE_MODE_WATCHLIST) ? "watchlist" : "signals";
    ave_sm_json_field_t fields[] = {
        {"token_id", ""},
        {"chain", ""},
        {"cursor", cursor_buf},
        {"origin", origin},
    };

    if (s_token_count < 1) return;
    const browse_token_t *t = &s_tokens[s_token_idx];
    if (!t->token_id[0] || !t->chain[0]) return;

    snprintf(cursor_buf, sizeof(cursor_buf), "%d", s_token_idx);
    fields[0].value = t->token_id;
    fields[1].value = t->chain;
    if (!ave_sm_build_key_action_json("watch", fields, 4, cmd, sizeof(cmd))) return;
    ave_send_json(cmd);
}

static void _emit_watchlist_remove(void)
{
    char cmd[384];
    char cursor_buf[16];
    ave_sm_json_field_t fields[] = {
        {"token_id", ""},
        {"chain", ""},
        {"cursor", cursor_buf},
    };

    if (s_token_count < 1) return;
    const browse_token_t *t = &s_tokens[s_token_idx];
    if (!t->token_id[0] || !t->chain[0]) return;

    snprintf(cursor_buf, sizeof(cursor_buf), "%d", s_token_idx);
    fields[0].value = t->token_id;
    fields[1].value = t->chain;
    if (ave_sm_build_key_action_json("watchlist_remove", fields, 3, cmd, sizeof(cmd))) {
        ave_send_json(cmd);
    }
}

void screen_browse_key(int key)
{
    if (key == AVE_KEY_UP) {
        _move_selection(-1);
        return;
    }
    if (key == AVE_KEY_DOWN) {
        _move_selection(+1);
        return;
    }
    if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
        _enter_selected_detail();
        return;
    }
    if (key == AVE_KEY_X) {
        if (s_mode == BROWSE_MODE_WATCHLIST) {
            ave_send_json("{\"type\":\"key_action\",\"action\":\"watchlist_chain_cycle\"}");
        } else {
            ave_send_json("{\"type\":\"key_action\",\"action\":\"signals_chain_cycle\"}");
        }
        return;
    }
    if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
        ave_sm_open_explorer();
    }
}

int screen_browse_get_selected_context_json(char *out, size_t out_n)
{
    char addr_esc[256];
    char chain_esc[64];
    char symbol_esc[64];
    const browse_token_t *t;
    int n;

    if (!out || out_n == 0) return 0;
    if (s_token_count < 1 || s_token_idx < 0 || s_token_idx >= s_token_count) return 0;

    t = &s_tokens[s_token_idx];
    if (!t->token_id[0] || !t->chain[0]) return 0;
    if (!ave_sm_json_escape_string(t->token_id, addr_esc, sizeof(addr_esc))) return 0;
    if (!ave_sm_json_escape_string(t->chain, chain_esc, sizeof(chain_esc))) return 0;
    if (!ave_sm_json_escape_string(t->symbol, symbol_esc, sizeof(symbol_esc))) return 0;

    n = snprintf(out, out_n,
                 "{\"screen\":\"browse\",\"cursor\":%d,\"token\":{\"addr\":\"%s\",\"chain\":\"%s\",\"symbol\":\"%s\"}}",
                 s_token_idx,
                 addr_esc,
                 chain_esc,
                 symbol_esc);
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

const char *screen_browse_get_source_label(void)
{
    return s_source_label;
}
