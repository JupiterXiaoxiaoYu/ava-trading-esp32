/**
 * @file screen_spotlight.c
 * @brief SPOTLIGHT screen — token detail with K-line chart and risk info.
 *
 * Layout (320×240 landscape):
 *   y=  0..22   top bar: symbol  price  change%
 *   y= 22..145  lv_chart K-line (320×123px)
 *   y=145..168  risk badges: [SAFE/DANGER] [MINT:NO] [FREEZE:NO]
 *   y=168..190  holders + liquidity
 *   y=190..215  divider
 *   y=215..240  bottom bar: [B] BACK  [X] SELL  [A] BUY  [Y] PORTFOLIO
 */
#include "ave_screen_manager.h"
#include "ave_transport.h"
#include "ave_price_fmt.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define MAX_CHART_PTS 100

static lv_obj_t *s_screen      = NULL;
static lv_obj_t *s_lbl_sym     = NULL;
static lv_obj_t *s_lbl_price   = NULL;
static lv_obj_t *s_lbl_change  = NULL;
static lv_obj_t *s_chart       = NULL;
static lv_chart_series_t *s_ser = NULL;
static lv_obj_t *s_lbl_cmin    = NULL;
static lv_obj_t *s_lbl_cmax    = NULL;
static lv_obj_t *s_lbl_risk    = NULL;
static lv_obj_t *s_lbl_mint    = NULL;
static lv_obj_t *s_lbl_freeze  = NULL;
static lv_obj_t *s_lbl_holders  = NULL;
static lv_obj_t *s_lbl_liq      = NULL;
static lv_obj_t *s_lbl_t_start  = NULL;
static lv_obj_t *s_lbl_t_mid    = NULL;
static lv_obj_t *s_lbl_t_end    = NULL;

/* Cached for key handler */
static char s_token_id[120] = {0};
static char s_chain[20]     = {0};
static char s_symbol[24]    = {0};
static char s_contract_tail[12] = {0};
static char s_source_tag[24] = {0};

/* Navigation loading guard — set while waiting for feed_prev/next response */
static bool s_loading = false;
static uint32_t s_loading_started_ms = 0;
static lv_timer_t *s_loading_timer = NULL;
#define SPOTLIGHT_LOADING_TIMEOUT_MS 2500

/* Back fallback timer — cancelled when server responds, fires locally if not */
static lv_timer_t *s_back_timer = NULL;

void screen_spotlight_cancel_back_timer(void)
{
    if (s_back_timer) {
        lv_timer_del(s_back_timer);
        s_back_timer = NULL;
    }
}

static void _clear_loading_guard(void)
{
    s_loading = false;
    s_loading_started_ms = 0;
    if (s_loading_timer) {
        lv_timer_del(s_loading_timer);
        s_loading_timer = NULL;
    }
}

static void _loading_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_loading_timer = NULL;
    s_loading = false;
    s_loading_started_ms = 0;
    printf("[SPOTLIGHT] loading timeout released\n");
}

static void _refresh_loading_guard(void)
{
    if (!s_loading) return;
    if (lv_tick_elaps(s_loading_started_ms) < SPOTLIGHT_LOADING_TIMEOUT_MS) return;
    _clear_loading_guard();
}

static void _arm_loading_guard(void)
{
    s_loading = true;
    s_loading_started_ms = lv_tick_get();
    if (s_loading_timer) {
        lv_timer_del(s_loading_timer);
        s_loading_timer = NULL;
    }
    s_loading_timer = lv_timer_create(_loading_timeout_cb, SPOTLIGHT_LOADING_TIMEOUT_MS, NULL);
    if (s_loading_timer) lv_timer_set_repeat_count(s_loading_timer, 1);
}

/* K-line timeframe cycling */
static int s_interval_idx = 1;  /* default 1H */
static const char *INTERVALS[]     = {"5",   "60",  "240", "1440"};
static const char *INTERVAL_LBLS[] = {"5M",  "1H",  "4H",  "1D"};
#define N_INTERVALS 4

static lv_obj_t *s_lbl_tf  = NULL;
static lv_obj_t *s_lbl_pos = NULL;
static lv_obj_t *s_lbl_origin_hint = NULL;
static lv_obj_t *s_lbl_watchlist_star = NULL;

#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_CHART   lv_color_hex(0x0D1B2A)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)
#define COLOR_BADGE   lv_color_hex(0x1E1E1E)

/* ─── JSON helpers ───────────────────────────────────────────────────────── */
static int _str(const char *o, const char *k, char *out, int n) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p == '"') {
        p++; int i = 0;
        while (*p && *p != '"' && i < n-1) out[i++] = *p++;
        out[i] = 0; return 1;
    }
    return 0;
}

static int _bool(const char *o, const char *k, int def) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p == 't') return 1;
    if (*p == 'f') return 0;
    return def;
}

static int _int(const char *o, const char *k, int def) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p == '-' || (*p >= '0' && *p <= '9')) return atoi(p);
    return def;
}

static int _parse_chart(const char *json, int16_t *out, int max) {
    const char *p = strstr(json, "\"chart\"");
    if (!p) return 0;
    p = strchr(p, '['); if (!p) return 0;
    p++;
    int n = 0;
    while (*p && *p != ']' && n < max) {
        while (*p == ' ' || *p == ',') p++;
        if (*p == ']') break;
        int v = atoi(p);
        if (v < 0) v = 0;
        out[n++] = (int16_t)v;
        while (*p && *p != ',' && *p != ']') p++;
    }
    return n;
}

static void _identity_text(char *out, size_t out_n, const char *symbol, const char *chain, const char *tail)
{
    if (!out || out_n == 0) return;
    if (tail && tail[0]) {
        snprintf(out, out_n, "%s %s *%s", symbol && symbol[0] ? symbol : "???", chain && chain[0] ? chain : "?", tail);
        return;
    }
    snprintf(out, out_n, "%s %s", symbol && symbol[0] ? symbol : "???", chain && chain[0] ? chain : "?");
}

/* ─── Back fallback ──────────────────────────────────────────────────────── */
static void _back_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_back_timer = NULL;
    ave_sm_go_back_fallback();  /* prefer context-aware fallback */
}

/* ─── Build screen ───────────────────────────────────────────────────────── */
static void _build(void) {
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_set_size(s_screen, 320, 240);

    /* ── Top bar ─────────────────────────────────────────────────────── */
    lv_obj_t *top = lv_obj_create(s_screen);
    lv_obj_set_size(top, 320, 22);
    lv_obj_align(top, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_color(top, COLOR_BAR, 0);
    lv_obj_set_style_border_width(top, 0, 0);
    lv_obj_set_style_pad_all(top, 0, 0);

    s_lbl_sym = lv_label_create(top);
    lv_obj_align(s_lbl_sym, LV_ALIGN_LEFT_MID, 6, 0);
    lv_obj_set_style_text_color(s_lbl_sym, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_sym, &lv_font_montserrat_14, 0);

    s_lbl_price = lv_label_create(top);
    lv_obj_align(s_lbl_price, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_lbl_price, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_price, &lv_font_montserrat_14, 0);

    s_lbl_change = lv_label_create(top);
    lv_obj_align(s_lbl_change, LV_ALIGN_RIGHT_MID, -6, 0);
    lv_obj_set_style_text_font(s_lbl_change, &lv_font_montserrat_12, 0);

    s_lbl_tf = lv_label_create(top);
    lv_obj_align(s_lbl_tf, LV_ALIGN_RIGHT_MID, -78, 0);
    lv_obj_set_width(s_lbl_tf, 32);
    lv_label_set_long_mode(s_lbl_tf, LV_LABEL_LONG_CLIP);
    lv_label_set_text(s_lbl_tf, "1H");
    lv_obj_set_style_text_color(s_lbl_tf, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_tf, &lv_font_montserrat_12, 0);

    s_lbl_origin_hint = lv_label_create(top);
    lv_obj_set_width(s_lbl_origin_hint, 76);
    lv_label_set_long_mode(s_lbl_origin_hint, LV_LABEL_LONG_CLIP);
    lv_obj_align(s_lbl_origin_hint, LV_ALIGN_TOP_RIGHT, -4, 0);
    lv_label_set_text(s_lbl_origin_hint, "");
    lv_obj_set_style_text_color(s_lbl_origin_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_origin_hint, &lv_font_montserrat_12, 0);

    /* ── K-line chart (276×110, x=44 leaving room for Y labels) ────────── */
    s_chart = lv_chart_create(s_screen);
    lv_obj_set_size(s_chart, 276, 110);
    lv_obj_set_pos(s_chart, 44, 22);
    lv_obj_set_style_bg_color(s_chart, COLOR_CHART, 0);
    lv_obj_set_style_border_width(s_chart, 0, 0);
    lv_obj_set_style_pad_all(s_chart, 0, 0);
    lv_chart_set_type(s_chart, LV_CHART_TYPE_LINE);
    lv_chart_set_div_line_count(s_chart, 3, 1);  /* 3 h-lines, 1 v-line at 12h */
    lv_obj_set_style_line_color(s_chart, lv_color_hex(0x1A2A3A), LV_PART_MAIN);

    s_ser = lv_chart_add_series(s_chart, COLOR_GREEN, LV_CHART_AXIS_PRIMARY_Y);
    lv_chart_set_point_count(s_chart, MAX_CHART_PTS);

    /* Hide dots (LVGL 9: width + height) */
    lv_obj_set_style_size(s_chart, 0, 0, LV_PART_INDICATOR);

    /* Y-axis price labels (left of chart, x=2, clipped to 42px) */
    s_lbl_cmax = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_cmax, 2, 23);
    lv_obj_set_width(s_lbl_cmax, 42);
    lv_label_set_long_mode(s_lbl_cmax, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_cmax, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_cmax, &lv_font_montserrat_12, 0);

    s_lbl_cmin = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_cmin, 2, 119);  /* near chart bottom (22+110-13) */
    lv_obj_set_width(s_lbl_cmin, 42);
    lv_label_set_long_mode(s_lbl_cmin, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_cmin, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_cmin, &lv_font_montserrat_12, 0);

    /* X-axis time labels (below chart at y=134) — updated from JSON */
    s_lbl_t_start = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_t_start, 46, 134);
    lv_label_set_text(s_lbl_t_start, "");
    lv_obj_set_style_text_color(s_lbl_t_start, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_t_start, &lv_font_montserrat_12, 0);

    s_lbl_t_mid = lv_label_create(s_screen);
    lv_obj_align(s_lbl_t_mid, LV_ALIGN_TOP_MID, 22, 134);
    lv_label_set_text(s_lbl_t_mid, "");
    lv_obj_set_style_text_color(s_lbl_t_mid, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_t_mid, &lv_font_montserrat_12, 0);

    s_lbl_t_end = lv_label_create(s_screen);
    lv_obj_align(s_lbl_t_end, LV_ALIGN_TOP_RIGHT, -4, 134);
    lv_label_set_text(s_lbl_t_end, "now");
    lv_obj_set_style_text_color(s_lbl_t_end, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_t_end, &lv_font_montserrat_12, 0);

    /* ── Risk badges row ─────────────────────────────────────────────── */
    /* Risk level badge */
    lv_obj_t *rb = lv_obj_create(s_screen);
    lv_obj_set_size(rb, 90, 18);
    lv_obj_set_pos(rb, 4, 149);
    lv_obj_set_style_bg_color(rb, COLOR_BADGE, 0);
    lv_obj_set_style_border_width(rb, 0, 0);
    lv_obj_set_style_radius(rb, 4, 0);
    lv_obj_set_style_pad_all(rb, 0, 0);
    s_lbl_risk = lv_label_create(rb);
    lv_obj_align(s_lbl_risk, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_font(s_lbl_risk, &lv_font_montserrat_12, 0);

    /* Mintable badge */
    lv_obj_t *mb = lv_obj_create(s_screen);
    lv_obj_set_size(mb, 90, 18);
    lv_obj_set_pos(mb, 100, 149);
    lv_obj_set_style_bg_color(mb, COLOR_BADGE, 0);
    lv_obj_set_style_border_width(mb, 0, 0);
    lv_obj_set_style_radius(mb, 4, 0);
    lv_obj_set_style_pad_all(mb, 0, 0);
    s_lbl_mint = lv_label_create(mb);
    lv_obj_align(s_lbl_mint, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_font(s_lbl_mint, &lv_font_montserrat_12, 0);

    /* Freezable badge */
    lv_obj_t *fb = lv_obj_create(s_screen);
    lv_obj_set_size(fb, 90, 18);
    lv_obj_set_pos(fb, 196, 149);
    lv_obj_set_style_bg_color(fb, COLOR_BADGE, 0);
    lv_obj_set_style_border_width(fb, 0, 0);
    lv_obj_set_style_radius(fb, 4, 0);
    lv_obj_set_style_pad_all(fb, 0, 0);
    s_lbl_freeze = lv_label_create(fb);
    lv_obj_align(s_lbl_freeze, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_font(s_lbl_freeze, &lv_font_montserrat_12, 0);

    /* ── Holders / Liquidity ─────────────────────────────────────────── */
    s_lbl_holders = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_holders, 4, 172);
    lv_obj_set_style_text_color(s_lbl_holders, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_holders, &lv_font_montserrat_12, 0);

    s_lbl_liq = lv_label_create(s_screen);
    lv_obj_align(s_lbl_liq, LV_ALIGN_TOP_RIGHT, -28, 172);
    lv_obj_set_style_text_color(s_lbl_liq, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_liq, &lv_font_montserrat_12, 0);

    s_lbl_watchlist_star = lv_label_create(s_screen);
    lv_obj_align(s_lbl_watchlist_star, LV_ALIGN_TOP_RIGHT, -4, 172);
    lv_label_set_text(s_lbl_watchlist_star, "☆");
    lv_obj_set_style_text_color(s_lbl_watchlist_star, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_watchlist_star, &lv_font_montserrat_14, 0);

    /* ── Divider ─────────────────────────────────────────────────────── */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* Position indicator: "< N/M >" — updated in screen_spotlight_show().
     * Keep it above the bottom-bar affordances so the action keys remain unambiguous. */
    s_lbl_pos = lv_label_create(s_screen);
    lv_obj_align(s_lbl_pos, LV_ALIGN_BOTTOM_MID, 0, -18);
    lv_label_set_text(s_lbl_pos, "");
    lv_obj_set_style_text_color(s_lbl_pos, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_pos, &lv_font_montserrat_12, 0);

    /* ── Bottom bar affordances (Task 5) ─────────────────────────────── */
    lv_obj_t *bot = lv_obj_create(s_screen);
    lv_obj_set_size(bot, 320, 240 - 215);
    lv_obj_set_pos(bot, 0, 215);
    lv_obj_set_style_bg_opa(bot, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(bot, 0, 0);
    lv_obj_set_style_pad_all(bot, 0, 0);
    lv_obj_clear_flag(bot, LV_OBJ_FLAG_SCROLLABLE);

    /* Uneven slots leave enough room for the long "PORTFOLIO" label while keeping
     * trade actions visually distinct and non-overlapping on 320x240. */
    lv_obj_t *slot_b = lv_obj_create(bot);
    lv_obj_set_size(slot_b, 64, 240 - 215);
    lv_obj_set_pos(slot_b, 0, 0);
    lv_obj_set_style_bg_opa(slot_b, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_b, 0, 0);
    lv_obj_set_style_pad_all(slot_b, 0, 0);
    lv_obj_clear_flag(slot_b, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_x = lv_obj_create(bot);
    lv_obj_set_size(slot_x, 64, 240 - 215);
    lv_obj_set_pos(slot_x, 64, 0);
    lv_obj_set_style_bg_opa(slot_x, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_x, 0, 0);
    lv_obj_set_style_pad_all(slot_x, 0, 0);
    lv_obj_clear_flag(slot_x, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_a = lv_obj_create(bot);
    lv_obj_set_size(slot_a, 64, 240 - 215);
    lv_obj_set_pos(slot_a, 128, 0);
    lv_obj_set_style_bg_opa(slot_a, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_a, 0, 0);
    lv_obj_set_style_pad_all(slot_a, 0, 0);
    lv_obj_clear_flag(slot_a, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_y = lv_obj_create(bot);
    lv_obj_set_size(slot_y, 128, 240 - 215);
    lv_obj_set_pos(slot_y, 192, 0);
    lv_obj_set_style_bg_opa(slot_y, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_y, 0, 0);
    lv_obj_set_style_pad_all(slot_y, 0, 0);
    lv_obj_clear_flag(slot_y, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *lbl_back = lv_label_create(slot_b);
    lv_obj_align(lbl_back, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_back, "[B] BACK");
    lv_obj_set_style_text_color(lbl_back, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(lbl_back, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_sell = lv_label_create(slot_x);
    lv_obj_align(lbl_sell, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_sell, "[X] SELL");
    lv_obj_set_style_text_color(lbl_sell, COLOR_ORANGE, 0);
    lv_obj_set_style_text_font(lbl_sell, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_buy = lv_label_create(slot_a);
    lv_obj_align(lbl_buy, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_buy, "[A] BUY");
    lv_obj_set_style_text_color(lbl_buy, COLOR_GREEN, 0);
    lv_obj_set_style_text_font(lbl_buy, &lv_font_montserrat_12, 0);

    lv_obj_t *lbl_portfolio = lv_label_create(slot_y);
    lv_obj_align(lbl_portfolio, LV_ALIGN_CENTER, 0, 0);
    lv_label_set_text(lbl_portfolio, "[Y] PORTFOLIO");
    lv_obj_set_style_text_color(lbl_portfolio, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(lbl_portfolio, &lv_font_montserrat_12, 0);
}

/* ─── Public API ──────────────────────────────────────────────────────────── */

void screen_spotlight_show(const char *json_data)
{
    if (!s_screen) _build();

    /* Cancel back fallback timer — server responded successfully */
    screen_spotlight_cancel_back_timer();

    /* Clear navigation loading guard — new data has arrived */
    _clear_loading_guard();

    /* Reset interval to 1H on fresh (non-live) load */
    int is_live = _bool(json_data, "live", 0);
    if (!is_live) s_interval_idx = 1;
    lv_label_set_text(s_lbl_tf, INTERVAL_LBLS[s_interval_idx]);

    lv_screen_load(s_screen);

    /* Parse basic fields */
    char sym[24]={0}, price[24]={0}, change[20]={0}, risk_lvl[12]={0};
    char holders[20]={0}, liq[20]={0}, cmin[16]={0}, cmax[16]={0};
    char identity_buf[64]={0};
    s_token_id[0] = '\0';
    s_chain[0] = '\0';
    s_symbol[0] = '\0';
    s_contract_tail[0] = '\0';
    s_source_tag[0] = '\0';
    _str(json_data, "symbol",    sym,     sizeof(sym));
    _str(json_data, "price",     price,   sizeof(price));
    _str(json_data, "change_24h",change,  sizeof(change));
    _str(json_data, "risk_level",risk_lvl,sizeof(risk_lvl));
    _str(json_data, "holders",   holders, sizeof(holders));
    _str(json_data, "liquidity", liq,     sizeof(liq));
    _str(json_data, "token_id",  s_token_id, sizeof(s_token_id));
    _str(json_data, "chain",     s_chain,    sizeof(s_chain));
    _str(json_data, "contract_tail", s_contract_tail, sizeof(s_contract_tail));
    _str(json_data, "source_tag", s_source_tag, sizeof(s_source_tag));
    snprintf(s_symbol, sizeof(s_symbol), "%s", sym);
    /* Compact Y-axis labels; fall back to full price strings */
    if (!_str(json_data, "chart_min_y", cmin, sizeof(cmin)))
        _str(json_data, "chart_min", cmin, sizeof(cmin));
    if (!_str(json_data, "chart_max_y", cmax, sizeof(cmax)))
        _str(json_data, "chart_max", cmax, sizeof(cmax));

    int change_pos = _bool(json_data, "change_positive", 1);
    int is_honeypot = _bool(json_data, "is_honeypot", 0);
    int is_mintable = _bool(json_data, "is_mintable",  0);
    int is_freezable= _bool(json_data, "is_freezable", 0);

    /* Top bar */
    _identity_text(identity_buf, sizeof(identity_buf), sym, s_chain, s_contract_tail);
    lv_label_set_text(s_lbl_sym,   identity_buf);
    lv_label_set_text(s_lbl_price, price[0]  ? price  : "$0");
    lv_label_set_text(s_lbl_change,change[0] ? change : "N/A");
    lv_obj_set_style_text_color(s_lbl_change,
        change_pos ? COLOR_GREEN : COLOR_RED, 0);

    /* Chart — parse pre-normalized int array (always [0..1000] from server) */
    int16_t pts[MAX_CHART_PTS];
    int n = _parse_chart(json_data, pts, MAX_CHART_PTS);
    if (n > 0) {
        /* Fixed Y range matches the [0..1000] log-normalized output.
         * Top pixel = chart_max price, bottom pixel = chart_min price. */
        lv_chart_set_range(s_chart, LV_CHART_AXIS_PRIMARY_Y, 0, 1000);
        lv_chart_set_point_count(s_chart, (uint16_t)n);
        int32_t *y_arr = lv_chart_get_y_array(s_chart, s_ser);
        if (y_arr) {
            for (int i = 0; i < n; i++) y_arr[i] = (int32_t)pts[i];
        }
        lv_chart_refresh(s_chart);
        lv_obj_set_style_line_color(s_chart,
            change_pos ? COLOR_GREEN : COLOR_RED, LV_PART_ITEMS);
    }

    /* Y-axis price labels — always update so they track the current window */
    lv_label_set_text(s_lbl_cmin, cmin[0] ? cmin : "");
    lv_label_set_text(s_lbl_cmax, cmax[0] ? cmax : "");

    /* X-axis time labels */
    char ct_start[20]={0}, ct_mid[20]={0}, ct_end[20]={0};
    _str(json_data, "chart_t_start", ct_start, sizeof(ct_start));
    _str(json_data, "chart_t_mid",   ct_mid,   sizeof(ct_mid));
    _str(json_data, "chart_t_end",   ct_end,   sizeof(ct_end));
    if (ct_start[0]) lv_label_set_text(s_lbl_t_start, ct_start);
    if (ct_mid[0])   lv_label_set_text(s_lbl_t_mid,   ct_mid);
    lv_label_set_text(s_lbl_t_end, ct_end[0] ? ct_end : "now");

    /* Risk badges */
    if (is_honeypot) {
        lv_label_set_text(s_lbl_risk, "HONEYPOT");
        lv_obj_set_style_text_color(s_lbl_risk, COLOR_RED, 0);
    } else {
        const char *rl = risk_lvl[0] ? risk_lvl : "SAFE";
        lv_label_set_text(s_lbl_risk, rl);
        lv_color_t c = (strcmp(rl,"LOW")==0||strcmp(rl,"SAFE")==0) ?
                        COLOR_GREEN : COLOR_ORANGE;
        lv_obj_set_style_text_color(s_lbl_risk, c, 0);
    }

    lv_label_set_text(s_lbl_mint,   is_mintable  ? "MINT:YES" : "MINT:NO");
    lv_obj_set_style_text_color(s_lbl_mint,
        is_mintable ? COLOR_ORANGE : COLOR_GREEN, 0);

    lv_label_set_text(s_lbl_freeze, is_freezable ? "FREEZE:YES" : "FREEZE:NO");
    lv_obj_set_style_text_color(s_lbl_freeze,
        is_freezable ? COLOR_ORANGE : COLOR_GREEN, 0);

    /* Holders / Liquidity */
    char hbuf[32], lbuf[32];
    snprintf(hbuf, sizeof(hbuf), "Holders: %s", holders[0] ? holders : "--");
    snprintf(lbuf, sizeof(lbuf), "Liq: %s",     liq[0]     ? liq     : "--");
    lv_label_set_text(s_lbl_holders, hbuf);
    lv_label_set_text(s_lbl_liq,     lbuf);

    /* Feed position indicator (present only when navigating feed list) */
    int cursor = _int(json_data, "cursor", -1);
    int total  = _int(json_data, "total",   0);
    if (cursor >= 0 && total > 1) {
        lv_label_set_text_fmt(s_lbl_pos, "< %d/%d >", cursor + 1, total);
    } else {
        lv_label_set_text(s_lbl_pos, "");
    }
}

void screen_spotlight_key(int key)
{
    if (key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
        screen_spotlight_cancel_back_timer();
        s_back_timer = lv_timer_create(_back_timeout_cb, 3000, NULL);
        lv_timer_set_repeat_count(s_back_timer, 1);
    } else if (key == AVE_KEY_LEFT) {
        _arm_loading_guard();
        ave_send_json("{\"type\":\"key_action\",\"action\":\"feed_prev\"}");
        printf("[SPOTLIGHT] feed_prev\n");
    } else if (key == AVE_KEY_RIGHT) {
        _arm_loading_guard();
        ave_send_json("{\"type\":\"key_action\",\"action\":\"feed_next\"}");
        printf("[SPOTLIGHT] feed_next\n");
    } else if (key == AVE_KEY_A) {
        _refresh_loading_guard();
        if (s_loading || !s_token_id[0] || !s_chain[0]) return;
        /* key_action bypasses LLM — server calls ave_buy_token directly */
        char cmd[512];
        ave_sm_json_field_t fields[] = {
            {"token_id", s_token_id},
            {"chain", s_chain},
            {"symbol", s_symbol},
        };
        if (!ave_sm_build_key_action_json("buy", fields, 3, cmd, sizeof(cmd))) return;
        ave_send_json(cmd);
        printf("[SPOTLIGHT] BUY -> token=%s chain=%s\n", s_token_id, s_chain);
    } else if (key == AVE_KEY_UP) {
        if (!s_token_id[0] || !s_chain[0]) return;
        _arm_loading_guard();
        s_interval_idx = (s_interval_idx + 1) % N_INTERVALS;
        if (s_lbl_tf) lv_label_set_text(s_lbl_tf, INTERVAL_LBLS[s_interval_idx]);
        char cmd[512];
        ave_sm_json_field_t fields[] = {
            {"token_id", s_token_id},
            {"chain", s_chain},
            {"interval", INTERVALS[s_interval_idx]},
        };
        if (!ave_sm_build_key_action_json("kline_interval", fields, 3, cmd, sizeof(cmd))) return;
        ave_send_json(cmd);
        printf("[SPOTLIGHT] TF -> %s\n", INTERVAL_LBLS[s_interval_idx]);
    } else if (key == AVE_KEY_DOWN) {
        if (!s_token_id[0] || !s_chain[0]) return;
        _arm_loading_guard();
        s_interval_idx = (s_interval_idx - 1 + N_INTERVALS) % N_INTERVALS;
        if (s_lbl_tf) lv_label_set_text(s_lbl_tf, INTERVAL_LBLS[s_interval_idx]);
        char cmd2[512];
        ave_sm_json_field_t fields[] = {
            {"token_id", s_token_id},
            {"chain", s_chain},
            {"interval", INTERVALS[s_interval_idx]},
        };
        if (!ave_sm_build_key_action_json("kline_interval", fields, 3, cmd2, sizeof(cmd2))) return;
        ave_send_json(cmd2);
        printf("[SPOTLIGHT] TF -> %s\n", INTERVAL_LBLS[s_interval_idx]);
    } else if (key == AVE_KEY_X) {
        _refresh_loading_guard();
        if (s_loading || !s_token_id[0] || !s_chain[0]) return;
        char cmd[512];
        ave_sm_json_field_t fields[] = {
            {"token_id", s_token_id},
            {"chain", s_chain},
            {"symbol", s_symbol},
        };
        if (!ave_sm_build_key_action_json("quick_sell", fields, 3, cmd, sizeof(cmd))) return;
        ave_send_json(cmd);
        printf("[SPOTLIGHT] QUICK SELL -> token=%s chain=%s\n", s_token_id, s_chain);
    }
}

int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    char addr_esc[256];
    char chain_esc[64];
    char symbol_esc[64];

    if (!out || out_n == 0) return 0;
    if (!s_token_id[0]) return 0;
    if (!s_chain[0]) return 0;
    if (!ave_sm_json_escape_string(s_token_id, addr_esc, sizeof(addr_esc))) return 0;
    if (!ave_sm_json_escape_string(s_chain, chain_esc, sizeof(chain_esc))) return 0;
    if (!ave_sm_json_escape_string(s_symbol, symbol_esc, sizeof(symbol_esc))) return 0;

    int n = snprintf(
        out, out_n,
        "{\"screen\":\"spotlight\",\"token\":{\"addr\":\"%s\",\"chain\":\"%s\",\"symbol\":\"%s\"}}",
        addr_esc,
        chain_esc,
        symbol_esc
    );
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
