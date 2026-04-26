#include "ava_devicekit_runtime.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct sink {
    char last[1024];
    int count;
};

static int send_text(const char *json, void *user)
{
    struct sink *s = (struct sink *)user;
    snprintf(s->last, sizeof(s->last), "%s", json);
    s->count++;
    return 1;
}

int main(void)
{
    ava_dk_runtime_t rt;
    struct sink s = {{0}, 0};
    char msg[512];

    ava_dk_runtime_init(&rt, NULL);
    ava_dk_runtime_set_transport(&rt, send_text, &s);
    assert(ava_dk_runtime_state(&rt) == AVA_DK_STATE_STARTING);
    assert(ava_dk_runtime_build_hello_json(&rt.config, msg, sizeof(msg)) == 1);
    assert(strstr(msg, "\"type\":\"hello\"") != NULL);
    assert(strstr(msg, "\"devicekit\":true") != NULL);

    ava_dk_runtime_on_network_event(&rt, AVA_DK_NET_WIFI_CONFIG_ENTER);
    assert(ava_dk_runtime_state(&rt) == AVA_DK_STATE_WIFI_CONFIGURING);
    ava_dk_runtime_on_network_event(&rt, AVA_DK_NET_CONNECTED);
    assert(ava_dk_runtime_state(&rt) == AVA_DK_STATE_ACTIVATING);
    ava_dk_runtime_set_state(&rt, AVA_DK_STATE_IDLE);

    assert(ava_dk_runtime_start_listening(&rt, "{\"selected\":{\"symbol\":\"SOL\"}}") == 1);
    assert(s.count == 2);
    assert(strstr(s.last, "\"state\":\"start\"") != NULL);
    assert(ava_dk_runtime_state(&rt) == AVA_DK_STATE_LISTENING);

    assert(ava_dk_runtime_send_wake_detect(&rt, "ava", "{\"selected\":{\"symbol\":\"SOL\"}}") == 1);
    assert(strstr(s.last, "\"state\":\"detect\"") != NULL);
    assert(strstr(s.last, "\"text\":\"ava\"") != NULL);

    assert(ava_dk_runtime_stop_listening(&rt) == 1);
    assert(ava_dk_runtime_state(&rt) == AVA_DK_STATE_IDLE);
    return 0;
}
