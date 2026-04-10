#ifndef AVE_FONT_PROVIDER_H
#define AVE_FONT_PROVIDER_H

#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

const lv_font_t *ave_font_cjk_14(void);
const lv_font_t *ave_font_cjk_16(void);
const char *ave_font_debug_sim_misans_path(void);

#endif /* AVE_FONT_PROVIDER_H */
