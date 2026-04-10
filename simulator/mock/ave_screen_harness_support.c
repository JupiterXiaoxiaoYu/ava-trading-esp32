#include <stdio.h>
#include <string.h>

#include "lvgl/lvgl.h"

#if defined(__GNUC__)
#define AVE_HARNESS_WEAK __attribute__((weak))
#else
#define AVE_HARNESS_WEAK
#endif

AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_12 = {0};
AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_14 = {0};

AVE_HARNESS_WEAK void lv_obj_set_style_text_align(lv_obj_t *obj, int align, int part)
{
    (void)obj;
    (void)align;
    (void)part;
}

AVE_HARNESS_WEAK int lv_font_get_line_height(const lv_font_t *font)
{
    (void)font;
    return 14;
}

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
