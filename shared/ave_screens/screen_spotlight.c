/**
 * @file screen_spotlight.c
 * @brief SPOTLIGHT screen — token detail with K-line chart and risk info.
 *
 * Layout (320×240 landscape):
 *   y=  0..22   top bar: symbol  price  change%
 *   y= 22..145  lv_chart K-line (320×123px)
 *   y=145..214  4-line compact footer stats:
 *               Risk|Mint|Freeze
 *               Vol24h|Liq|Mcap
 *               Holders|Top100
 *               CA short + page marker
 *   y=214..215  divider
 *   y=215..240  bottom bar: [B] BACK  [X] SELL  [A] BUY
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
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

#define MAX_CHART_PTS 100

static lv_obj_t *s_screen      = NULL;
static lv_obj_t *s_lbl_sym     = NULL;
static lv_obj_t *s_lbl_price   = NULL;
static lv_obj_t *s_lbl_change  = NULL;
static lv_obj_t *s_chart       = NULL;
static lv_chart_series_t *s_ser = NULL;
static lv_obj_t *s_lbl_cmin    = NULL;
static lv_obj_t *s_lbl_cmax    = NULL;
static lv_obj_t *s_lbl_stats_row1 = NULL;
static lv_obj_t *s_lbl_stats_row2 = NULL;
static lv_obj_t *s_lbl_stats_row3 = NULL;
static lv_obj_t *s_lbl_stats_row4 = NULL;
static lv_obj_t *s_lbl_t_start  = NULL;
static lv_obj_t *s_lbl_t_mid    = NULL;
static lv_obj_t *s_lbl_t_end    = NULL;

#define FOOTER_X 4
#define FOOTER_W 312
#define FOOTER_ROW4_Y 189
#define FOOTER_PAGE_W 72
#define FOOTER_ROW4_GAP 6

static int _copy_contract_candidate(const char *src, char *out, size_t out_n)
{
    size_t len = 0;

    if (!src || !src[0] || !out || out_n == 0) return 0;
    if (strstr(src, "...")) return 0;
    len = strlen(src);
    if (len < 13) return 0;
    snprintf(out, out_n, "%s", src);
    return 1;
}

static void _format_contract_short(
    const char *contract,
    const char *mint,
    const char *token_id,
    char *out,
    size_t out_n
)
{
    char raw[160] = {0};
    size_t len = 0;
    if (!out || out_n == 0) return;
    out[0] = '\0';
    if (_copy_contract_candidate(contract, raw, sizeof(raw)) ||
        _copy_contract_candidate(mint, raw, sizeof(raw)) ||
        _copy_contract_candidate(token_id, raw, sizeof(raw))) {
        len = strlen(raw);
        snprintf(out, out_n, "%.*s...%s", 6, raw, raw + len - 6);
        return;
    }
    snprintf(out, out_n, "N/A");
}

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
static int s_loading_reason = 0;
static char s_loading_origin_token_id[120] = {0};
static char s_loading_origin_chain[20] = {0};
static int s_loading_expected_interval_idx = -1;
static int s_loading_origin_cursor = -1;
static int s_loading_origin_total = 0;
static int s_loading_nav_delta = 0;
#define SPOTLIGHT_LOADING_TIMEOUT_MS 2500
#define SPOTLIGHT_LOADING_REASON_NONE 0
#define SPOTLIGHT_LOADING_REASON_FEED_NAV 1
#define SPOTLIGHT_LOADING_REASON_INTERVAL 2

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
/* Back fallback timer — cancelled when server responds, fires locally if not */
static lv_timer_t *s_back_timer = NULL;
#endif
static int s_feed_cursor = -1;
static int s_feed_total = 0;

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
void screen_spotlight_cancel_back_timer(void)
{
    if (s_back_timer) {
        lv_timer_del(s_back_timer);
        s_back_timer = NULL;
    }
}
#else
void screen_spotlight_cancel_back_timer(void) {}
#endif

static void _clear_loading_guard(void)
{
    s_loading = false;
    s_loading_started_ms = 0;
    s_loading_reason = SPOTLIGHT_LOADING_REASON_NONE;
    s_loading_origin_token_id[0] = '\0';
    s_loading_origin_chain[0] = '\0';
    s_loading_expected_interval_idx = -1;
    s_loading_origin_cursor = -1;
    s_loading_origin_total = 0;
    s_loading_nav_delta = 0;
    if (s_loading_timer) {
        lv_timer_del(s_loading_timer);
        s_loading_timer = NULL;
    }
}

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
static void _loading_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_loading_timer = NULL;
    s_loading = false;
    s_loading_started_ms = 0;
    s_loading_reason = SPOTLIGHT_LOADING_REASON_NONE;
    s_loading_origin_token_id[0] = '\0';
    s_loading_origin_chain[0] = '\0';
    s_loading_expected_interval_idx = -1;
    s_loading_origin_cursor = -1;
    s_loading_origin_total = 0;
    s_loading_nav_delta = 0;
    printf("[SPOTLIGHT] loading timeout released\n");
}
#endif

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
static void _refresh_loading_guard(void)
{
    if (!s_loading) return;
    if (lv_tick_elaps(s_loading_started_ms) < SPOTLIGHT_LOADING_TIMEOUT_MS) return;
    _clear_loading_guard();
}

static void _arm_loading_guard(
    int reason,
    const char *token_id,
    const char *chain,
    int expected_interval_idx,
    int nav_delta
)
{
    s_loading = true;
    s_loading_started_ms = lv_tick_get();
    s_loading_reason = reason;
    s_loading_expected_interval_idx = expected_interval_idx;
    snprintf(s_loading_origin_token_id, sizeof(s_loading_origin_token_id), "%s", token_id ? token_id : "");
    snprintf(s_loading_origin_chain, sizeof(s_loading_origin_chain), "%s", chain ? chain : "");
    s_loading_origin_cursor = (reason == SPOTLIGHT_LOADING_REASON_FEED_NAV) ? s_feed_cursor : -1;
    s_loading_origin_total = (reason == SPOTLIGHT_LOADING_REASON_FEED_NAV) ? s_feed_total : 0;
    s_loading_nav_delta = (reason == SPOTLIGHT_LOADING_REASON_FEED_NAV) ? nav_delta : 0;
    if (s_loading_timer) {
        lv_timer_del(s_loading_timer);
        s_loading_timer = NULL;
    }
    s_loading_timer = lv_timer_create(_loading_timeout_cb, SPOTLIGHT_LOADING_TIMEOUT_MS, NULL);
    if (s_loading_timer) lv_timer_set_repeat_count(s_loading_timer, 1);
}
#endif

static int _incoming_spotlight_releases_loading_guard(
    int is_live,
    const char *incoming_token_id,
    const char *incoming_chain,
    int incoming_interval_idx,
    int incoming_cursor,
    int incoming_total
)
{
    if (!s_loading) return 0;
    if (is_live) return 0;
    if (!incoming_token_id || !incoming_token_id[0]) return 0;
    if (!incoming_chain || !incoming_chain[0]) return 0;

    if (s_loading_reason == SPOTLIGHT_LOADING_REASON_FEED_NAV) {
        if (!s_loading_origin_token_id[0] || !s_loading_origin_chain[0]) return 1;
        if ((strcmp(incoming_token_id, s_loading_origin_token_id) != 0) ||
            (strcmp(incoming_chain, s_loading_origin_chain) != 0)) {
            return 1;
        }
        if (s_loading_origin_cursor < 0 || s_loading_nav_delta == 0) return 0;
        if (incoming_cursor < 0 || incoming_total <= 0) return 0;
        if (s_loading_origin_total > 0 && incoming_total != s_loading_origin_total) {
            return (incoming_cursor != s_loading_origin_cursor);
        }
        return ((incoming_cursor - s_loading_origin_cursor) * s_loading_nav_delta) > 0;
    }

    if (s_loading_reason == SPOTLIGHT_LOADING_REASON_INTERVAL) {
        if (strcmp(incoming_token_id, s_loading_origin_token_id) != 0) return 0;
        if (strcmp(incoming_chain, s_loading_origin_chain) != 0) return 0;
        if (s_loading_expected_interval_idx < 0) return 1;
        return incoming_interval_idx == s_loading_expected_interval_idx;
    }

    return 1;
}

/* K-line timeframe cycling */
static int s_interval_idx = 3;  /* default 1H */
static const char *INTERVALS[]     = {"s1",  "1",   "5",   "60",  "240", "1440"};
static const char *INTERVAL_LBLS[] = {"L1S", "L1M", "5M",  "1H",  "4H",  "1D"};
#define N_INTERVALS 6

static lv_obj_t *s_lbl_tf  = NULL;
static lv_obj_t *s_lbl_pos = NULL;

#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_CHART   lv_color_hex(0x0D1B2A)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)

/* ─── JSON helpers ───────────────────────────────────────────────────────── */
static int _str(const char *o, const char *k, char *out, int n) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t' || *p == ':') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, out, (size_t)n, NULL);
}

static int _bool(const char *o, const char *k, int def) {
    char qbuf[16];
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t' || *p == ':') p++;
    if (*p == '"') {
        if (!ave_json_decode_quoted(p, qbuf, sizeof(qbuf), NULL)) return def;
        if (!strcmp(qbuf, "1") || !strcmp(qbuf, "true") || !strcmp(qbuf, "TRUE")) return 1;
        if (!strcmp(qbuf, "0") || !strcmp(qbuf, "false") || !strcmp(qbuf, "FALSE")) return 0;
        return def;
    }
    if (*p == 't') return 1;
    if (*p == 'f') return 0;
    if (*p == '-' || isdigit((unsigned char)*p)) {
        return (strtol(p, NULL, 10) != 0) ? 1 : 0;
    }
    return def;
}

static int _int(const char *o, const char *k, int def) {
    char nd[64]; snprintf(nd, sizeof(nd), "\"%s\"", k);
    const char *p = strstr(o, nd); if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t' || *p == ':') p++;
    if (*p == '-' || (*p >= '0' && *p <= '9')) return atoi(p);
    return def;
}

static int _field_text(const char *o, const char *k, char *out, int n)
{
    char nd[64];
    const char *p;
    const char *start;
    size_t len = 0;

    if (_str(o, k, out, n)) return 1;
    if (!out || n <= 0) return 0;

    snprintf(nd, sizeof(nd), "\"%s\"", k);
    p = strstr(o, nd);
    if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t' || *p == ':') p++;
    if (!*p || *p == '{' || *p == '[' || *p == '"') return 0;

    start = p;
    while (*p && *p != ',' && *p != '}' && *p != ']') p++;
    while (p > start && (p[-1] == ' ' || p[-1] == '\t' || p[-1] == '\n' || p[-1] == '\r')) p--;
    len = (size_t)(p - start);
    if (len == 0 || len >= (size_t)n) return 0;

    memcpy(out, start, len);
    out[len] = '\0';
    return 1;
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

static int _interval_index_from_value(const char *interval)
{
    char normalized[16];
    size_t i = 0;
    const char *src = interval;

    if (!src || !src[0]) return -1;
    if (src[0] == 'k' || src[0] == 'K') src++;
    while (*src && i + 1 < sizeof(normalized)) {
        normalized[i++] = *src++;
    }
    normalized[i] = '\0';

    for (i = 0; i < N_INTERVALS; i++) {
        if (strcmp(normalized, INTERVALS[i]) == 0) return (int)i;
    }
    return -1;
}

static void _identity_text(char *out, size_t out_n, const char *symbol, const char *chain, const char *tail)
{
    (void)chain;
    (void)tail;
    if (!out || out_n == 0) return;
    snprintf(out, out_n, "%s", symbol && symbol[0] ? symbol : "???");
}

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
/* ─── Back fallback ──────────────────────────────────────────────────────── */
static void _back_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_back_timer = NULL;
    ave_sm_go_back_fallback();  /* prefer context-aware fallback */
}
#endif

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
    lv_obj_set_style_text_font(s_lbl_sym, ave_font_cjk_14(), 0);

    s_lbl_price = lv_label_create(top);
    lv_obj_align(s_lbl_price, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_lbl_price, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_price, &lv_font_montserrat_14, 0);

    s_lbl_change = lv_label_create(top);
    lv_obj_align(s_lbl_change, LV_ALIGN_RIGHT_MID, -6, 0);
    lv_obj_set_style_text_font(s_lbl_change, &lv_font_montserrat_12, 0);

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

    /* Timeframe label stays on chart so top bar remains sym/price/change focused. */
    s_lbl_tf = lv_label_create(s_chart);
    lv_obj_align(s_lbl_tf, LV_ALIGN_TOP_RIGHT, -4, 2);
    lv_obj_set_width(s_lbl_tf, 32);
    lv_label_set_long_mode(s_lbl_tf, LV_LABEL_LONG_CLIP);
    lv_label_set_text(s_lbl_tf, INTERVAL_LBLS[s_interval_idx]);
    lv_obj_set_style_text_color(s_lbl_tf, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_tf, &lv_font_montserrat_12, 0);

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

    /* ── Four-line compact footer stats ──────────────────────────────── */
    s_lbl_stats_row1 = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_stats_row1, 4, 148);
    lv_obj_set_width(s_lbl_stats_row1, 312);
    lv_label_set_long_mode(s_lbl_stats_row1, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_font(s_lbl_stats_row1, &lv_font_montserrat_12, 0);

    s_lbl_stats_row2 = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_stats_row2, 4, 161);
    lv_obj_set_width(s_lbl_stats_row2, 312);
    lv_label_set_long_mode(s_lbl_stats_row2, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_stats_row2, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_stats_row2, &lv_font_montserrat_12, 0);

    s_lbl_stats_row3 = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_stats_row3, 4, 175);
    lv_obj_set_width(s_lbl_stats_row3, 312);
    lv_label_set_long_mode(s_lbl_stats_row3, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_stats_row3, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_stats_row3, &lv_font_montserrat_12, 0);

    s_lbl_stats_row4 = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_stats_row4, FOOTER_X, FOOTER_ROW4_Y);
    lv_obj_set_width(s_lbl_stats_row4, FOOTER_W);
    lv_label_set_long_mode(s_lbl_stats_row4, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_stats_row4, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_stats_row4, &lv_font_montserrat_12, 0);

    /* ── Divider ─────────────────────────────────────────────────────── */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* Position indicator lives on row-4 and right-aligns against the footer edge. */
    s_lbl_pos = lv_label_create(s_screen);
    lv_obj_set_pos(s_lbl_pos, FOOTER_X + FOOTER_W - FOOTER_PAGE_W, FOOTER_ROW4_Y);
    lv_obj_set_width(s_lbl_pos, FOOTER_PAGE_W);
    lv_label_set_long_mode(s_lbl_pos, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(s_lbl_pos, LV_TEXT_ALIGN_RIGHT, 0);
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

    /* Three visible action affordances only; no extra spotlight footer action state. */
    lv_obj_t *slot_b = lv_obj_create(bot);
    lv_obj_set_size(slot_b, 106, 240 - 215);
    lv_obj_set_pos(slot_b, 0, 0);
    lv_obj_set_style_bg_opa(slot_b, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_b, 0, 0);
    lv_obj_set_style_pad_all(slot_b, 0, 0);
    lv_obj_clear_flag(slot_b, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_x = lv_obj_create(bot);
    lv_obj_set_size(slot_x, 106, 240 - 215);
    lv_obj_set_pos(slot_x, 106, 0);
    lv_obj_set_style_bg_opa(slot_x, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_x, 0, 0);
    lv_obj_set_style_pad_all(slot_x, 0, 0);
    lv_obj_clear_flag(slot_x, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *slot_a = lv_obj_create(bot);
    lv_obj_set_size(slot_a, 108, 240 - 215);
    lv_obj_set_pos(slot_a, 212, 0);
    lv_obj_set_style_bg_opa(slot_a, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(slot_a, 0, 0);
    lv_obj_set_style_pad_all(slot_a, 0, 0);
    lv_obj_clear_flag(slot_a, LV_OBJ_FLAG_SCROLLABLE);

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
}

/* ─── Public API ──────────────────────────────────────────────────────────── */

void screen_spotlight_show(const char *json_data)
{
    int is_live = _bool(json_data, "live", 0);
    char incoming_token_id[120] = {0};
    char incoming_chain[20] = {0};
    char interval_value[16] = {0};
    int interval_idx = -1;
    int cursor = -1;
    int total = 0;
    int should_release_loading = 0;

    _str(json_data, "token_id", incoming_token_id, sizeof(incoming_token_id));
    _str(json_data, "chain", incoming_chain, sizeof(incoming_chain));
    if (_str(json_data, "interval", interval_value, sizeof(interval_value))) {
        interval_idx = _interval_index_from_value(interval_value);
    }
    cursor = _int(json_data, "cursor", -1);
    total = _int(json_data, "total", 0);
    should_release_loading = _incoming_spotlight_releases_loading_guard(
        is_live,
        incoming_token_id,
        incoming_chain,
        interval_idx,
        cursor,
        total
    );

    if (!s_screen) _build();

    if (should_release_loading) _clear_loading_guard();

    if (interval_idx >= 0) {
        s_interval_idx = interval_idx;
    } else if (!is_live) {
        s_interval_idx = 3;  /* default 1H for fresh payloads that omit interval */
    }
    lv_label_set_text(s_lbl_tf, INTERVAL_LBLS[s_interval_idx]);

    lv_screen_load(s_screen);

    /* Parse basic fields */
    char sym[24]={0}, price[24]={0}, change[20]={0}, risk_lvl[12]={0};
    char holders[20]={0}, liq[20]={0}, cmin[16]={0}, cmax[16]={0};
    char vol24h[20]={0}, mcap[20]={0}, top100[20]={0}, ca_compact[32]={0};
    char contract_addr[160]={0}, mint_addr[160]={0};
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
    _field_text(json_data, "holders",   holders, sizeof(holders));
    _field_text(json_data, "liquidity", liq,     sizeof(liq));
    _field_text(json_data, "volume_24h", vol24h, sizeof(vol24h));
    _field_text(json_data, "market_cap", mcap,   sizeof(mcap));
    _field_text(json_data, "top100_concentration", top100, sizeof(top100));
    _field_text(json_data, "contract", contract_addr, sizeof(contract_addr));
    if (!contract_addr[0]) {
        _field_text(json_data, "contract_address", contract_addr, sizeof(contract_addr));
    }
    _field_text(json_data, "mint", mint_addr, sizeof(mint_addr));
    _str(json_data, "token_id",  s_token_id, sizeof(s_token_id));
    _str(json_data, "chain",     s_chain,    sizeof(s_chain));
    _str(json_data, "contract_tail", s_contract_tail, sizeof(s_contract_tail));
    _str(json_data, "source_tag", s_source_tag, sizeof(s_source_tag));
    _format_contract_short(contract_addr, mint_addr, s_token_id, ca_compact, sizeof(ca_compact));
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
    {
#if defined(AVE_SPOTLIGHT_SHOW_ONLY)
        lv_label_set_text(s_lbl_price, price[0] ? price : "$0");
#else
        char price_compact[32] = {0};
        ave_fmt_price_text(price_compact, sizeof(price_compact), price[0] ? price : "$0");
        lv_label_set_text(s_lbl_price, price_compact);
#endif
    }
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
    lv_label_set_text(s_lbl_t_start, ct_start[0] ? ct_start : "");
    lv_label_set_text(s_lbl_t_mid,   ct_mid[0] ? ct_mid : "");
    lv_label_set_text(s_lbl_t_end, ct_end[0] ? ct_end : "now");

    /* Footer line 1: Risk | Mint | Freeze */
    const char *risk_text = NULL;
    lv_color_t risk_color = COLOR_GRAY;
    if (is_honeypot) {
        risk_text = "HONEYPOT";
        risk_color = COLOR_RED;
    } else {
        risk_text = risk_lvl[0] ? risk_lvl : "SAFE";
        if ((strcmp(risk_text, "LOW") == 0) || (strcmp(risk_text, "SAFE") == 0)) {
            risk_color = COLOR_GREEN;
        } else if (strcmp(risk_text, "UNKNOWN") == 0) {
            risk_color = COLOR_GRAY;
        } else {
            risk_color = COLOR_ORANGE;
        }
    }
    lv_label_set_text_fmt(
        s_lbl_stats_row1,
        "Risk:%s | Mint:%s | Freeze:%s",
        risk_text,
        is_mintable ? "YES" : "NO",
        is_freezable ? "YES" : "NO"
    );
    lv_obj_set_style_text_color(s_lbl_stats_row1, risk_color, 0);

    /* Footer line 2-4: Vol/Liq/Mcap, Holders/Top100, and compact CA + page marker. */
    lv_label_set_text_fmt(
        s_lbl_stats_row2,
        "Vol24h:%s | Liq:%s | Mcap:%s",
        vol24h[0] ? vol24h : "N/A",
        liq[0] ? liq : "N/A",
        mcap[0] ? mcap : "N/A"
    );
    lv_label_set_text_fmt(
        s_lbl_stats_row3,
        "Holders:%s | Top100:%s",
        holders[0] ? holders : "N/A",
        top100[0] ? top100 : "N/A"
    );
    lv_label_set_text_fmt(
        s_lbl_stats_row4,
        "CA:%s",
        ca_compact
    );

    /* Feed position indicator (present only when navigating feed list) */
    s_feed_cursor = cursor;
    s_feed_total = total;
    if (cursor >= 0 && total > 1) {
        lv_obj_set_width(s_lbl_stats_row4, FOOTER_W - FOOTER_PAGE_W - FOOTER_ROW4_GAP);
        lv_obj_set_pos(s_lbl_pos, FOOTER_X + FOOTER_W - FOOTER_PAGE_W, FOOTER_ROW4_Y);
        lv_obj_set_width(s_lbl_pos, FOOTER_PAGE_W);
        lv_label_set_text_fmt(s_lbl_pos, "<%d/%d>", cursor + 1, total);
    } else {
        lv_obj_set_width(s_lbl_stats_row4, FOOTER_W);
        lv_label_set_text(s_lbl_pos, "");
    }
}

#if !defined(AVE_SPOTLIGHT_SHOW_ONLY)
void screen_spotlight_key(int key)
{
    if (key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
        screen_spotlight_cancel_back_timer();
        s_back_timer = lv_timer_create(_back_timeout_cb, 3000, NULL);
        lv_timer_set_repeat_count(s_back_timer, 1);
    } else if (key == AVE_KEY_LEFT) {
        _arm_loading_guard(SPOTLIGHT_LOADING_REASON_FEED_NAV, s_token_id, s_chain, -1, -1);
        ave_send_json("{\"type\":\"key_action\",\"action\":\"feed_prev\"}");
        printf("[SPOTLIGHT] feed_prev\n");
    } else if (key == AVE_KEY_RIGHT) {
        _arm_loading_guard(SPOTLIGHT_LOADING_REASON_FEED_NAV, s_token_id, s_chain, -1, 1);
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
        s_interval_idx = (s_interval_idx + 1) % N_INTERVALS;
        _arm_loading_guard(
            SPOTLIGHT_LOADING_REASON_INTERVAL,
            s_token_id,
            s_chain,
            s_interval_idx,
            0
        );
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
        s_interval_idx = (s_interval_idx - 1 + N_INTERVALS) % N_INTERVALS;
        _arm_loading_guard(
            SPOTLIGHT_LOADING_REASON_INTERVAL,
            s_token_id,
            s_chain,
            s_interval_idx,
            0
        );
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
#else
void screen_spotlight_key(int key)
{
    (void)key;
}

int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
#endif
