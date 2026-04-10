/**
 * @file screen_confirm.c
 * @brief CONFIRM screen — countdown timer for trade confirmation.
 *
 * Layout (320x240 landscape):
 *   y=  0..22   top bar: "BUY  BONK  0.5 SOL  ~ $71.15"  (14px)
 *   y= 26       TP/SL/Slip row  (12px, gray)
 *   y= 44       trade_id  (12px, gray)
 *   y= 70..90   countdown bar (320x20), green->orange->red
 *   y= 95       countdown label "X.Xs"  (14px, centered)
 *   y=215..240   divider + bottom bar: "< CANCEL"  "CONFIRM >"
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

void screen_result_show(const char *json_data);

/* ─── Colors ────────────────────────────────────────────────────────────── */
#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)

/* ─── LVGL objects ──────────────────────────────────────────────────────── */
static lv_obj_t   *s_screen       = NULL;
static lv_obj_t   *s_lbl_top      = NULL;
static lv_obj_t   *s_lbl_params   = NULL;
static lv_obj_t   *s_lbl_trade_id = NULL;
static lv_obj_t   *s_bar           = NULL;
static lv_obj_t   *s_lbl_countdown = NULL;
static lv_obj_t   *s_lbl_left     = NULL;
static lv_obj_t   *s_lbl_right    = NULL;

static lv_timer_t *s_timer        = NULL;
static lv_timer_t *s_ack_timer    = NULL;
static int         s_remaining_ms = 0;
static int         s_timeout_ms   = 10000;
static char        s_trade_id[80] = {0};
static uint32_t    s_show_ts      = 0;

void screen_confirm_cancel_timers(void)
{
    if (s_timer) {
        lv_timer_del(s_timer);
        s_timer = NULL;
    }
    if (s_ack_timer) {
        lv_timer_del(s_ack_timer);
        s_ack_timer = NULL;
    }
}

/* ─── Simple JSON helpers ───────────────────────────────────────────────── */
static int _get_str(const char *json, const char *key, char *out, int n)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return 0;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, out, (size_t)n, NULL);
}

static int _get_int(const char *json, const char *key, int def)
{
    char val[32] = {0};
    if (_get_str(json, key, val, sizeof(val))) return atoi(val);
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return def;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if ((*p >= '0' && *p <= '9') || *p == '-') return atoi(p);
    return def;
}

static int _get_optional_int(const char *json, const char *key, int *out)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return 0;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p == 'n') return 0; /* explicit null */
    if ((*p >= '0' && *p <= '9') || *p == '-') {
        *out = atoi(p);
        return 1;
    }
    if (*p == '"') {
        char val[32] = {0};
        if (!ave_json_decode_quoted(p, val, sizeof(val), NULL)) return 0;
        *out = atoi(val);
        return 1;
    }
    return 0;
}

static void _buf_reset(char *buf, size_t buf_n)
{
    if (!buf || buf_n == 0) return;
    buf[0] = '\0';
}

static void _buf_append(char *buf, size_t buf_n, const char *text)
{
    size_t used;

    if (!buf || buf_n == 0 || !text) return;
    used = strlen(buf);
    while (used + 1 < buf_n && *text) {
        buf[used++] = *text++;
    }
    buf[used] = '\0';
}

static int _is_action(const char *action, const char *expected)
{
    while (*action && *expected) {
        char a = *action;
        char b = *expected;
        if (a >= 'a' && a <= 'z') a = (char)(a - 'a' + 'A');
        if (b >= 'a' && b <= 'z') b = (char)(b - 'a' + 'A');
        if (a != b) return 0;
        action++;
        expected++;
    }
    return (*action == '\0' && *expected == '\0');
}

static double _get_float(const char *json, const char *key, double def)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return def;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if ((*p >= '0' && *p <= '9') || *p == '-' || *p == '.') return atof(p);
    return def;
}

static void _show_ack_timeout_notice(void)
{
    ave_sm_go_to_feed();
    screen_notify_show(
        "{\"level\":\"warning\",\"title\":\"Still Pending\","
        "\"body\":\"We did not receive a final confirmation yet.\","
        "\"subtitle\":\"We did not receive a final confirmation yet.\","
        "\"explain_state\":\"ack_timeout\"}"
    );
}

static void _show_confirm_timeout_result(void)
{
    screen_result_show(
        "{\"success\":false,\"title\":\"Trade Cancelled\","
        "\"error\":\"Confirmation timed out. Nothing was executed.\","
        "\"subtitle\":\"Confirmation timed out. Nothing was executed.\","
        "\"explain_state\":\"confirm_timeout\"}"
    );
}

/* ─── Ack watchdog callback ─────────────────────────────────────────────── */
static void _ack_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_ack_timer = NULL;
    _show_ack_timeout_notice();
}

/* ─── Timer callback ────────────────────────────────────────────────────── */
static void _countdown_cb(lv_timer_t *t)
{
    (void)t;
    /* Ack watchdog should not be running during countdown, but guard anyway */
    if (s_ack_timer) { lv_timer_del(s_ack_timer); s_ack_timer = NULL; }
    s_remaining_ms -= 100;
    if (s_remaining_ms <= 0) {
        s_remaining_ms = 0;
        if (s_timer) { lv_timer_del(s_timer); s_timer = NULL; }
        printf("[CONFIRM] TIMEOUT trade_id=%s\n", s_trade_id);
        _show_confirm_timeout_result();
        return;
    }

    /* Update bar value (0-100), scaled to initial timeout */
    int bar_val = (s_remaining_ms * 100) / s_timeout_ms;
    lv_bar_set_value(s_bar, bar_val, LV_ANIM_OFF);

    /* Bar color based on remaining time */
    lv_color_t c;
    if (s_remaining_ms > 5000) c = COLOR_GREEN;
    else if (s_remaining_ms > 2000) c = COLOR_ORANGE;
    else c = COLOR_RED;
    lv_obj_set_style_bg_color(s_bar, c, LV_PART_INDICATOR);

    /* Update countdown label */
    char buf[16];
    snprintf(buf, sizeof(buf), "%d.%ds", s_remaining_ms / 1000, (s_remaining_ms % 1000) / 100);
    lv_label_set_text(s_lbl_countdown, buf);
}

/* ─── Build screen ──────────────────────────────────────────────────────── */
static void _build_screen(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_set_size(s_screen, 320, 240);

    /* ── Top bar (h=22) ─────────────────────────────────────────────────── */
    lv_obj_t *top_bar = lv_obj_create(s_screen);
    lv_obj_set_size(top_bar, 320, 22);
    lv_obj_align(top_bar, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_color(top_bar, COLOR_BAR, 0);
    lv_obj_set_style_border_width(top_bar, 0, 0);
    lv_obj_set_style_pad_all(top_bar, 0, 0);

    s_lbl_top = lv_label_create(top_bar);
    lv_obj_align(s_lbl_top, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_lbl_top, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_top, &lv_font_montserrat_14, 0);

    /* ── TP / SL / Slippage row ─────────────────────────────────────────── */
    s_lbl_params = lv_label_create(s_screen);
    lv_obj_align(s_lbl_params, LV_ALIGN_TOP_MID, 0, 26);
    lv_obj_set_style_text_color(s_lbl_params, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_params, &lv_font_montserrat_12, 0);

    /* ── Trade ID ───────────────────────────────────────────────────────── */
    s_lbl_trade_id = lv_label_create(s_screen);
    lv_obj_align(s_lbl_trade_id, LV_ALIGN_TOP_MID, 0, 44);
    lv_obj_set_style_text_color(s_lbl_trade_id, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_trade_id, &lv_font_montserrat_12, 0);

    /* ── Countdown bar ──────────────────────────────────────────────────── */
    s_bar = lv_bar_create(s_screen);
    lv_obj_set_size(s_bar, 300, 20);
    lv_obj_align(s_bar, LV_ALIGN_TOP_MID, 0, 70);
    lv_bar_set_range(s_bar, 0, 100);
    lv_bar_set_value(s_bar, 100, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_bar, COLOR_DIVIDER, 0);          /* track color */
    lv_obj_set_style_bg_color(s_bar, COLOR_GREEN, LV_PART_INDICATOR);

    /* ── Countdown label ────────────────────────────────────────────────── */
    s_lbl_countdown = lv_label_create(s_screen);
    lv_obj_align(s_lbl_countdown, LV_ALIGN_TOP_MID, 0, 95);
    lv_obj_set_style_text_color(s_lbl_countdown, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_countdown, &lv_font_montserrat_14, 0);

    /* ── Divider above bottom bar ───────────────────────────────────────── */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* ── Bottom bar ─────────────────────────────────────────────────────── */
    s_lbl_left = lv_label_create(s_screen);
    lv_obj_align(s_lbl_left, LV_ALIGN_BOTTOM_LEFT, 8, -4);
    lv_label_set_text(s_lbl_left, "[B] CANCEL");
    lv_obj_set_style_text_color(s_lbl_left, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_left, &lv_font_montserrat_12, 0);

    s_lbl_right = lv_label_create(s_screen);
    lv_obj_align(s_lbl_right, LV_ALIGN_BOTTOM_RIGHT, -8, -4);
    lv_label_set_text(s_lbl_right, "CONFIRM [A]");
    lv_obj_set_style_text_color(s_lbl_right, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_right, &lv_font_montserrat_12, 0);
}

/* ─── Public API ────────────────────────────────────────────────────────── */

void screen_confirm_show(const char *json_data)
{
    if (!s_screen) {
        _build_screen();
    }

    /* Stop any existing timers */
    screen_confirm_cancel_timers();

    /* Parse fields */
    char action[16] = {0}, symbol[24] = {0};
    char amount_native[32] = {0}, amount_usd[32] = {0};
    char out_amount[32] = {0};
    char chain[16] = {0}, contract_tail[12] = {0};
    s_trade_id[0] = '\0';
    _get_str(json_data, "trade_id",      s_trade_id,     sizeof(s_trade_id));
    _get_str(json_data, "action",        action,         sizeof(action));
    _get_str(json_data, "symbol",        symbol,         sizeof(symbol));
    _get_str(json_data, "amount_native", amount_native,  sizeof(amount_native));
    _get_str(json_data, "amount_usd",    amount_usd,     sizeof(amount_usd));
    _get_str(json_data, "out_amount",    out_amount,     sizeof(out_amount));
    _get_str(json_data, "chain",         chain,          sizeof(chain));
    _get_str(json_data, "contract_tail", contract_tail,  sizeof(contract_tail));

    int tp_pct = 0, sl_pct = 0;
    int has_tp = _get_optional_int(json_data, "tp_pct", &tp_pct);
    int has_sl = _get_optional_int(json_data, "sl_pct", &sl_pct);
    double slippage = _get_float(json_data, "slippage_pct", 1.0);
    int timeout_sec = _get_int(json_data,   "timeout_sec",  10);

    /* Top bar text */
    char top_buf[128];
    char identity_buf[48];
    _buf_reset(identity_buf, sizeof(identity_buf));
    _buf_append(identity_buf, sizeof(identity_buf), symbol);
    if (chain[0]) {
        _buf_append(identity_buf, sizeof(identity_buf), " ");
        _buf_append(identity_buf, sizeof(identity_buf), chain);
    }
    if (contract_tail[0]) {
        _buf_append(identity_buf, sizeof(identity_buf), " *");
        _buf_append(identity_buf, sizeof(identity_buf), contract_tail);
    }
    _buf_reset(top_buf, sizeof(top_buf));
    _buf_append(top_buf, sizeof(top_buf), action);
    if (strlen(out_amount) > 0) {
        /* Exact quote available: "BUY <out_amount> BONK  0.1 SOL" */
        _buf_append(top_buf, sizeof(top_buf), "  ");
        _buf_append(top_buf, sizeof(top_buf), out_amount);
        _buf_append(top_buf, sizeof(top_buf), " ");
        _buf_append(top_buf, sizeof(top_buf), identity_buf);
        _buf_append(top_buf, sizeof(top_buf), "  ");
        _buf_append(top_buf, sizeof(top_buf), amount_native);
    } else {
        /* Fallback: "BUY  BONK  0.1 SOL  ≈ $15.00" */
        _buf_append(top_buf, sizeof(top_buf), "  ");
        _buf_append(top_buf, sizeof(top_buf), identity_buf);
        _buf_append(top_buf, sizeof(top_buf), "  ");
        _buf_append(top_buf, sizeof(top_buf), amount_native);
        _buf_append(top_buf, sizeof(top_buf), "  ");
        _buf_append(top_buf, sizeof(top_buf), amount_usd);
    }
    lv_label_set_text(s_lbl_top, top_buf);

    /* Params row */
    char params_buf[96];
    const int no_tp_sl = (_is_action(action, "SELL") || _is_action(action, "CANCEL"));
    char tp_buf[16], sl_buf[16];
    if (!no_tp_sl && has_tp) snprintf(tp_buf, sizeof(tp_buf), "+%d%%", tp_pct);
    else snprintf(tp_buf, sizeof(tp_buf), "--");
    if (!no_tp_sl && has_sl) snprintf(sl_buf, sizeof(sl_buf), "-%d%%", sl_pct);
    else snprintf(sl_buf, sizeof(sl_buf), "--");
    snprintf(params_buf, sizeof(params_buf), "TP: %s   SL: %s   Slip: %.1f%%", tp_buf, sl_buf, slippage);
    lv_label_set_text(s_lbl_params, params_buf);

    /* Trade ID */
    char tid_buf[96];
    snprintf(tid_buf, sizeof(tid_buf), "trade_id: %s", s_trade_id);
    lv_label_set_text(s_lbl_trade_id, tid_buf);

    /* Initialize countdown */
    s_timeout_ms   = timeout_sec * 1000;
    s_remaining_ms = s_timeout_ms;
    int bar_val = 100;
    lv_bar_set_value(s_bar, bar_val, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_bar, COLOR_GREEN, LV_PART_INDICATOR);

    char cd_buf[16];
    snprintf(cd_buf, sizeof(cd_buf), "%d.0s", timeout_sec);
    lv_label_set_text(s_lbl_countdown, cd_buf);

    lv_screen_load(s_screen);

    /* Start countdown timer */
    s_timer = lv_timer_create(_countdown_cb, 100, NULL);

    s_show_ts = lv_tick_get();
}

void screen_confirm_key(int key)
{
    if (key == AVE_KEY_B) {
        /* Cancel — notify server */
        screen_confirm_cancel_timers();
        {
            char msg[192];
            snprintf(msg, sizeof(msg),
                     "{\"type\":\"trade_action\",\"action\":\"cancel\",\"trade_id\":\"%s\"}",
                     s_trade_id);
            ave_send_json(msg);
            printf("[CONFIRM] CANCEL trade_id=%s\n", s_trade_id);
        }
        ave_sm_go_to_feed();
    } else if (key == AVE_KEY_A) {
        if ((lv_tick_get() - s_show_ts) < 500) return;  /* 500ms cooldown, prevent rapid tap-through */
        /* Confirm — notify server, then arm ack watchdog */
        if (s_timer) { lv_timer_del(s_timer); s_timer = NULL; }
        {
            char msg[192];
            snprintf(msg, sizeof(msg),
                     "{\"type\":\"trade_action\",\"action\":\"confirm\",\"trade_id\":\"%s\"}",
                     s_trade_id);
            ave_send_json(msg);
            printf("[CONFIRM] CONFIRMED trade_id=%s\n", s_trade_id);
        }
        /* Arm 15-second watchdog; fires if server never responds */
        if (s_ack_timer) { lv_timer_del(s_ack_timer); s_ack_timer = NULL; }
        s_ack_timer = lv_timer_create(_ack_timeout_cb, 15000, NULL);
        lv_timer_set_repeat_count(s_ack_timer, 1);
    }
}

int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    int n;

    if (!out || out_n == 0) return 0;

    n = snprintf(out, out_n, "%s", "{\"screen\":\"confirm\"}");
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
