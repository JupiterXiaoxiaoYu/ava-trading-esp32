#ifndef FAKE_LVGL_H
#define FAKE_LVGL_H

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct lv_obj_t {
    char text[128];
} lv_obj_t;

typedef struct lv_chart_series_t {
    int dummy;
} lv_chart_series_t;

typedef struct lv_timer_t lv_timer_t;

typedef struct lv_display_t {
    int dummy;
} lv_display_t;

typedef struct lv_font_t {
    int dummy;
} lv_font_t;

typedef struct lv_color_t {
    uint32_t full;
} lv_color_t;

struct lv_timer_t {
    uint32_t period;
    int32_t repeat_count;
    uint32_t due_tick;
    void (*cb)(lv_timer_t *);
    void *user_data;
    bool active;
};

extern const lv_font_t lv_font_montserrat_12;
extern const lv_font_t lv_font_montserrat_14;

#define LV_ALIGN_TOP_LEFT      0
#define LV_ALIGN_TOP_MID       1
#define LV_ALIGN_TOP_RIGHT     2
#define LV_ALIGN_LEFT_MID      3
#define LV_ALIGN_CENTER        4
#define LV_ALIGN_RIGHT_MID     5
#define LV_ALIGN_BOTTOM_LEFT   6
#define LV_ALIGN_BOTTOM_MID    7
#define LV_ALIGN_BOTTOM_RIGHT  8

#define LV_LABEL_LONG_CLIP 0

#define LV_CHART_TYPE_LINE       0
#define LV_CHART_AXIS_PRIMARY_Y  0

#define LV_PART_MAIN       0
#define LV_PART_ITEMS      1
#define LV_PART_INDICATOR  2

#define LV_ANIM_OFF 0

lv_color_t lv_color_hex(uint32_t value);

lv_obj_t *lv_obj_create(lv_obj_t *parent);
void lv_obj_set_style_bg_color(lv_obj_t *obj, lv_color_t color, int part);
void lv_obj_set_size(lv_obj_t *obj, int w, int h);
void lv_obj_set_pos(lv_obj_t *obj, int x, int y);
void lv_obj_align(lv_obj_t *obj, int align, int x_ofs, int y_ofs);
void lv_obj_set_style_border_width(lv_obj_t *obj, int width, int part);
void lv_obj_set_style_pad_all(lv_obj_t *obj, int pad, int part);
void lv_obj_set_style_text_color(lv_obj_t *obj, lv_color_t color, int part);
void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *font, int part);
void lv_obj_set_width(lv_obj_t *obj, int w);
void lv_obj_set_style_line_color(lv_obj_t *obj, lv_color_t color, int part);
void lv_obj_set_style_size(lv_obj_t *obj, int w, int h, int part);
void lv_obj_set_style_radius(lv_obj_t *obj, int radius, int part);

lv_obj_t *lv_label_create(lv_obj_t *parent);
void lv_label_set_long_mode(lv_obj_t *obj, int mode);
void lv_label_set_text(lv_obj_t *obj, const char *text);
void lv_label_set_text_fmt(lv_obj_t *obj, const char *fmt, ...);

lv_obj_t *lv_chart_create(lv_obj_t *parent);
void lv_chart_set_type(lv_obj_t *obj, int type);
void lv_chart_set_div_line_count(lv_obj_t *obj, int hdiv, int vdiv);
lv_chart_series_t *lv_chart_add_series(lv_obj_t *obj, lv_color_t color, int axis);
void lv_chart_set_point_count(lv_obj_t *obj, uint16_t count);
void lv_chart_set_range(lv_obj_t *obj, int axis, int min, int max);
int32_t *lv_chart_get_y_array(lv_obj_t *obj, lv_chart_series_t *ser);
void lv_chart_refresh(lv_obj_t *obj);

void lv_screen_load(lv_obj_t *screen);

lv_timer_t *lv_timer_create(void (*cb)(lv_timer_t *), uint32_t period, void *user_data);
void lv_timer_set_repeat_count(lv_timer_t *timer, int32_t repeat_count);
void lv_timer_del(lv_timer_t *timer);
uint32_t lv_timer_handler(void);

void lv_init(void);
void lv_tick_inc(uint32_t tick_period);
uint32_t lv_tick_get(void);
uint32_t lv_tick_elaps(uint32_t prev_tick);

#ifdef __cplusplus
}
#endif

#endif
