#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ave_screen_manager.h"
#include "ave_transport.h"
#include "lvgl/lvgl.h"

#if defined(__GNUC__)
#define AVE_HARNESS_WEAK __attribute__((weak))
#else
#define AVE_HARNESS_WEAK
#endif

AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_12 = {0};
AVE_HARNESS_WEAK const lv_font_t lv_font_montserrat_14 = {0};

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
    if (obj) obj->text_color_full = color.full;
    (void)color;
    (void)part;
}

void lv_obj_set_style_text_font(lv_obj_t *obj, const lv_font_t *font, int part)
{
    if (obj) obj->text_font = font;
    (void)font;
    (void)part;
}

AVE_HARNESS_WEAK void lv_obj_set_style_text_align(
    lv_obj_t *obj,
    lv_text_align_t align,
    lv_style_selector_t selector
)
{
    if (!obj) return;
    obj->text_align = align;
    (void)selector;
}

void lv_obj_set_width(lv_obj_t *obj, int width)
{
    if (!obj) return;
    obj->width = width;
}

void lv_obj_set_size(lv_obj_t *obj, int width, int height)
{
    if (!obj) return;
    obj->width = width;
    obj->height = height;
}

void lv_obj_set_pos(lv_obj_t *obj, int x, int y)
{
    if (!obj) return;
    obj->x = x;
    obj->y = y;
}

void lv_obj_align(lv_obj_t *obj, int align, int x_ofs, int y_ofs)
{
    const int root_w = 320;
    const int root_h = 240;
    int x = x_ofs;
    int y = y_ofs;

    if (!obj) return;

    switch (align) {
        case LV_ALIGN_TOP_LEFT: x = x_ofs; y = y_ofs; break;
        case LV_ALIGN_TOP_MID: x = (root_w - obj->width) / 2 + x_ofs; y = y_ofs; break;
        case LV_ALIGN_TOP_RIGHT: x = root_w - obj->width + x_ofs; y = y_ofs; break;
        case LV_ALIGN_LEFT_MID: x = x_ofs; y = (root_h - obj->height) / 2 + y_ofs; break;
        case LV_ALIGN_CENTER: x = (root_w - obj->width) / 2 + x_ofs; y = (root_h - obj->height) / 2 + y_ofs; break;
        case LV_ALIGN_RIGHT_MID: x = root_w - obj->width + x_ofs; y = (root_h - obj->height) / 2 + y_ofs; break;
        case LV_ALIGN_BOTTOM_LEFT: x = x_ofs; y = root_h - obj->height + y_ofs; break;
        case LV_ALIGN_BOTTOM_MID: x = (root_w - obj->width) / 2 + x_ofs; y = root_h - obj->height + y_ofs; break;
        case LV_ALIGN_BOTTOM_RIGHT: x = root_w - obj->width + x_ofs; y = root_h - obj->height + y_ofs; break;
        default: break;
    }

    obj->x = x;
    obj->y = y;
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

AVE_HARNESS_WEAK lv_obj_t *lv_bar_create(lv_obj_t *parent)
{
    return lv_obj_create(parent);
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

/* Link-only font provider stub used by spotlight/feed screen construction. */
AVE_HARNESS_WEAK const lv_font_t *ave_font_cjk_14(void)
{
    return &lv_font_montserrat_14;
}

#if !defined(VERIFY_SPOTLIGHT)
AVE_HARNESS_WEAK void ave_fmt_price_text(char *buf, size_t n, const char *raw_price)
{
    if (!buf || n == 0) return;
    snprintf(buf, n, "%s", raw_price && raw_price[0] ? raw_price : "$0");
}
#endif

void ave_send_json(const char *json)
{
    snprintf(g_last_json, sizeof(g_last_json), "%s", json ? json : "");
}

#if !defined(VERIFY_SPOTLIGHT)
AVE_HARNESS_WEAK int ave_sm_json_escape_string(const char *src, char *out, size_t out_n)
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

AVE_HARNESS_WEAK int ave_sm_build_key_action_json(
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

AVE_HARNESS_WEAK void ave_sm_go_back_fallback(void)
{
}

AVE_HARNESS_WEAK void ave_sm_go_to_feed(void)
{
}
#endif

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
#include "../../ava-devicekit/reference_apps/ava_box/ui/screen_feed.c"

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
#include "../../ava-devicekit/reference_apps/ava_box/ui/screen_portfolio.c"

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

    screen_portfolio_show("{\"holdings\":[{\"symbol\":\"BONK\",\"source_tag\":\"paper\",\"contract_tail\":\"ABCD\",\"avg_cost_usd\":\"$1\",\"value_usd\":\"$2\",\"pnl\":\"$1\",\"pnl_positive\":true}],\"total_usd\":\"Cash 1 SOL\",\"pnl\":\"$1\",\"mode_label\":\"Paper\",\"chain_label\":\"SOL\"}");
    if (!s_row_sym[0] || strstr(s_row_sym[0]->text, "PAPE") || strstr(s_row_sym[0]->text, "*ABCD") || strcmp(s_row_sym[0]->text, "BONK") != 0) {
        fprintf(stderr, "FAIL: portfolio row leaked source/address suffix into symbol: %s\n", s_row_sym[0] ? s_row_sym[0]->text : "<null>");
        ok = 0;
    }

    memset(s_holdings, 0, sizeof(s_holdings));
    s_holding_count = 1;
    s_sel_idx = 0;
    snprintf(s_holdings[0].addr, sizeof(s_holdings[0].addr), "%s", "addr\"1\\line");
    snprintf(s_holdings[0].chain, sizeof(s_holdings[0].chain), "%s", "sol\"ana");
    snprintf(s_holdings[0].symbol, sizeof(s_holdings[0].symbol), "%s", "SYM\"1");
    snprintf(s_holdings[0].balance_raw, sizeof(s_holdings[0].balance_raw), "%s", "10\".25");

    clear_last_json();
    screen_portfolio_key(AVE_KEY_RIGHT);
    ok &= expect_contains("\"action\":\"portfolio_watch\"", "portfolio watch action");
    ok &= expect_contains("addr\\\"1\\\\line", "portfolio watch addr escaped");
    ok &= expect_contains("sol\\\"ana", "portfolio watch chain escaped");
    ok &= expect_not_contains("addr\"1\\line", "portfolio raw watch addr");

    clear_last_json();
    screen_portfolio_key(AVE_KEY_A);
    ok &= expect_contains("\"action\":\"portfolio_activity_detail\"", "portfolio activity detail action");
    ok &= expect_contains("SYM\\\"1", "portfolio activity detail symbol escaped");
    ok &= expect_not_contains("SYM\"1", "portfolio raw detail symbol");

    clear_last_json();
    screen_portfolio_key(AVE_KEY_X);
    ok &= expect_contains("\"action\":\"portfolio_sell\"", "portfolio sell action");
    ok &= expect_contains("SYM\\\"1", "portfolio sell symbol escaped");
    ok &= expect_contains("10\\\".25", "portfolio sell balance escaped");
    ok &= expect_not_contains("10\".25", "portfolio raw balance");

    return ok ? 0 : 1;
}
#elif defined(VERIFY_SPOTLIGHT)
#define AVE_SPOTLIGHT_SHOW_ONLY 1
#include "../../ava-devicekit/reference_apps/ava_box/ui/screen_spotlight.c"

int main(void)
{
    int ok = 1;
    const char *spotlight_json =
        "{"
        "\"symbol\":\"PEPE\","
        "\"token_id\":\"spot-1\","
        "\"chain\":\"eth\","
        "\"interval\":\"1440\","
        "\"contract_tail\":\"beef\","
        "\"price\":\"$1\","
        "\"change_24h\":\"+1%\","
        "\"chart\":[1,2],"
        "\"chart_min\":\"$1\","
        "\"chart_max\":\"$2\""
        "}";
    const char *spotlight_rich_json =
        "{"
        "\"symbol\":\"BONK\","
        "\"token_id\":\"spot-rich-token-sol\","
        "\"contract\":\"0x2299f25A95A9539f25A95A9539f25A95A953C599\","
        "\"chain\":\"sol\","
        "\"cursor\":0,"
        "\"total\":20,"
        "\"interval\":\"60\","
        "\"price\":\"$1.2300\","
        "\"change_24h\":\"+4.56%\","
        "\"change_positive\":true,"
        "\"risk_level\":\"LOW\","
        "\"is_honeypot\":false,"
        "\"is_mintable\":false,"
        "\"is_freezable\":false,"
        "\"holders\":\"1,234\","
        "\"liquidity\":\"$98.8K\","
        "\"volume_24h\":\"$7.7M\","
        "\"market_cap\":\"$123.5M\","
        "\"top100_concentration\":\"27.3%\","
        "\"contract_short\":\"0x22...C599\","
        "\"chart\":[120,240,360,520,680,740,810,900],"
        "\"chart_min\":\"$1.00\","
        "\"chart_max\":\"$2.00\""
        "}";
    const char *spotlight_numeric_json =
        "{"
        "\"symbol\":\"NUM\","
        "\"token_id\":\"spot-numeric-token-base\","
        "\"mint\":\"0x9988aabbccddeeff112233445566778899008888\","
        "\"chain\":\"eth\","
        "\"interval\":\"60\","
        "\"price\":\"$0.1\","
        "\"change_24h\":\"-1%\","
        "\"change_positive\":0,"
        "\"risk_level\":\"LOW\","
        "\"is_honeypot\":false,"
        "\"is_mintable\":false,"
        "\"is_freezable\":false,"
        "\"holders\":1234,"
        "\"liquidity\":98765,"
        "\"volume_24h\":7654321,"
        "\"market_cap\":123456789,"
        "\"top100_concentration\":27.3,"
        "\"contract_short\":\"0x99...8888\","
        "\"chart\":[100,200],"
        "\"chart_min\":\"$0.09\","
        "\"chart_max\":\"$0.11\""
        "}";
    const char *spotlight_top10_only_json =
        "{"
        "\"symbol\":\"T10\","
        "\"token_id\":\"top10-only\","
        "\"chain\":\"eth\","
        "\"interval\":\"60\","
        "\"price\":\"$1\","
        "\"change_24h\":\"+1%\","
        "\"holders\":\"99\","
        "\"top10_concentration\":\"12.3%\","
        "\"chart\":[100,200],"
        "\"chart_min\":\"$0.09\","
        "\"chart_max\":\"$0.11\""
        "}";

    g_last_json[0] = '\0';
    screen_spotlight_show(spotlight_json);
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (strcmp(s_lbl_sym->text, "PEPE") != 0) {
        fprintf(stderr,
                "FAIL: spotlight top-bar symbol polluted identity: %s\n",
                s_lbl_sym->text);
        ok = 0;
    }
    if (strcmp(s_lbl_tf->text, "1D") != 0) {
        fprintf(stderr,
                "FAIL: spotlight timeframe label did not follow payload interval: %s\n",
                s_lbl_tf->text);
        ok = 0;
    }
    if (s_lbl_pos->y >= 215) {
        fprintf(stderr, "FAIL: spotlight position indicator overlaps divider/bottom bar (y=%d)\n", s_lbl_pos->y);
        ok = 0;
    }
    if (s_lbl_pos->y != s_lbl_stats_row4->y) {
        fprintf(stderr,
                "FAIL: spotlight position indicator should share row-4 with CA (row4_y=%d pos_y=%d)\n",
                s_lbl_stats_row4->y,
                s_lbl_pos->y);
        ok = 0;
    }
    g_last_json[0] = '\0';
    screen_spotlight_show(
        "{"
        "\"symbol\":\"PEPE\","
        "\"token_id\":\"spot-1\","
        "\"chain\":\"eth\","
        "\"interval\":\"s1\","
        "\"price\":\"$1\","
        "\"change_24h\":\"+1%\","
        "\"chart\":[1,2],"
        "\"chart_min\":\"$1\","
        "\"chart_max\":\"$2\""
        "}"
    );
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show(s1) unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (strcmp(s_lbl_tf->text, "L1S") != 0) {
        fprintf(stderr,
                "FAIL: spotlight timeframe label did not map s1 to L1S: %s\n",
                s_lbl_tf->text);
        ok = 0;
    }
    g_last_json[0] = '\0';
    screen_spotlight_show(
        "{"
        "\"symbol\":\"PEPE\","
        "\"token_id\":\"spot-1\","
        "\"chain\":\"eth\","
        "\"interval\":\"1\","
        "\"price\":\"$1\","
        "\"change_24h\":\"+1%\","
        "\"chart\":[1,2],"
        "\"chart_min\":\"$1\","
        "\"chart_max\":\"$2\""
        "}"
    );
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show(1m) unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (strcmp(s_lbl_tf->text, "L1M") != 0) {
        fprintf(stderr,
                "FAIL: spotlight timeframe label did not map 1 to L1M: %s\n",
                s_lbl_tf->text);
        ok = 0;
    }

    g_last_json[0] = '\0';
    screen_spotlight_show(spotlight_rich_json);
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show(rich) unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row1->text, "Risk:LOW") ||
        !strstr(s_lbl_stats_row1->text, "Mint:NO") ||
        !strstr(s_lbl_stats_row1->text, "Freeze:NO")) {
        fprintf(stderr, "FAIL: spotlight row1 missing Risk/Mint/Freeze: %s\n", s_lbl_stats_row1->text);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row2->text, "Vol24h:$7.7M") ||
        !strstr(s_lbl_stats_row2->text, "Liq:$98.8K") ||
        !strstr(s_lbl_stats_row2->text, "Mcap:$123.5M")) {
        fprintf(stderr, "FAIL: spotlight row2 missing Vol24h/Liq/Mcap: %s\n", s_lbl_stats_row2->text);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row3->text, "Holders:1,234") ||
        !strstr(s_lbl_stats_row3->text, "Top100:27.3%")) {
        fprintf(stderr, "FAIL: spotlight row3 missing Holders/Top100: %s\n", s_lbl_stats_row3->text);
        ok = 0;
    }
    if (strcmp(s_lbl_stats_row4->text, "CA:0x2299...53C599") != 0) {
        fprintf(stderr, "FAIL: spotlight row4 missing compact CA (first6/last6): %s\n", s_lbl_stats_row4->text);
        ok = 0;
    }
    if (s_lbl_origin->text[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight origin hint should be empty by default: %s\n", s_lbl_origin->text);
        ok = 0;
    }
    if (strcmp(s_lbl_watch_star->text, "☆") != 0) {
        fprintf(stderr, "FAIL: spotlight star should default to unwatchlisted: %s\n", s_lbl_watch_star->text);
        ok = 0;
    }
    if (strcmp(s_lbl_pos->text, "<1/20>") != 0) {
        fprintf(stderr, "FAIL: spotlight row4 missing page marker text: %s\n", s_lbl_pos->text);
        ok = 0;
    }
    if (s_lbl_pos->width < 40) {
        fprintf(stderr, "FAIL: spotlight page marker width should reserve a right column (w=%d)\n", s_lbl_pos->width);
        ok = 0;
    }
    if ((s_lbl_pos->x + s_lbl_pos->width) != 316) {
        fprintf(stderr,
                "FAIL: spotlight page marker right edge drifted (x=%d w=%d)\n",
                s_lbl_pos->x,
                s_lbl_pos->width);
        ok = 0;
    }
    if ((s_lbl_stats_row4->x + s_lbl_stats_row4->width) >= s_lbl_pos->x) {
        fprintf(stderr,
                "FAIL: spotlight row4 CA overlaps page marker (ca_right=%d pos_left=%d)\n",
                s_lbl_stats_row4->x + s_lbl_stats_row4->width,
                s_lbl_pos->x);
        ok = 0;
    }
    if (s_lbl_watch_star->x <= (s_lbl_stats_row4->x + s_lbl_stats_row4->width)) {
        fprintf(stderr,
                "FAIL: spotlight watchlist star overlaps CA (star_x=%d ca_right=%d)\n",
                s_lbl_watch_star->x,
                s_lbl_stats_row4->x + s_lbl_stats_row4->width);
        ok = 0;
    }

    g_last_json[0] = '\0';
    screen_spotlight_show(spotlight_numeric_json);
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show(numeric) unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row2->text, "Vol24h:7654321") ||
        !strstr(s_lbl_stats_row2->text, "Liq:98765") ||
        !strstr(s_lbl_stats_row2->text, "Mcap:123456789")) {
        fprintf(stderr, "FAIL: spotlight row2 numeric scalars not parsed: %s\n", s_lbl_stats_row2->text);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row3->text, "Holders:1234") ||
        !strstr(s_lbl_stats_row3->text, "Top100:27.3")) {
        fprintf(stderr, "FAIL: spotlight row3 numeric scalars not parsed: %s\n", s_lbl_stats_row3->text);
        ok = 0;
    }
    if (!strstr(s_lbl_change->text, "-1%")) {
        fprintf(stderr, "FAIL: spotlight numeric change_positive payload regressed change label: %s\n", s_lbl_change->text);
        ok = 0;
    }
    if (strcmp(s_lbl_stats_row4->text, "CA:0x9988...008888") != 0) {
        fprintf(stderr, "FAIL: spotlight mint-based compact CA regressed: %s\n", s_lbl_stats_row4->text);
        ok = 0;
    }

    g_last_json[0] = '\0';
    screen_spotlight_show(spotlight_top10_only_json);
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight show(top10-only) unexpectedly sent key_action JSON: %s\n", g_last_json);
        ok = 0;
    }
    if (!strstr(s_lbl_stats_row3->text, "Top100:N/A")) {
        fprintf(stderr, "FAIL: spotlight must not backfill Top100 from top10 field: %s\n", s_lbl_stats_row3->text);
        ok = 0;
    }
    if (strstr(s_lbl_stats_row3->text, "12.3%")) {
        fprintf(stderr, "FAIL: spotlight leaked top10_concentration into Top100 row: %s\n", s_lbl_stats_row3->text);
        ok = 0;
    }
    if (s_lbl_pos->text[0] != '\0') {
        fprintf(stderr, "FAIL: spotlight page marker should be empty without cursor/total: %s\n", s_lbl_pos->text);
        ok = 0;
    }
    const int expected_row4_width = FOOTER_W - FOOTER_ROW4_STAR_W - FOOTER_ROW4_HINT_GAP;
    if (s_lbl_stats_row4->width != expected_row4_width) {
        fprintf(stderr, "FAIL: spotlight CA row should reclaim width while reserving star column (w=%d want=%d)\n",
                s_lbl_stats_row4->width, expected_row4_width);
        ok = 0;
    }

    g_last_json[0] = '\0';
    const char *spotlight_watchlist_cursor_json =
        "{"
        "\"symbol\":\"BONK\","
        "\"token_id\":\"spot-watchlist\","
        "\"chain\":\"sol\","
        "\"cursor\":1,"
        "\"total\":3,"
        "\"price\":\"$1.23\","
        "\"change_24h\":\"+2.2%\","
        "\"change_positive\":true,"
        "\"risk_level\":\"LOW\","
        "\"is_honeypot\":false,"
        "\"is_mintable\":false,"
        "\"is_freezable\":false,"
        "\"holders\":\"1,234\","
        "\"liquidity\":\"$120K\","
        "\"volume_24h\":\"$88K\","
        "\"market_cap\":\"$5M\","
        "\"top100_concentration\":\"33.3%\","
        "\"contract\":\"0x2299f25A95A9539f25A95A9539f25A95A953C599\","
        "\"is_watchlisted\":true,"
        "\"origin_hint\":\"From Signal Watchlist\","
        "\"chart\":[200,400,600,800],"
        "\"chart_min\":\"$1.00\","
        "\"chart_max\":\"$2.00\""
        "}";
    screen_spotlight_show(spotlight_watchlist_cursor_json);
    if (strcmp(s_lbl_watch_star->text, "★") != 0) {
        fprintf(stderr, "FAIL: spotlight watchlist star missing on combined layout: %s\n", s_lbl_watch_star->text);
        ok = 0;
    }
    if (strcmp(s_lbl_origin->text, "From Signal Watchlist") != 0) {
        fprintf(stderr, "FAIL: spotlight origin hint missing on combined layout: %s\n", s_lbl_origin->text);
        ok = 0;
    }
    if (strcmp(s_lbl_pos->text, "<2/3>") != 0) {
        fprintf(stderr, "FAIL: spotlight page marker not showing with watchlist star: %s\n", s_lbl_pos->text);
        ok = 0;
    }
    const int expected_row4_width_with_marker =
        FOOTER_W - FOOTER_ROW4_STAR_W - FOOTER_ROW4_HINT_GAP - FOOTER_PAGE_W - FOOTER_ROW4_GAP;
    if (s_lbl_stats_row4->width != expected_row4_width_with_marker) {
        fprintf(stderr,
                "FAIL: spotlight row4 width without marker should match reservation: w=%d want=%d\n",
                s_lbl_stats_row4->width, expected_row4_width_with_marker);
        ok = 0;
    }
    if (s_lbl_watch_star->x <= (s_lbl_stats_row4->x + s_lbl_stats_row4->width)) {
        fprintf(stderr,
                "FAIL: spotlight star overlaps CA on combined layout: star_x=%d ca_right=%d\n",
                s_lbl_watch_star->x,
                s_lbl_stats_row4->x + s_lbl_stats_row4->width);
        ok = 0;
    }
    if ((s_lbl_origin->x + s_lbl_origin->width) >= (s_lbl_tf->x - 4)) {
        fprintf(stderr,
                "FAIL: spotlight origin hint overlaps timeframe badge: origin_right=%d tf_x=%d\n",
                s_lbl_origin->x + s_lbl_origin->width,
                s_lbl_tf->x);
        ok = 0;
    }

    g_last_json[0] = '\0';
    screen_spotlight_key(AVE_KEY_A);
    screen_spotlight_key(AVE_KEY_X);
    screen_spotlight_key(AVE_KEY_UP);
    screen_spotlight_key(AVE_KEY_B);
    if (g_last_json[0] != '\0') {
        fprintf(stderr, "FAIL: AVE_SPOTLIGHT_SHOW_ONLY key path unexpectedly sent JSON: %s\n", g_last_json);
        ok = 0;
    }

    return ok ? 0 : 1;
}
#else
#error "Define VERIFY_FEED, VERIFY_PORTFOLIO, or VERIFY_SPOTLIGHT"
#endif
