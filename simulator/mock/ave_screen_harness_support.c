#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lvgl/lvgl.h"

#if defined(__GNUC__)
#define AVE_HARNESS_WEAK __attribute__((weak))
#else
#define AVE_HARNESS_WEAK
#endif

AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_12 = {0};
AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_14 = {0};

AVE_HARNESS_WEAK void lv_obj_set_style_text_align(lv_obj_t *obj, lv_text_align_t value, lv_style_selector_t selector)
{
    (void)obj;
    (void)value;
    (void)selector;
}

AVE_HARNESS_WEAK void lv_label_set_recolor(lv_obj_t *obj, bool en)
{
    (void)obj;
    (void)en;
}

AVE_HARNESS_WEAK int32_t lv_font_get_line_height(const lv_font_t *font)
{
    (void)font;
    return 14;
}

#if defined(JSON_VERIFY_LVGL_H)
AVE_HARNESS_WEAK lv_obj_t *lv_bar_create(lv_obj_t *parent)
{
    (void)parent;
    return (lv_obj_t *)calloc(1, sizeof(lv_obj_t));
}

AVE_HARNESS_WEAK void lv_bar_set_range(lv_obj_t *obj, int min, int max)
{
    (void)obj;
    (void)min;
    (void)max;
}

AVE_HARNESS_WEAK void lv_bar_set_value(lv_obj_t *obj, int value, int anim)
{
    (void)obj;
    (void)value;
    (void)anim;
}
#endif

AVE_HARNESS_WEAK const lv_font_t *ave_font_cjk_14(void)
{
    return &lv_font_montserrat_14;
}

AVE_HARNESS_WEAK const lv_font_t *ave_font_cjk_16(void)
{
    return &lv_font_montserrat_14;
}

AVE_HARNESS_WEAK void ave_fmt_price_text(char *buf, size_t n, const char *raw_price)
{
    if (!buf || n == 0) return;
    snprintf(buf, n, "%s", raw_price && raw_price[0] ? raw_price : "$0");
}
