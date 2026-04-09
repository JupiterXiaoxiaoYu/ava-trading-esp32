#ifndef MOCK_LVGL_LVGL_H
#define MOCK_LVGL_LVGL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct lv_obj_t {
    int placeholder;
} lv_obj_t;

typedef struct lv_display_t {
    int placeholder;
} lv_display_t;

typedef uint32_t lv_color_t;

typedef struct lv_font_t {
    int placeholder;
} lv_font_t;

extern const lv_font_t lv_font_montserrat_12;
extern const lv_font_t lv_font_montserrat_14;

#define LV_OPA_COVER 255
#define LV_OBJ_FLAG_SCROLLABLE 0x1
#define LV_ALIGN_RIGHT_MID 0
#define LV_ALIGN_LEFT_MID 1
#define LV_ALIGN_CENTER 2
#define LV_LABEL_LONG_CLIP 0

static inline lv_color_t lv_color_hex(uint32_t c)
{
    return c;
}

static inline lv_obj_t *lv_obj_create(lv_obj_t *parent)
{
    (void)parent;
    static lv_obj_t obj;
    return &obj;
}

static inline void lv_obj_remove_flag(lv_obj_t *obj, int flag)
{
    (void)obj;
    (void)flag;
}

static inline void lv_obj_clear_flag(lv_obj_t *obj, int flag)
{
    (void)obj;
    (void)flag;
}

static inline void lv_obj_set_style_bg_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

static inline void lv_obj_set_style_bg_opa(lv_obj_t *obj, int opa, int part)
{
    (void)obj;
    (void)opa;
    (void)part;
}

static inline void lv_obj_set_style_border_width(lv_obj_t *obj, int width, int part)
{
    (void)obj;
    (void)width;
    (void)part;
}

static inline void lv_obj_set_style_pad_all(lv_obj_t *obj, int pad, int part)
{
    (void)obj;
    (void)pad;
    (void)part;
}

static inline void lv_obj_set_style_pad_left(lv_obj_t *obj, int pad, int part)
{
    (void)obj;
    (void)pad;
    (void)part;
}

static inline void lv_obj_set_style_text_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

static inline void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *font, int part)
{
    (void)obj;
    (void)font;
    (void)part;
}

static inline void lv_obj_set_style_text_opa(lv_obj_t *obj, int opa, int part)
{
    (void)obj;
    (void)opa;
    (void)part;
}

static inline void lv_obj_set_size(lv_obj_t *obj, int width, int height)
{
    (void)obj;
    (void)width;
    (void)height;
}

static inline void lv_obj_set_width(lv_obj_t *obj, int width)
{
    (void)obj;
    (void)width;
}

static inline void lv_obj_align(lv_obj_t *obj, int align, int x_ofs, int y_ofs)
{
    (void)obj;
    (void)align;
    (void)x_ofs;
    (void)y_ofs;
}

static inline lv_obj_t *lv_label_create(lv_obj_t *parent)
{
    return lv_obj_create(parent);
}

static inline void lv_label_set_text(lv_obj_t *obj, const char *text)
{
    (void)obj;
    (void)text;
}

static inline void lv_label_set_long_mode(lv_obj_t *obj, int mode)
{
    (void)obj;
    (void)mode;
}

static inline void lv_obj_set_pos(lv_obj_t *obj, int x, int y)
{
    (void)obj;
    (void)x;
    (void)y;
}

static inline void lv_screen_load(lv_obj_t *obj)
{
    (void)obj;
}

#ifdef __cplusplus
}
#endif

#endif
