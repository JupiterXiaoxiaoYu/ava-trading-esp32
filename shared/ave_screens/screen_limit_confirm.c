/**
 * @file screen_limit_confirm.c
 * @brief LIMIT CONFIRM screen — countdown confirmation for limit orders.
 *
 * Layout (320x240 landscape):
 *   y=  0..21   top bar: "[PAPER] LIMIT BUY"
 *   y= 28       asset row
 *   y= 50       target + size
 *   y= 70       current + distance
 *   y= 88       expiry + trade id
 *   y=110..130  countdown bar (320x20)
 *   y=135       countdown label
 *   y=215..240  divider + bottom key labels
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

void screen_result_show(const char *json_data);

/* ---- Colors ------------------------------------------------------------ */
#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_SOL     lv_color_hex(0x9945FF)
#define COLOR_ETH     lv_color_hex(0x627EEA)
#define COLOR_BSC     lv_color_hex(0xF3BA2F)
#define COLOR_BASE    lv_color_hex(0x0052FF)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)

/* ---- JSON helper ------------------------------------------------------- */
static int _getf(const char *j, const char *k, char *o, int n)
{
    char nd[64];
    snprintf(nd, 64, "\"%s\"", k);
    const char *p = strstr(j, nd);
    if (!p) return 0;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;
    return ave_json_decode_quoted(p, o, (size_t)n, NULL);
}

static int _get_int(const char *j, const char *k, int def)
{
    char buf[32] = {0};
    if (_getf(j, k, buf, sizeof(buf))) return atoi(buf);
    /* try bare number */
    char nd[64];
    snprintf(nd, 64, "\"%s\"", k);
    const char *p = strstr(j, nd);
    if (!p) return def;
    p += strlen(nd);
    while (*p == ' ' || *p == ':') p++;
    if ((*p >= '0' && *p <= '9') || *p == '-') return atoi(p);
    return def;
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

static const char *_chain_short(const char *chain)
{
    if (!chain || !chain[0]) return "";
    if (strncmp(chain, "solana", 6) == 0) return "SOL";
    if (strncmp(chain, "eth", 3) == 0) return "ETH";
    if (strncmp(chain, "bsc", 3) == 0) return "BSC";
    if (strncmp(chain, "base", 4) == 0) return "BASE";

    static char buf[8];
    int i = 0;
    while (chain[i] && i < 4) {
        char c = chain[i];
        buf[i++] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
    }
    buf[i] = '\0';
    return buf;
}

static const char *_chain_color_hex(const char *chain)
{
    if (!chain) return "9E9E9E";
    if (strncmp(chain, "solana", 6) == 0) return "9945FF";
    if (strncmp(chain, "eth", 3) == 0) return "627EEA";
    if (strncmp(chain, "bsc", 3) == 0) return "F3BA2F";
    if (strncmp(chain, "base", 4) == 0) return "0052FF";
    return "9E9E9E";
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
        "\"error\":\"Confirmation timed out.\","
        "\"subtitle\":\"Nothing was executed.\","
        "\"explain_state\":\"confirm_timeout\"}"
    );
}

/* ---- LVGL objects ------------------------------------------------------ */
static lv_obj_t   *s_screen      = NULL;
static lv_obj_t   *s_lbl_top     = NULL;
static lv_obj_t   *s_lbl_asset   = NULL;
static lv_obj_t   *s_lbl_contract = NULL;
static lv_obj_t   *s_lbl_target  = NULL;
static lv_obj_t   *s_lbl_current = NULL;
static lv_obj_t   *s_lbl_meta    = NULL;
static lv_obj_t   *s_bar         = NULL;
static lv_obj_t   *s_lbl_count   = NULL;
static lv_obj_t   *s_lbl_left    = NULL;
static lv_obj_t   *s_lbl_right   = NULL;

static lv_timer_t *s_timer       = NULL;
static lv_timer_t *s_ack_timer   = NULL;
static int         s_seconds     = 10;
static int         s_total       = 10;
static char        s_trade_id[80] = {0};
static uint32_t    s_show_ts     = 0;
static int         s_submitted   = 0;

void screen_limit_confirm_cancel_timers(void)
{
    if (s_timer) {
        lv_timer_del(s_timer);
        s_timer = NULL;
    }
    if (s_ack_timer) {
        lv_timer_del(s_ack_timer);
        s_ack_timer = NULL;
    }
    s_submitted = 0;
}

/* ---- Ack watchdog callback --------------------------------------------- */
static void _ack_timeout_cb(lv_timer_t *t)
{
    (void)t;
    s_ack_timer = NULL;
    s_submitted = 0;
    _show_ack_timeout_notice();
}

/* ---- Countdown helpers ------------------------------------------------- */
static lv_color_t _bar_color(int pct)
{
    if (pct > 50) return COLOR_GREEN;
    if (pct > 20) return COLOR_ORANGE;
    return COLOR_RED;
}

static void _update_countdown(void)
{
    int pct = (s_total > 0) ? (s_seconds * 100 / s_total) : 0;
    lv_bar_set_value(s_bar, pct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_bar, _bar_color(pct), LV_PART_INDICATOR);

    char buf[32];
    snprintf(buf, sizeof(buf), "%ds", s_seconds);
    lv_label_set_text(s_lbl_count, buf);
}

static void _tick_cb(lv_timer_t *t)
{
    (void)t;
    s_seconds--;
    if (s_seconds <= 0) {
        lv_timer_del(s_timer);
        s_timer = NULL;
        if (s_ack_timer) { lv_timer_del(s_ack_timer); s_ack_timer = NULL; }
        s_submitted = 0;
        printf("[LIMIT_CONFIRM] TIMEOUT trade_id=%s\n", s_trade_id);
        _show_confirm_timeout_result();
        return;
    }
    _update_countdown();
}

/* ---- Build layout ------------------------------------------------------ */
static void _build_screen(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_set_size(s_screen, 320, 240);

    /* Top bar (h=22) */
    lv_obj_t *bar = lv_obj_create(s_screen);
    lv_obj_set_size(bar, 320, 22);
    lv_obj_align(bar, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_bg_color(bar, COLOR_BAR, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_pad_all(bar, 0, 0);

    s_lbl_top = lv_label_create(bar);
    lv_obj_align(s_lbl_top, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_lbl_top, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_top, ave_font_cjk_14(), 0);

    /* Asset row */
    s_lbl_asset = lv_label_create(s_screen);
    lv_obj_align(s_lbl_asset, LV_ALIGN_TOP_LEFT, 8, 28);
    lv_obj_set_width(s_lbl_asset, 304);
    lv_label_set_long_mode(s_lbl_asset, LV_LABEL_LONG_CLIP);
    lv_label_set_recolor(s_lbl_asset, true);
    lv_obj_set_style_text_color(s_lbl_asset, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_asset, ave_font_cjk_16(), 0);
    lv_obj_set_style_text_align(s_lbl_asset, LV_TEXT_ALIGN_LEFT, 0);

    /* Contract row */
    s_lbl_contract = lv_label_create(s_screen);
    lv_obj_align(s_lbl_contract, LV_ALIGN_TOP_LEFT, 8, 48);
    lv_obj_set_width(s_lbl_contract, 304);
    lv_label_set_long_mode(s_lbl_contract, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_obj_set_style_text_color(s_lbl_contract, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_contract, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_contract, LV_TEXT_ALIGN_LEFT, 0);

    /* Target price */
    s_lbl_target = lv_label_create(s_screen);
    lv_obj_align(s_lbl_target, LV_ALIGN_TOP_LEFT, 8, 68);
    lv_obj_set_width(s_lbl_target, 304);
    lv_label_set_long_mode(s_lbl_target, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_target, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_target, &lv_font_montserrat_14, 0);

    /* Current price + distance */
    s_lbl_current = lv_label_create(s_screen);
    lv_obj_align(s_lbl_current, LV_ALIGN_TOP_LEFT, 8, 88);
    lv_obj_set_width(s_lbl_current, 304);
    lv_label_set_long_mode(s_lbl_current, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_current, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_current, &lv_font_montserrat_12, 0);

    /* Expiry + trade id */
    s_lbl_meta = lv_label_create(s_screen);
    lv_obj_align(s_lbl_meta, LV_ALIGN_TOP_LEFT, 8, 106);
    lv_obj_set_width(s_lbl_meta, 304);
    lv_label_set_long_mode(s_lbl_meta, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_meta, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_meta, &lv_font_montserrat_12, 0);

    /* Countdown bar */
    s_bar = lv_bar_create(s_screen);
    lv_obj_set_size(s_bar, 320, 20);
    lv_obj_align(s_bar, LV_ALIGN_TOP_LEFT, 0, 128);
    lv_bar_set_range(s_bar, 0, 100);
    lv_obj_set_style_bg_color(s_bar, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(s_bar, 0, 0);
    lv_obj_set_style_radius(s_bar, 0, 0);
    lv_obj_set_style_radius(s_bar, 0, LV_PART_INDICATOR);

    /* Countdown label */
    s_lbl_count = lv_label_create(s_screen);
    lv_obj_align(s_lbl_count, LV_ALIGN_TOP_MID, 0, 154);
    lv_obj_set_style_text_color(s_lbl_count, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_count, &lv_font_montserrat_14, 0);

    /* Divider above bottom bar */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* Bottom labels */
    s_lbl_left = lv_label_create(s_screen);
    lv_obj_align(s_lbl_left, LV_ALIGN_BOTTOM_LEFT, 8, -4);
    lv_label_set_text(s_lbl_left, "[B] CANCEL");
    lv_obj_set_style_text_color(s_lbl_left, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_left, &lv_font_montserrat_12, 0);

    s_lbl_right = lv_label_create(s_screen);
    lv_obj_align(s_lbl_right, LV_ALIGN_BOTTOM_RIGHT, -8, -4);
    lv_label_set_text(s_lbl_right, "SET ORDER [A]");
    lv_obj_set_style_text_color(s_lbl_right, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_right, &lv_font_montserrat_12, 0);
}

/* ---- Public API -------------------------------------------------------- */
void screen_limit_confirm_show(const char *json_data)
{
    if (!s_screen) _build_screen();

    /* Stop previous timers */
    screen_limit_confirm_cancel_timers();
    s_submitted = 0;

    /* Parse fields */
    char action[32] = {0}, symbol[24] = {0}, limit_price[32] = {0}, mode_label[16] = {0};
    char current_price[32] = {0}, distance[16] = {0}, amount[32] = {0};
    char chain[16] = {0}, token_id[96] = {0};
    int  expire_hours = 24;

    _getf(json_data, "action",        action,        sizeof(action));
    _getf(json_data, "symbol",        symbol,        sizeof(symbol));
    _getf(json_data, "mode_label",    mode_label,    sizeof(mode_label));
    _getf(json_data, "limit_price",   limit_price,   sizeof(limit_price));
    _getf(json_data, "current_price", current_price, sizeof(current_price));
    _getf(json_data, "distance",      distance,      sizeof(distance));
    _getf(json_data, "amount_native", amount,        sizeof(amount));
    s_trade_id[0] = '\0';
    _getf(json_data, "trade_id",      s_trade_id,    sizeof(s_trade_id));
    _getf(json_data, "chain",         chain,         sizeof(chain));
    _getf(json_data, "token_id",      token_id,      sizeof(token_id));
    expire_hours = _get_int(json_data, "expire_hours", 24);
    s_total   = _get_int(json_data, "timeout_sec", 10);
    s_seconds = s_total;

    /* Top bar text */
    char top[96];
    char identity[96];
    char contract[112];
    const char *chain_short = _chain_short(chain);
    _buf_reset(identity, sizeof(identity));
    _buf_append(identity, sizeof(identity), symbol);
    if (chain_short[0]) {
        _buf_append(identity, sizeof(identity), "  ");
        _buf_append(identity, sizeof(identity), "#");
        _buf_append(identity, sizeof(identity), _chain_color_hex(chain));
        _buf_append(identity, sizeof(identity), " ");
        _buf_append(identity, sizeof(identity), chain_short);
        _buf_append(identity, sizeof(identity), "#");
    }
    _buf_reset(top, sizeof(top));
    if (mode_label[0]) {
        _buf_append(top, sizeof(top), "[");
        _buf_append(top, sizeof(top), mode_label);
        _buf_append(top, sizeof(top), "] ");
    }
    _buf_append(top, sizeof(top), action);
    lv_label_set_text(s_lbl_top, top);
    lv_label_set_text(s_lbl_asset, identity[0] ? identity : "TOKEN");
    snprintf(contract, sizeof(contract), "CA: %s", token_id[0] ? token_id : "--");
    lv_label_set_text(s_lbl_contract, contract);

    /* Target price */
    char buf[80];
    snprintf(buf, sizeof(buf), "Target %s   Size %s",
             limit_price[0] ? limit_price : "--",
             amount[0] ? amount : "--");
    lv_label_set_text(s_lbl_target, buf);

    /* Current price + distance */
    snprintf(buf, sizeof(buf), "Current %s   Distance %s",
             current_price[0] ? current_price : "--",
             distance[0] ? distance : "--");
    lv_label_set_text(s_lbl_current, buf);

    /* Expiry + trade id */
    snprintf(buf, sizeof(buf), "Expires %dh   Trade ID %.20s",
             expire_hours,
             s_trade_id[0] ? s_trade_id : "--");
    lv_label_set_text(s_lbl_meta, buf);

    /* Init countdown */
    _update_countdown();

    lv_screen_load(s_screen);

    s_timer = lv_timer_create(_tick_cb, 1000, NULL);
    s_show_ts = lv_tick_get();
}

void screen_limit_confirm_key(int key)
{
    if (s_submitted && (key == AVE_KEY_A || key == AVE_KEY_B || key == AVE_KEY_Y)) {
        return;
    }

    if (key == AVE_KEY_B) {
        screen_limit_confirm_cancel_timers();
        {
            char msg[192];
            snprintf(msg, sizeof(msg),
                     "{\"type\":\"trade_action\",\"action\":\"cancel\",\"trade_id\":\"%s\"}",
                     s_trade_id);
            ave_send_json(msg);
            printf("[LIMIT_CONFIRM] Cancelled trade_id=%s\n", s_trade_id);
        }
    } else if (key == AVE_KEY_A) {
        if ((lv_tick_get() - s_show_ts) < 500) return;  /* Match CONFIRM anti-mis-tap cooldown */
        if (s_timer) { lv_timer_del(s_timer); s_timer = NULL; }
        {
            char msg[192];
            snprintf(msg, sizeof(msg),
                     "{\"type\":\"trade_action\",\"action\":\"confirm\",\"trade_id\":\"%s\"}",
                     s_trade_id);
            ave_send_json(msg);
            printf("[LIMIT_CONFIRM] Order set -> trade_id=%s\n", s_trade_id);
        }
        s_submitted = 1;
        /* Arm 15-second watchdog; fires if server never responds */
        if (s_ack_timer) { lv_timer_del(s_ack_timer); s_ack_timer = NULL; }
        s_ack_timer = lv_timer_create(_ack_timeout_cb, 15000, NULL);
        lv_timer_set_repeat_count(s_ack_timer, 1);
    }
}

int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    int n;

    if (!out || out_n == 0) return 0;

    n = snprintf(
        out,
        out_n,
        "%s",
        s_submitted
            ? "{\"screen\":\"limit_confirm\",\"awaiting_ack\":true}"
            : "{\"screen\":\"limit_confirm\"}"
    );
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
