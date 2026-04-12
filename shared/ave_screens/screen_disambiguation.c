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

#define MAX_ITEMS 12
#define VISIBLE_ROWS 6
#define ROW_H 28

typedef struct {
    char token_id[96];
    char chain[16];
    char symbol[24];
    char contract_tail[12];
    char source_tag[24];
} disambiguation_item_t;

static disambiguation_item_t s_items[MAX_ITEMS];
static int s_item_count = 0;
static int s_cursor = 0;
static int s_scroll_top = 0;
static int s_total_candidates = 0;
static int s_overflow_count = 0;

#if !defined(JSON_VERIFY_LVGL_H)
static lv_obj_t *s_screen = NULL;
static lv_obj_t *s_lbl_title = NULL;
static lv_obj_t *s_lbl_hint = NULL;
static lv_obj_t *s_lbl_count = NULL;
static lv_obj_t *s_row_bg[VISIBLE_ROWS];
static lv_obj_t *s_row_main[VISIBLE_ROWS];
static lv_obj_t *s_row_meta[VISIBLE_ROWS];

#define COLOR_WHITE   lv_color_hex(0xFFFFFF)
#define COLOR_GRAY    lv_color_hex(0x9E9E9E)
#define COLOR_BG      lv_color_hex(0x0A0A0A)
#define COLOR_BAR     lv_color_hex(0x141414)
#define COLOR_ALT     lv_color_hex(0x101010)
#define COLOR_SEL     lv_color_hex(0x15281C)
#define COLOR_DIVIDER lv_color_hex(0x2A2A2A)

static void _build(void);
static void _update_rows(void);
#endif

static int _json_str(const char *obj, const char *key, char *out, int n)
{
    char needle[64];
    const char *p;
    int i = 0;

    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(obj, needle);
    if (!p) return 0;
    p += (int)strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') return 0;
    p++;
    while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
    out[i] = '\0';
    return 1;
}

static int _json_int(const char *obj, const char *key, int def)
{
    char needle[64];
    const char *p;

    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(obj, needle);
    if (!p) return def;
    p += (int)strlen(needle);
    while (*p == ' ' || *p == ':') p++;
    if ((*p >= '0' && *p <= '9') || *p == '-') return atoi(p);
    return def;
}

static void _derive_contract_tail(disambiguation_item_t *item)
{
    size_t len;

    if (!item || item->contract_tail[0]) return;
    len = strlen(item->token_id);
    if (len == 0) return;
    if (len > 4) {
        memcpy(item->contract_tail, item->token_id + len - 4, 4);
        item->contract_tail[4] = '\0';
        return;
    }
    memcpy(item->contract_tail, item->token_id, len);
    item->contract_tail[len] = '\0';
}

static void _parse_items(const char *json)
{
    const char *arr;
    const char *p;

    s_item_count = 0;
    s_cursor = _json_int(json, "cursor", 0);
    s_scroll_top = 0;
    s_total_candidates = _json_int(json, "total_candidates", 0);
    s_overflow_count = _json_int(json, "overflow_count", 0);

    arr = strstr(json, "\"items\"");
    if (!arr) return;
    arr = strchr(arr, '[');
    if (!arr) return;
    p = arr + 1;

    while (*p && s_item_count < MAX_ITEMS) {
        const char *obj_start;
        size_t obj_len;
        int depth = 1;
        char *obj;
        disambiguation_item_t *item;

        p = strchr(p, '{');
        if (!p) break;
        obj_start = p++;
        while (*p && depth > 0) {
            if (*p == '"') {
                p++;
                while (*p && *p != '"') {
                    if (*p == '\\' && p[1]) p++;
                    if (*p) p++;
                }
                if (*p) p++;
                continue;
            }
            if (*p == '{') depth++;
            if (*p == '}') depth--;
            p++;
        }
        obj_len = (size_t)(p - obj_start);
        obj = (char *)malloc(obj_len + 1);
        if (!obj) break;
        memcpy(obj, obj_start, obj_len);
        obj[obj_len] = '\0';

        item = &s_items[s_item_count];
        memset(item, 0, sizeof(*item));
        _json_str(obj, "token_id", item->token_id, sizeof(item->token_id));
        _json_str(obj, "chain", item->chain, sizeof(item->chain));
        _json_str(obj, "symbol", item->symbol, sizeof(item->symbol));
        _json_str(obj, "contract_tail", item->contract_tail, sizeof(item->contract_tail));
        _json_str(obj, "source_tag", item->source_tag, sizeof(item->source_tag));
        if (!item->symbol[0]) snprintf(item->symbol, sizeof(item->symbol), "UNKNOWN");
        _derive_contract_tail(item);

        free(obj);
        s_item_count++;
    }

    if (s_total_candidates <= 0) s_total_candidates = s_item_count;
    if (s_item_count <= 0) return;
    if (s_cursor < 0) s_cursor = 0;
    if (s_cursor >= s_item_count) s_cursor = s_item_count - 1;
    if (s_cursor >= VISIBLE_ROWS) s_scroll_top = s_cursor - VISIBLE_ROWS + 1;
}

void screen_disambiguation_show(const char *json_data)
{
    _parse_items(json_data);
#if !defined(JSON_VERIFY_LVGL_H)
    if (!s_screen) _build();
    _update_rows();
    lv_screen_load(s_screen);
#endif
}

void screen_disambiguation_cancel_timers(void)
{
}

int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{
    if (!out || out_n == 0) return 0;
    /* Disambiguation is not yet an authoritative token selection. */
    return 0;
}

static void _send_selected_item(void)
{
    char msg[512];
    char cursor_buf[16];
    ave_sm_json_field_t fields[4];
    size_t field_count = 0;
    disambiguation_item_t *item;

    if (s_item_count <= 0 || s_cursor < 0 || s_cursor >= s_item_count) return;
    item = &s_items[s_cursor];
    if (!item->token_id[0] || !item->chain[0]) return;

    snprintf(cursor_buf, sizeof(cursor_buf), "%d", s_cursor);
    fields[field_count++] = (ave_sm_json_field_t){"token_id", item->token_id};
    fields[field_count++] = (ave_sm_json_field_t){"chain", item->chain};
    fields[field_count++] = (ave_sm_json_field_t){"cursor", cursor_buf};
    fields[field_count++] = (ave_sm_json_field_t){"symbol", item->symbol};

    if (!ave_sm_build_key_action_json("disambiguation_select", fields, field_count, msg, sizeof(msg))) return;
    ave_send_json(msg);
}

#if defined(JSON_VERIFY_LVGL_H)

void screen_disambiguation_key(int key)
{
    if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
    } else if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
        _send_selected_item();
    }
}

#else

static void _build(void)
{
    int i;

    s_screen = lv_obj_create(NULL);
    lv_obj_set_size(s_screen, 320, 240);
    lv_obj_set_style_bg_color(s_screen, COLOR_BG, 0);

    {
        lv_obj_t *top = lv_obj_create(s_screen);
        lv_obj_set_size(top, 320, 22);
        lv_obj_align(top, LV_ALIGN_TOP_LEFT, 0, 0);
        lv_obj_set_style_bg_color(top, COLOR_BAR, 0);
        lv_obj_set_style_border_width(top, 0, 0);
        lv_obj_set_style_pad_all(top, 0, 0);

        s_lbl_title = lv_label_create(top);
        lv_obj_align(s_lbl_title, LV_ALIGN_LEFT_MID, 6, 0);
        lv_obj_set_style_text_color(s_lbl_title, COLOR_WHITE, 0);
        lv_obj_set_style_text_font(s_lbl_title, &lv_font_montserrat_12, 0);
        lv_label_set_text(s_lbl_title, "CHOOSE ASSET");

        s_lbl_count = lv_label_create(top);
        lv_obj_align(s_lbl_count, LV_ALIGN_RIGHT_MID, -6, 0);
        lv_obj_set_style_text_color(s_lbl_count, COLOR_GRAY, 0);
        lv_obj_set_style_text_font(s_lbl_count, &lv_font_montserrat_12, 0);
    }

    s_lbl_hint = lv_label_create(s_screen);
    lv_obj_align(s_lbl_hint, LV_ALIGN_TOP_LEFT, 8, 28);
    lv_obj_set_style_text_color(s_lbl_hint, COLOR_GRAY, 0);
    lv_obj_set_style_text_font(s_lbl_hint, &lv_font_montserrat_12, 0);
    lv_label_set_text(s_lbl_hint, "UP/DOWN move  A/RIGHT choose  B back");

    for (i = 0; i < VISIBLE_ROWS; i++) {
        int y = 48 + i * ROW_H;
        s_row_bg[i] = lv_obj_create(s_screen);
        lv_obj_set_size(s_row_bg[i], 320, ROW_H);
        lv_obj_set_pos(s_row_bg[i], 0, y);
        lv_obj_set_style_border_width(s_row_bg[i], 0, 0);
        lv_obj_set_style_pad_all(s_row_bg[i], 0, 0);

        s_row_main[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_main[i], 8, 3);
        lv_obj_set_style_text_color(s_row_main[i], COLOR_WHITE, 0);
        lv_obj_set_style_text_font(s_row_main[i], &lv_font_montserrat_14, 0);

        s_row_meta[i] = lv_label_create(s_row_bg[i]);
        lv_obj_set_pos(s_row_meta[i], 8, 15);
        lv_obj_set_style_text_color(s_row_meta[i], COLOR_GRAY, 0);
        lv_obj_set_style_text_font(s_row_meta[i], &lv_font_montserrat_12, 0);
    }

    {
        lv_obj_t *div = lv_obj_create(s_screen);
        lv_obj_t *bot_left;
        lv_obj_t *bot_right;
        lv_obj_set_size(div, 320, 1);
        lv_obj_align(div, LV_ALIGN_TOP_LEFT, 0, 215);
        lv_obj_set_style_bg_color(div, COLOR_DIVIDER, 0);
        lv_obj_set_style_border_width(div, 0, 0);

        bot_left = lv_label_create(s_screen);
        lv_obj_align(bot_left, LV_ALIGN_BOTTOM_LEFT, 8, -4);
        lv_obj_set_style_text_color(bot_left, COLOR_GRAY, 0);
        lv_obj_set_style_text_font(bot_left, &lv_font_montserrat_12, 0);
        lv_label_set_text(bot_left, "[B] BACK");

        bot_right = lv_label_create(s_screen);
        lv_obj_align(bot_right, LV_ALIGN_BOTTOM_RIGHT, -8, -4);
        lv_obj_set_style_text_color(bot_right, COLOR_WHITE, 0);
        lv_obj_set_style_text_font(bot_right, &lv_font_montserrat_12, 0);
        lv_label_set_text(bot_right, "CHOOSE [A]");
    }
}

static void _update_rows(void)
{
    int i;
    char buf[96];
    char meta[96];

    if (s_lbl_count) {
        if (s_item_count > 0) {
            snprintf(buf, sizeof(buf), "%d/%d", s_cursor + 1, s_total_candidates > 0 ? s_total_candidates : s_item_count);
            lv_label_set_text(s_lbl_count, buf);
        } else {
            lv_label_set_text(s_lbl_count, "0/0");
        }
    }

    if (s_lbl_hint) {
        if (s_overflow_count > 0) {
            lv_label_set_text(s_lbl_hint, "Showing first 12. Refine search.");
        } else {
            lv_label_set_text(s_lbl_hint, "UP/DOWN move  A/RIGHT choose  B back");
        }
    }

    for (i = 0; i < VISIBLE_ROWS; i++) {
        int idx = s_scroll_top + i;
        lv_color_t bg = (idx == s_cursor) ? COLOR_SEL : ((i & 1) ? COLOR_ALT : COLOR_BG);
        lv_obj_set_style_bg_color(s_row_bg[i], bg, 0);

        if (idx >= s_item_count) {
            lv_label_set_text(s_row_main[i], "");
            lv_label_set_text(s_row_meta[i], "");
            continue;
        }

        {
            disambiguation_item_t *item = &s_items[idx];
            snprintf(buf, sizeof(buf), "%s", item->symbol[0] ? item->symbol : "UNKNOWN");
            snprintf(
                meta,
                sizeof(meta),
                "%s  *%s%s%s",
                item->chain[0] ? item->chain : "unknown",
                item->contract_tail[0] ? item->contract_tail : "----",
                item->source_tag[0] ? "  " : "",
                item->source_tag[0] ? item->source_tag : ""
            );
            lv_label_set_text(s_row_main[i], buf);
            lv_label_set_text(s_row_meta[i], meta);
        }
    }
}

static void _move_cursor(int delta)
{
    if (s_item_count <= 0) return;
    s_cursor += delta;
    if (s_cursor < 0) s_cursor = 0;
    if (s_cursor >= s_item_count) s_cursor = s_item_count - 1;
    if (s_cursor < s_scroll_top) s_scroll_top = s_cursor;
    if (s_cursor >= s_scroll_top + VISIBLE_ROWS) s_scroll_top = s_cursor - VISIBLE_ROWS + 1;
    _update_rows();
}

void screen_disambiguation_key(int key)
{
    if (key == AVE_KEY_UP) {
        _move_cursor(-1);
    } else if (key == AVE_KEY_DOWN) {
        _move_cursor(+1);
    } else if (key == AVE_KEY_LEFT || key == AVE_KEY_B) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"back\"}");
    } else if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) {
        _send_selected_item();
    } else if (key == AVE_KEY_X) {
        screen_notify_show("{\"level\":\"info\",\"title\":\"Locked\",\"body\":\"Use A to confirm a choice.\"}");
    }
}

#endif
