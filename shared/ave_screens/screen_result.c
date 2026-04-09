/**
 * @file screen_result.c
 * @brief RESULT screen — trade success/failure display (manual dismiss only).
 *
 * Layout (320x240 landscape, centered vertically):
 *   Large icon: checkmark (success, green) or X (fail, red)  font=32
 *   Title: "Bought!" or "Trade Failed"  font=24
 *   Line 1: amount or error message  font=16
 *   Line 2: TP/SL (success only)  font=12, gray
 *   Line 3: TX id (success only)  font=12, gray
 *   y=215~240: bottom bar "press any key"
 */
#include "ave_screen_manager.h"
#include "ave_transport.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ─── Colors ────────────────────────────────────────────────────────────── */
#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)

/* ─── LVGL objects ──────────────────────────────────────────────────────── */
static lv_obj_t   *s_screen     = NULL;
static lv_obj_t   *s_lbl_icon   = NULL;
static lv_obj_t   *s_lbl_title  = NULL;
static lv_obj_t   *s_lbl_line1  = NULL;
static lv_obj_t   *s_lbl_line2  = NULL;
static lv_obj_t   *s_lbl_line3  = NULL;
static lv_obj_t   *s_lbl_bottom = NULL;

static lv_timer_t *s_back_timer = NULL;

void screen_result_cancel_timers(void)
{
    if (s_back_timer) {
        lv_timer_del(s_back_timer);
        s_back_timer = NULL;
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
    if (*p == '"') {
        p++;
        int i = 0;
        while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
        out[i] = '\0';
        return 1;
    }
    return 0;
}

static int _get_bool(const char *json, const char *key)
{
    char needle[64];
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return 0;
    p += strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p == 't') return 1;   /* true */
    return 0;                   /* false or missing */
}

static int _has_text(const char *s)
{
    if (!s) return 0;
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
    return *s != '\0';
}

static void _trim_in_place(char *s)
{
    if (!s) return;
    char *start = s;
    while (*start == ' ' || *start == '\t' || *start == '\n' || *start == '\r') start++;
    if (start != s) memmove(s, start, strlen(start) + 1);

    size_t len = strlen(s);
    while (len > 0) {
        char c = s[len - 1];
        if (c != ' ' && c != '\t' && c != '\n' && c != '\r') break;
        s[--len] = '\0';
    }
}

static void _request_back(void)
{
    /* Frozen Task 3 policy: RESULT dismiss is fully manual-only.
     * Do not arm any fallback timers; just emit the back action immediately. */
    if (s_back_timer) { lv_timer_del(s_back_timer); s_back_timer = NULL; }
    ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
}

/* ─── Timer callback ────────────────────────────────────────────────────── */
/* ─── Build screen ──────────────────────────────────────────────────────── */
static void _build_screen(void)
{
    s_screen = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);
    lv_obj_set_size(s_screen, 320, 240);

    /* Icon (checkmark or X) — use font 32 since 48 may not be available */
    s_lbl_icon = lv_label_create(s_screen);
    lv_obj_align(s_lbl_icon, LV_ALIGN_CENTER, 0, -70);
    lv_obj_set_style_text_font(s_lbl_icon, &lv_font_montserrat_32, 0);

    /* Title */
    s_lbl_title = lv_label_create(s_screen);
    lv_obj_align(s_lbl_title, LV_ALIGN_CENTER, 0, -30);
    lv_obj_set_width(s_lbl_title, 300);
    lv_label_set_long_mode(s_lbl_title, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_title, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_title, &lv_font_montserrat_24, 0);
    lv_obj_set_style_text_align(s_lbl_title, LV_TEXT_ALIGN_CENTER, 0);

    /* Line 1: amount or error */
    s_lbl_line1 = lv_label_create(s_screen);
    lv_obj_align(s_lbl_line1, LV_ALIGN_CENTER, 0, 5);
    lv_obj_set_width(s_lbl_line1, 300);
    lv_label_set_long_mode(s_lbl_line1, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_line1, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(s_lbl_line1, &lv_font_montserrat_16, 0);
    lv_obj_set_style_text_align(s_lbl_line1, LV_TEXT_ALIGN_CENTER, 0);

    /* Line 2: TP/SL (success only) */
    s_lbl_line2 = lv_label_create(s_screen);
    lv_obj_align(s_lbl_line2, LV_ALIGN_CENTER, 0, 30);
    lv_obj_set_width(s_lbl_line2, 300);
    lv_label_set_long_mode(s_lbl_line2, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_line2, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_line2, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_line2, LV_TEXT_ALIGN_CENTER, 0);

    /* Line 3: TX id (success only) */
    s_lbl_line3 = lv_label_create(s_screen);
    lv_obj_align(s_lbl_line3, LV_ALIGN_CENTER, 0, 48);
    lv_obj_set_width(s_lbl_line3, 300);
    lv_label_set_long_mode(s_lbl_line3, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_color(s_lbl_line3, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_line3, &lv_font_montserrat_12, 0);
    lv_obj_set_style_text_align(s_lbl_line3, LV_TEXT_ALIGN_CENTER, 0);

    /* Divider above bottom bar */
    lv_obj_t *div = lv_obj_create(s_screen);
    lv_obj_set_size(div, 320, 1);
    lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
    lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
    lv_obj_set_style_border_width(div, 0, 0);

    /* Bottom bar */
    s_lbl_bottom = lv_label_create(s_screen);
    lv_obj_align(s_lbl_bottom, LV_ALIGN_BOTTOM_MID, 0, -4);
    lv_label_set_text(s_lbl_bottom, "press any key");
    lv_obj_set_style_text_color(s_lbl_bottom, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_bottom, &lv_font_montserrat_12, 0);
}

/* ─── Public API ────────────────────────────────────────────────────────── */

void screen_result_show(const char *json_data)
{
    if (!s_screen) {
        _build_screen();
    }

    screen_result_cancel_timers();

    int success = _get_bool(json_data, "success");

    char title[64] = {0};
    char subtitle[128] = {0};
    _get_str(json_data, "title", title, sizeof(title));
    _get_str(json_data, "subtitle", subtitle, sizeof(subtitle));
    _trim_in_place(title);
    _trim_in_place(subtitle);

    if (success) {
        lv_label_set_text(s_lbl_icon, LV_SYMBOL_OK);
        lv_obj_set_style_text_color(s_lbl_icon, COLOR_GREEN, 0);

        lv_label_set_text(s_lbl_title, _has_text(title) ? title : "Success");

        /* Amount line */
        char out_amount[64] = {0}, amount[64] = {0}, amount_usd[32] = {0};
        _get_str(json_data, "out_amount", out_amount, sizeof(out_amount));
        _get_str(json_data, "amount", amount, sizeof(amount));
        _get_str(json_data, "amount_usd", amount_usd, sizeof(amount_usd));
        _trim_in_place(out_amount);
        _trim_in_place(amount);
        _trim_in_place(amount_usd);
        char line1[128];
        const char *amount_main = _has_text(out_amount) ? out_amount : amount;
        if (_has_text(amount_main) && _has_text(amount_usd)) {
            snprintf(line1, sizeof(line1), "%s  (%s)", amount_main, amount_usd);
        } else if (_has_text(amount_main)) {
            snprintf(line1, sizeof(line1), "%s", amount_main);
        } else if (_has_text(amount_usd)) {
            snprintf(line1, sizeof(line1), "%s", amount_usd);
        } else {
            snprintf(line1, sizeof(line1), "Completed");
        }
        lv_label_set_text(s_lbl_line1, line1);

        /* TP / SL line */
        char tp_price[32] = {0}, sl_price[32] = {0};
        _get_str(json_data, "tp_price", tp_price, sizeof(tp_price));
        _get_str(json_data, "sl_price", sl_price, sizeof(sl_price));
        _trim_in_place(tp_price);
        _trim_in_place(sl_price);
        if (_has_text(subtitle)) {
            lv_label_set_text(s_lbl_line2, subtitle);
            lv_obj_clear_flag(s_lbl_line2, LV_OBJ_FLAG_HIDDEN);
        } else if (_has_text(tp_price) || _has_text(sl_price)) {
            char line2[96];
            snprintf(line2, sizeof(line2), "TP: %s  SL: %s",
                     _has_text(tp_price) ? tp_price : "--",
                     _has_text(sl_price) ? sl_price : "--");
            lv_label_set_text(s_lbl_line2, line2);
            lv_obj_clear_flag(s_lbl_line2, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_label_set_text(s_lbl_line2, "");
            lv_obj_add_flag(s_lbl_line2, LV_OBJ_FLAG_HIDDEN);
        }

        /* TX id line */
        char tx_id[32] = {0}, tx_hash[32] = {0};
        _get_str(json_data, "tx_id", tx_id, sizeof(tx_id));
        _get_str(json_data, "tx_hash", tx_hash, sizeof(tx_hash));
        _trim_in_place(tx_id);
        _trim_in_place(tx_hash);
        if (!_has_text(tx_id) && _has_text(tx_hash)) {
            strncpy(tx_id, tx_hash, sizeof(tx_id) - 1);
            tx_id[sizeof(tx_id) - 1] = '\0';
        }
        if (_has_text(tx_id)) {
            char line3[64];
            snprintf(line3, sizeof(line3), "TX: %s", tx_id);
            lv_label_set_text(s_lbl_line3, line3);
            lv_obj_clear_flag(s_lbl_line3, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_label_set_text(s_lbl_line3, "");
            lv_obj_add_flag(s_lbl_line3, LV_OBJ_FLAG_HIDDEN);
        }
    } else {
        lv_label_set_text(s_lbl_icon, LV_SYMBOL_CLOSE);
        lv_obj_set_style_text_color(s_lbl_icon, COLOR_RED, 0);

        lv_label_set_text(s_lbl_title, _has_text(title) ? title : "Failed");

        /* Error line */
        char error[128] = {0};
        _get_str(json_data, "error", error, sizeof(error));
        _trim_in_place(error);
        lv_label_set_text(s_lbl_line1, _has_text(error) ? error : "Unknown error");

        if (_has_text(subtitle) && strcmp(subtitle, error) != 0) {
            lv_label_set_text(s_lbl_line2, subtitle);
            lv_obj_clear_flag(s_lbl_line2, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_label_set_text(s_lbl_line2, "");
            lv_obj_add_flag(s_lbl_line2, LV_OBJ_FLAG_HIDDEN);
        }
        lv_label_set_text(s_lbl_line3, "");
        lv_obj_add_flag(s_lbl_line3, LV_OBJ_FLAG_HIDDEN);
    }

    lv_screen_load(s_screen);
}

void screen_result_key(int key)
{
    (void)key;
    screen_result_cancel_timers();
    _request_back();
}

int screen_result_get_selected_context_json(char *out, size_t out_n)
{
    int n;

    if (!out || out_n == 0) return 0;

    n = snprintf(out, out_n, "%s", "{\"screen\":\"result\"}");
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}
