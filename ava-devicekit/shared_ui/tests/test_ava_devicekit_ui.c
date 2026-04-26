#include "ava_devicekit_ui.h"

#include <stdio.h>
#include <string.h>

static int g_feed_show = 0;
static int g_confirm_show = 0;
static int g_feed_key = 0;
static int g_cancel_timers = 0;
static char g_sent[1024];

static void show_feed(const char *json, void *user)
{
    (void)user;
    if (json && strstr(json, "BONK")) g_feed_show++;
}

static void show_confirm(const char *json, void *user)
{
    (void)user;
    if (json && strstr(json, "trade_id")) g_confirm_show++;
}

static void key_feed(ava_dk_key_t key, void *user)
{
    (void)user;
    if (key == AVA_DK_KEY_A) g_feed_key++;
}

static int selection_context(char *out, size_t out_n, void *user)
{
    (void)user;
    return snprintf(out, out_n, "{\"screen\":\"feed\",\"selected\":{\"symbol\":\"BONK\"}}") < (int)out_n;
}

static void cancel_timers(void *user)
{
    (void)user;
    g_cancel_timers++;
}

static void send_json(const char *json, void *user)
{
    (void)user;
    snprintf(g_sent, sizeof(g_sent), "%s", json ? json : "");
}

static int expect(int cond, const char *msg)
{
    if (!cond) {
        fprintf(stderr, "FAIL: %s\n", msg);
        return 1;
    }
    return 0;
}

int main(void)
{
    ava_dk_ui_runtime_t rt;
    char msg[512];
    int failures = 0;

    ava_dk_ui_init(&rt);
    ava_dk_ui_set_transport(&rt, send_json, NULL);
    ava_dk_ui_register_screen(&rt, AVA_DK_SCREEN_FEED, (ava_dk_screen_vtable_t){show_feed, key_feed, selection_context, cancel_timers, NULL});
    ava_dk_ui_register_screen(&rt, AVA_DK_SCREEN_CONFIRM, (ava_dk_screen_vtable_t){show_confirm, NULL, NULL, cancel_timers, NULL});

    failures += expect(ava_dk_ui_screen_from_name("spotlight") == AVA_DK_SCREEN_SPOTLIGHT, "screen mapping");
    failures += expect(ava_dk_ui_handle_display_json(&rt, "{\"type\":\"display\",\"screen\":\"feed\",\"data\":{\"tokens\":[{\"symbol\":\"BONK\"}]}}") == 1, "feed display handled");
    failures += expect(g_feed_show == 1, "feed show called");
    failures += expect(ava_dk_ui_current_screen(&rt) == AVA_DK_SCREEN_FEED, "current feed");
    failures += expect(ava_dk_ui_key_press(&rt, AVA_DK_KEY_A) == 1 && g_feed_key == 1, "key routed to feed");
    failures += expect(ava_dk_ui_key_press(&rt, AVA_DK_KEY_Y) == 1 && strstr(g_sent, "portfolio") != NULL, "global portfolio key emitted");
    failures += expect(ava_dk_ui_key_press(&rt, AVA_DK_KEY_FN) == 1 && strstr(g_sent, "listen_detect") != NULL && strstr(g_sent, "BONK") != NULL, "fn listen with context emitted");
    failures += expect(ava_dk_ui_handle_display_json(&rt, "{\"type\":\"display\",\"screen\":\"confirm\",\"data\":{\"trade_id\":\"t1\"}}") == 1, "confirm display handled");
    failures += expect(g_confirm_show == 1 && ava_dk_ui_current_screen(&rt) == AVA_DK_SCREEN_CONFIRM, "confirm current");
    failures += expect(g_cancel_timers > 0, "transition cancels timers");
    failures += expect(ava_dk_ui_build_key_action_json("buy", "\"token_id\":\"abc-solana\"", msg, sizeof(msg)) == 1 && strstr(msg, "token_id") != NULL, "build key action");
    failures += expect(ava_dk_ui_build_listen_detect_json("hello Ava", "{\"screen\":\"feed\"}", msg, sizeof(msg)) == 1 && strstr(msg, "hello Ava") != NULL, "build listen detect");

    return failures ? 1 : 0;
}
