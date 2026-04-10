#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ave_screen_manager.h"
#include "ave_transport.h"
#include <lvgl/lvgl.h>

/* ---- Fake LVGL runtime -------------------------------------------------- */
const lv_font_t lv_font_montserrat_12 = {0};
const lv_font_t lv_font_montserrat_14 = {0};

#define FAKE_TIMER_CAP 16
#define FAKE_CHART_CAP 128

static uint32_t g_tick = 0;
static lv_timer_t *g_timers[FAKE_TIMER_CAP];
static uint32_t g_timer_due[FAKE_TIMER_CAP];
static bool g_timer_active[FAKE_TIMER_CAP];
static int g_timer_count = 0;
static int32_t g_chart_y[FAKE_CHART_CAP];

lv_color_t lv_color_hex(uint32_t value)
{
    lv_color_t c;
    c.full = value;
    return c;
}

static lv_obj_t *new_obj(void)
{
    lv_obj_t *obj = (lv_obj_t *)calloc(1, sizeof(lv_obj_t));
    return obj;
}

lv_obj_t *lv_obj_create(lv_obj_t *parent)
{
    (void)parent;
    return new_obj();
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

void lv_obj_set_size(lv_obj_t *obj, int w, int h)
{
    (void)obj;
    (void)w;
    (void)h;
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

void lv_obj_set_style_border_width(lv_obj_t *obj, int width, int part)
{
    (void)obj;
    (void)width;
    (void)part;
}

void lv_obj_set_style_pad_all(lv_obj_t *obj, int pad, int part)
{
    (void)obj;
    (void)pad;
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

void lv_obj_clear_flag(lv_obj_t *obj, int flag)
{
    (void)obj;
    (void)flag;
}

void lv_obj_set_width(lv_obj_t *obj, int w)
{
    (void)obj;
    (void)w;
}

void lv_obj_set_style_line_color(lv_obj_t *obj, lv_color_t color, int part)
{
    (void)obj;
    (void)color;
    (void)part;
}

void lv_obj_set_style_size(lv_obj_t *obj, int w, int h, int part)
{
    (void)obj;
    (void)w;
    (void)h;
    (void)part;
}

void lv_obj_set_style_radius(lv_obj_t *obj, int radius, int part)
{
    (void)obj;
    (void)radius;
    (void)part;
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
    va_list ap;
    if (!obj) return;
    va_start(ap, fmt);
    vsnprintf(obj->text, sizeof(obj->text), fmt, ap);
    va_end(ap);
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
    static lv_chart_series_t s_series;
    (void)obj;
    (void)color;
    (void)axis;
    return &s_series;
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
    return g_chart_y;
}

void lv_chart_refresh(lv_obj_t *obj)
{
    (void)obj;
}

void lv_screen_load(lv_obj_t *screen)
{
    (void)screen;
}

void lv_init(void)
{
    g_tick = 0;
    g_timer_count = 0;
    memset(g_timers, 0, sizeof(g_timers));
    memset(g_timer_due, 0, sizeof(g_timer_due));
    memset(g_timer_active, 0, sizeof(g_timer_active));
}

lv_timer_t *lv_timer_create(void (*cb)(lv_timer_t *), uint32_t period, void *user_data)
{
    lv_timer_t *timer;
    if (g_timer_count >= FAKE_TIMER_CAP) return NULL;

    timer = (lv_timer_t *)calloc(1, sizeof(lv_timer_t));
    if (!timer) return NULL;

    timer->cb = cb;
    timer->period = period;
    timer->repeat_count = -1;
    timer->user_data = user_data;
    g_timers[g_timer_count++] = timer;
    g_timer_due[g_timer_count - 1] = g_tick + period;
    g_timer_active[g_timer_count - 1] = true;
    return timer;
}

void lv_timer_set_repeat_count(lv_timer_t *timer, int32_t repeat_count)
{
    if (!timer) return;
    timer->repeat_count = repeat_count;
}

void lv_timer_del(lv_timer_t *timer)
{
    int i;
    if (!timer) return;

    for (i = 0; i < g_timer_count; i++) {
        if (g_timers[i] == timer) {
            free(g_timers[i]);
            g_timers[i] = g_timers[g_timer_count - 1];
            g_timer_due[i] = g_timer_due[g_timer_count - 1];
            g_timer_active[i] = g_timer_active[g_timer_count - 1];
            g_timers[g_timer_count - 1] = NULL;
            g_timer_due[g_timer_count - 1] = 0;
            g_timer_active[g_timer_count - 1] = false;
            g_timer_count--;
            return;
        }
    }
}

uint32_t lv_timer_handler(void)
{
    int i;
    for (i = g_timer_count - 1; i >= 0; i--) {
        lv_timer_t *timer = g_timers[i];
        if (!timer || !g_timer_active[i]) continue;
        if (g_tick < g_timer_due[i]) continue;

        timer->cb(timer);

        if (timer->repeat_count == 1) {
            lv_timer_del(timer);
        } else {
            if (timer->repeat_count > 1) timer->repeat_count--;
            g_timer_due[i] = g_tick + timer->period;
        }
    }
    return 0;
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

/* ---- Screen deps -------------------------------------------------------- */
static char g_last_json[512];

int ave_sm_json_escape_string(const char *src, char *out, size_t out_n)
{
    size_t oi = 0;
    size_t i = 0;
    if (!src || !out || out_n == 0) return 0;
    while (src[i] != '\0') {
        const char *esc = NULL;
        char ch = src[i++];
        switch (ch) {
            case '\"': esc = "\\\""; break;
            case '\\': esc = "\\\\"; break;
            case '\n': esc = "\\n"; break;
            case '\r': esc = "\\r"; break;
            case '\t': esc = "\\t"; break;
            default: break;
        }
        if (esc) {
            if (oi + 2 >= out_n) return 0;
            out[oi++] = esc[0];
            out[oi++] = esc[1];
            continue;
        }
        if (oi + 1 >= out_n) return 0;
        out[oi++] = ch;
    }
    out[oi] = '\0';
    return 1;
}

int ave_sm_build_key_action_json(
    const char *action,
    const ave_sm_json_field_t *fields,
    size_t field_count,
    char *out,
    size_t out_n
)
{
    char action_esc[128];
    size_t i;
    int n;
    int used = 0;

    if (!action || !out || out_n == 0) return 0;
    if (!ave_sm_json_escape_string(action, action_esc, sizeof(action_esc))) return 0;

    n = snprintf(out, out_n, "{\"type\":\"key_action\",\"action\":\"%s\"", action_esc);
    if (n <= 0 || (size_t)n >= out_n) return 0;
    used = n;

    for (i = 0; i < field_count; i++) {
        char key_esc[128];
        char val_esc[256];
        if (!fields || !fields[i].key || !fields[i].value) continue;
        if (!ave_sm_json_escape_string(fields[i].key, key_esc, sizeof(key_esc))) return 0;
        if (!ave_sm_json_escape_string(fields[i].value, val_esc, sizeof(val_esc))) return 0;
        n = snprintf(out + used, out_n - (size_t)used, ",\"%s\":\"%s\"", key_esc, val_esc);
        if (n <= 0 || (size_t)n >= out_n - (size_t)used) return 0;
        used += n;
    }

    n = snprintf(out + used, out_n - (size_t)used, "}");
    if (n <= 0 || (size_t)n >= out_n - (size_t)used) return 0;
    return 1;
}

void ave_send_json(const char *json)
{
    snprintf(g_last_json, sizeof(g_last_json), "%s", json ? json : "");
}

void ave_sm_go_back_fallback(void)
{
}

/* ---- Test target -------------------------------------------------------- */
void screen_spotlight_show(const char *json_data);
void screen_spotlight_key(int key);

static void reset_last_json(void)
{
    g_last_json[0] = '\0';
}

static int expect_json_contains(const char *needle, const char *msg)
{
    if (!strstr(g_last_json, needle)) {
        fprintf(stderr, "FAIL: %s (json=%s)\n", msg, g_last_json[0] ? g_last_json : "<empty>");
        return 0;
    }
    return 1;
}

static int expect_json_empty(const char *msg)
{
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: %s (json=%s)\n", msg, g_last_json);
        return 0;
    }
    return 1;
}

static int run_case(int trigger_key, const char *trigger_action)
{
    int ok = 1;

    reset_last_json();
    screen_spotlight_key(trigger_key);
    ok &= expect_json_contains(trigger_action, "trigger action should be sent");

    reset_last_json();
    screen_spotlight_key(AVE_KEY_A);
    ok &= expect_json_empty("A should be blocked while loading");

    reset_last_json();
    screen_spotlight_key(AVE_KEY_X);
    ok &= expect_json_empty("X should be blocked while loading");

    lv_tick_inc(10000);
    lv_timer_handler();

    reset_last_json();
    screen_spotlight_key(AVE_KEY_A);
    ok &= expect_json_contains("\"action\":\"buy\"", "A should recover after timeout");

    reset_last_json();
    screen_spotlight_key(AVE_KEY_X);
    ok &= expect_json_contains("\"action\":\"quick_sell\"", "X should recover after timeout");

    return ok;
}

int main(void)
{
    const char *seed_json =
        "{"
        "\"symbol\":\"BONK\","
        "\"price\":\"$0.1\","
        "\"change_24h\":\"+1.0%\","
        "\"token_id\":\"token-1\","
        "\"chain\":\"solana\","
        "\"chart\":[100,110,120],"
        "\"chart_min_y\":\"$0.09\","
        "\"chart_max_y\":\"$0.12\""
        "}";
    int ok = 1;

    lv_init();
    screen_spotlight_show(seed_json);

    ok &= run_case(AVE_KEY_LEFT, "\"action\":\"feed_prev\"");
    ok &= run_case(AVE_KEY_RIGHT, "\"action\":\"feed_next\"");
    ok &= run_case(AVE_KEY_UP, "\"action\":\"kline_interval\"");

    screen_spotlight_show(seed_json);

    reset_last_json();
    screen_spotlight_key(AVE_KEY_UP);
    ok &= expect_json_contains("\"interval\":\"240\"", "UP #1 should move 1H -> 4H");
    lv_tick_inc(10000);
    lv_timer_handler();

    reset_last_json();
    screen_spotlight_key(AVE_KEY_UP);
    ok &= expect_json_contains("\"interval\":\"1440\"", "UP #2 should move 4H -> 1D");
    lv_tick_inc(10000);
    lv_timer_handler();

    reset_last_json();
    screen_spotlight_key(AVE_KEY_UP);
    ok &= expect_json_contains("\"interval\":\"s1\"", "UP #3 should wrap 1D -> L1S");

    if (ok) {
        printf("PASS: spotlight loading timeout protects A/X from permanent lock.\n");
        return 0;
    }

    return 1;
}
