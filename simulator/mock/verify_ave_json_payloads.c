#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ave_screen_manager.h"
#include "ave_transport.h"
#include "lvgl/lvgl.h"

const lv_font_t lv_font_montserrat_12 = {0};
const lv_font_t lv_font_montserrat_14 = {0};

static char g_last_json[1024];
static uint32_t g_tick = 0;
static int32_t g_chart_points[128];

lv_color_t lv_color_hex(uint32_t value)
{
    lv_color_t color = {.full = value};
    return color;
}

lv_obj_t *lv_obj_create(lv_obj_t *parent)
{
    (void)parent;
    return (lv_obj_t *)calloc(1, sizeof(lv_obj_t));
}

void lv_obj_clear_flag(lv_obj_t *obj, int flag)
{
    (void)obj;
    (void)flag;
}

void lv_obj_set_style_bg_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

void lv_obj_set_style_bg_opa(lv_obj_t *obj, int opa, int part)
{
    (void)obj;
    (void)opa;
    (void)part;
}

void lv_obj_set_style_border_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

void lv_obj_set_style_border_side(lv_obj_t *obj, int side, int part)
{
    (void)obj;
    (void)side;
    (void)part;
}

void lv_obj_set_style_border_width(lv_obj_t *obj, int width, int part)
{
    (void)obj;
    (void)width;
    (void)part;
}

void lv_obj_set_style_line_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

void lv_obj_set_style_pad_all(lv_obj_t *obj, int pad, int part)
{
    (void)obj;
    (void)pad;
    (void)part;
}

void lv_obj_set_style_radius(lv_obj_t *obj, int radius, int part)
{
    (void)obj;
    (void)radius;
    (void)part;
}

void lv_obj_set_style_size(lv_obj_t *obj, int width, int height, int part)
{
    (void)obj;
    (void)width;
    (void)height;
    (void)part;
}

void lv_obj_set_style_text_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *font, int part)
{
    (void)obj;
    (void)font;
    (void)part;
}

void lv_obj_set_width(lv_obj_t *obj, int width)
{
    (void)obj;
    (void)width;
}

void lv_obj_set_size(lv_obj_t *obj, int width, int height)
{
    (void)obj;
    (void)width;
    (void)height;
}

void lv_obj_set_pos(lv_obj_t *obj, int x, int y)
{
    (void)obj;
    (void)x;
    (void)y;
}

void lv_obj_align(lv_obj_t *obj, int align, int x_ofs, int y_ofs)
{
    (void)obj;
    (void)align;
    (void)x_ofs;
    (void)y_ofs;
}

lv_obj_t *lv_label_create(lv_obj_t *parent)
{
    return lv_obj_create(parent);
}

void lv_label_set_long_mode(lv_obj_t *obj, int mode)
{
    (void)obj;
    (void)mode;
}

void lv_label_set_text(lv_obj_t *obj, const char *text)
{
    if (!obj) return;
    snprintf(obj->text, sizeof(obj->text), "%s", text ? text : "");
}

void lv_label_set_text_fmt(lv_obj_t *obj, const char *fmt, ...)
{
    va_list args;

    if (!obj) return;
    va_start(args, fmt);
    vsnprintf(obj->text, sizeof(obj->text), fmt, args);
    va_end(args);
}

lv_obj_t *lv_chart_create(lv_obj_t *parent)
{
    return lv_obj_create(parent);
}

void lv_chart_set_type(lv_obj_t *obj, int type)
{
    (void)obj;
    (void)type;
}

void lv_chart_set_div_line_count(lv_obj_t *obj, int hdiv, int vdiv)
{
    (void)obj;
    (void)hdiv;
    (void)vdiv;
}

lv_chart_series_t *lv_chart_add_series(lv_obj_t *obj, lv_color_t color, int axis)
{
    static lv_chart_series_t series;
    (void)obj;
    (void)color;
    (void)axis;
    return &series;
}

void lv_chart_set_point_count(lv_obj_t *obj, uint16_t count)
{
    (void)obj;
    (void)count;
}

void lv_chart_set_range(lv_obj_t *obj, int axis, int min, int max)
{
    (void)obj;
    (void)axis;
    (void)min;
    (void)max;
}

int32_t *lv_chart_get_y_array(lv_obj_t *obj, lv_chart_series_t *ser)
{
    (void)obj;
    (void)ser;
    return g_chart_points;
}

void lv_chart_refresh(lv_obj_t *obj)
{
    (void)obj;
}

void lv_screen_load(lv_obj_t *screen)
{
    (void)screen;
}

lv_timer_t *lv_timer_create(void (*cb)(lv_timer_t *), uint32_t period, void *user_data)
{
    lv_timer_t *timer = (lv_timer_t *)calloc(1, sizeof(lv_timer_t));
    if (!timer) return NULL;
    timer->cb = cb;
    timer->period = period;
    timer->user_data = user_data;
    timer->repeat_count = -1;
    return timer;
}

void lv_timer_set_repeat_count(lv_timer_t *timer, int32_t repeat_count)
{
    if (timer) timer->repeat_count = repeat_count;
}

void lv_timer_del(lv_timer_t *timer)
{
    free(timer);
}

void lv_init(void)
{
}

void lv_tick_inc(uint32_t tick_period)
{
    g_tick += tick_period;
}

uint32_t lv_tick_get(void)
{
    return g_tick;
}

uint32_t lv_tick_elaps(uint32_t prev_tick)
{
    return g_tick - prev_tick;
}

void ave_send_json(const char *json)
{
    snprintf(g_last_json, sizeof(g_last_json), "%s", json ? json : "");
}

static void clear_last_json(void)
{
    g_last_json[0] = '\0';
}

static int expect_contains(const char *needle, const char *label)
{
    if (!strstr(g_last_json, needle)) {
        fprintf(stderr, "FAIL: %s missing %s in %s\n", label, needle, g_last_json[0] ? g_last_json : "<empty>");
        return 0;
    }
    return 1;
}

static int expect_not_contains(const char *needle, const char *label)
{
    if (strstr(g_last_json, needle)) {
        fprintf(stderr, "FAIL: %s unexpectedly contained %s in %s\n", label, needle, g_last_json);
        return 0;
    }
    return 1;
}

#if !defined(VERIFY_FEED)
void screen_feed_show(const char *json_data) { (void)json_data; }
void screen_feed_key(int key) { (void)key; }
bool screen_feed_should_ignore_live_push(void) { return false; }
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
#endif

#if !defined(VERIFY_PORTFOLIO)
void screen_portfolio_show(const char *json_data) { (void)json_data; }
void screen_portfolio_key(int key) { (void)key; }
void screen_portfolio_cancel_back_timer(void) {}
int screen_portfolio_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
#endif

#if !defined(VERIFY_SPOTLIGHT)
void screen_spotlight_show(const char *json_data) { (void)json_data; }
void screen_spotlight_key(int key) { (void)key; }
void screen_spotlight_cancel_back_timer(void) {}
int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
#endif

void screen_confirm_show(const char *json_data) { (void)json_data; }
void screen_confirm_key(int key) { (void)key; }
void screen_confirm_cancel_timers(void) {}
void screen_limit_confirm_show(const char *json_data) { (void)json_data; }
void screen_limit_confirm_key(int key) { (void)key; }
void screen_limit_confirm_cancel_timers(void) {}
void screen_result_show(const char *json_data) { (void)json_data; }
void screen_result_key(int key) { (void)key; }
void screen_result_cancel_timers(void) {}
void screen_notify_show(const char *json_data) { (void)json_data; }
bool screen_notify_is_visible(void) { return false; }
void screen_notify_key(int key) { (void)key; }

#if defined(VERIFY_FEED)
#include "../../shared/ave_screens/screen_feed.c"

int main(void)
{
    int ok = 1;

    memset(s_tokens, 0, sizeof(s_tokens));
    s_token_count = 1;
    s_token_idx = 0;
    snprintf(s_tokens[0].token_id, sizeof(s_tokens[0].token_id), "%s", "bad\"id\\slash\nline");
    snprintf(s_tokens[0].chain, sizeof(s_tokens[0].chain), "%s", "sol\"ana");
    snprintf(s_tokens[0].symbol, sizeof(s_tokens[0].symbol), "%s", "S\"YM");

    clear_last_json();
    screen_feed_key(AVE_KEY_A);
    ok &= expect_contains("\"action\":\"watch\"", "feed watch action");
    ok &= expect_contains("bad\\\"id\\\\slash\\nline", "feed token id escaped");
    ok &= expect_contains("sol\\\"ana", "feed chain escaped");
    ok &= expect_not_contains("bad\"id\\slash\nline", "feed raw token id");

    return ok ? 0 : 1;
}
#elif defined(VERIFY_PORTFOLIO)
#include "../../shared/ave_screens/screen_portfolio.c"

int main(void)
{
    int ok = 1;

    memset(s_holdings, 0, sizeof(s_holdings));
    s_holding_count = 1;
    s_sel_idx = 0;
    snprintf(s_holdings[0].addr, sizeof(s_holdings[0].addr), "%s", "addr\"1\\line");
    snprintf(s_holdings[0].chain, sizeof(s_holdings[0].chain), "%s", "sol\"ana");
    snprintf(s_holdings[0].symbol, sizeof(s_holdings[0].symbol), "%s", "SYM\"1");
    snprintf(s_holdings[0].balance_raw, sizeof(s_holdings[0].balance_raw), "%s", "10\".25");

    clear_last_json();
    screen_portfolio_key(AVE_KEY_A);
    ok &= expect_contains("\"action\":\"portfolio_watch\"", "portfolio watch action");
    ok &= expect_contains("addr\\\"1\\\\line", "portfolio watch addr escaped");
    ok &= expect_contains("sol\\\"ana", "portfolio watch chain escaped");
    ok &= expect_not_contains("addr\"1\\line", "portfolio raw watch addr");

    clear_last_json();
    screen_portfolio_key(AVE_KEY_X);
    ok &= expect_contains("\"action\":\"portfolio_sell\"", "portfolio sell action");
    ok &= expect_contains("SYM\\\"1", "portfolio sell symbol escaped");
    ok &= expect_contains("10\\\".25", "portfolio sell balance escaped");
    ok &= expect_not_contains("10\".25", "portfolio raw balance");

    return ok ? 0 : 1;
}
#elif defined(VERIFY_SPOTLIGHT)
#include "../../shared/ave_screens/screen_spotlight.c"

int main(void)
{
    int ok = 1;

    s_loading = false;
    snprintf(s_token_id, sizeof(s_token_id), "%s", "spot\"id\\line");
    snprintf(s_chain, sizeof(s_chain), "%s", "ba\"se");
    snprintf(s_symbol, sizeof(s_symbol), "%s", "MO\"ON");
    s_interval_idx = 1;

    clear_last_json();
    screen_spotlight_key(AVE_KEY_A);
    ok &= expect_contains("\"action\":\"buy\"", "spotlight buy action");
    ok &= expect_contains("spot\\\"id\\\\line", "spotlight buy token escaped");
    ok &= expect_contains("MO\\\"ON", "spotlight buy symbol escaped");
    ok &= expect_not_contains("spot\"id\\line", "spotlight raw buy token");

    clear_last_json();
    screen_spotlight_key(AVE_KEY_UP);
    ok &= expect_contains("\"action\":\"kline_interval\"", "spotlight interval action");
    ok &= expect_contains("spot\\\"id\\\\line", "spotlight interval token escaped");
    ok &= expect_not_contains("spot\"id\\line", "spotlight raw interval token");

    s_loading = false;
    clear_last_json();
    screen_spotlight_key(AVE_KEY_X);
    ok &= expect_contains("\"action\":\"quick_sell\"", "spotlight quick sell action");
    ok &= expect_contains("MO\\\"ON", "spotlight quick sell symbol escaped");
    ok &= expect_not_contains("MO\"ON", "spotlight raw quick sell symbol");

    return ok ? 0 : 1;
}
#else
#error "Define VERIFY_FEED, VERIFY_PORTFOLIO, or VERIFY_SPOTLIGHT"
#endif
