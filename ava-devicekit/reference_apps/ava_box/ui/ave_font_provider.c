#include "ave_font_provider.h"

#include <stdio.h>
#include <string.h>

/* Firmware builds bundle these LVGL fonts via the firmware font component. */
LV_FONT_DECLARE(font_puhui_basic_14_1);
LV_FONT_DECLARE(font_puhui_basic_16_4);

const lv_font_t *ave_font_cjk_14(void)
{
#if defined(LV_SIMULATOR)
    return &lv_font_montserrat_14;
#else
    return &font_puhui_basic_14_1;
#endif
}

const lv_font_t *ave_font_cjk_16(void)
{
#if defined(LV_SIMULATOR)
    return &lv_font_montserrat_16;
#else
    return &font_puhui_basic_16_4;
#endif
}

const char *ave_font_debug_sim_misans_path(void)
{
    return NULL;
}
