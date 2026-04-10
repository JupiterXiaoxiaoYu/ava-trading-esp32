/**
 * @file screen_notify.c
 * @brief NOTIFY overlay — top banner (manual dismiss only).
 *
 * Layout (320x58 overlay on lv_layer_top):
 *   Left 6px color bar (full height, colored by level)
 *   Title: font 14, white, x=12, y=8
 *   Body:  font 12, gray,  x=12, y=28
 */
#include "ave_screen_manager.h"
#include "ave_json_utils.h"
#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

/* ---- Colors ------------------------------------------------------------ */
#define COLOR_GREEN   lv_color_hex(0x00C853)
#define COLOR_RED     lv_color_hex(0xFF1744)
#define COLOR_ORANGE  lv_color_hex(0xFF6D00)
#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)

/* ---- State ------------------------------------------------------------- */
static lv_obj_t   *s_overlay    = NULL;

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

/* ---- Hide callback ----------------------------------------------------- */
static void _hide_cb(lv_timer_t *t)
{
    (void)t;
    if (s_overlay) { lv_obj_del(s_overlay); s_overlay = NULL; }
}

/* ---- Public API -------------------------------------------------------- */
bool screen_notify_is_visible(void)
{
    return (s_overlay != NULL && lv_obj_is_valid(s_overlay));
}

void screen_notify_key(int key)
{
    (void)key;   /* any key dismisses immediately (manual-only policy) */
    if (!screen_notify_is_visible()) return;
    _hide_cb(NULL);
}

void screen_notify_show(const char *json_data)
{
    /* Tear down previous overlay if still visible */
    if (s_overlay) { lv_obj_del(s_overlay); s_overlay = NULL; }

    /* Parse JSON fields */
    char level[16] = {0}, title[80] = {0}, body[128] = {0}, subtitle[128] = {0};
    _getf(json_data, "level", level, sizeof(level));
    _getf(json_data, "title", title, sizeof(title));
    _getf(json_data, "body",  body,  sizeof(body));
    _getf(json_data, "subtitle", subtitle, sizeof(subtitle));
    if (body[0] == '\0' && subtitle[0] != '\0') {
        strncpy(body, subtitle, sizeof(body) - 1);
        body[sizeof(body) - 1] = '\0';
    }

    /* Determine accent color */
    lv_color_t accent = COLOR_GREEN;
    if (strcmp(level, "error") == 0)        accent = COLOR_RED;
    else if (strcmp(level, "warning") == 0) accent = COLOR_ORANGE;

    /* Overlay panel on lv_layer_top */
    s_overlay = lv_obj_create(lv_layer_top());
    lv_obj_set_pos(s_overlay, 0, 0);
    lv_obj_set_size(s_overlay, 320, 58);
    lv_obj_set_style_bg_color(s_overlay, lv_color_hex(0x0D0D0D), 0);
    lv_obj_set_style_bg_opa(s_overlay, LV_OPA_90, 0);
    lv_obj_set_style_border_width(s_overlay, 0, 0);
    lv_obj_set_style_radius(s_overlay, 0, 0);
    lv_obj_set_style_pad_all(s_overlay, 0, 0);

    /* Left color bar (6px wide, full height) */
    lv_obj_t *bar = lv_obj_create(s_overlay);
    lv_obj_set_size(bar, 6, 58);
    lv_obj_set_pos(bar, 0, 0);
    lv_obj_set_style_bg_color(bar, accent, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_radius(bar, 0, 0);
    lv_obj_set_style_pad_all(bar, 0, 0);

    /* Title label */
    lv_obj_t *lbl_title = lv_label_create(s_overlay);
    lv_obj_set_pos(lbl_title, 12, 8);
    lv_label_set_text(lbl_title, title);
    lv_obj_set_width(lbl_title, 320 - 12);
    lv_label_set_long_mode(lbl_title, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_color(lbl_title, COLOR_WHITE, 0);
    lv_obj_set_style_text_font(lbl_title, &lv_font_montserrat_14, 0);

    /* Body label */
    lv_obj_t *lbl_body = lv_label_create(s_overlay);
    lv_obj_set_pos(lbl_body, 12, 28);
    lv_label_set_text(lbl_body, body);
    lv_obj_set_width(lbl_body, 320 - 12);
    lv_label_set_long_mode(lbl_body, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_color(lbl_body, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(lbl_body, &lv_font_montserrat_12, 0);
}
