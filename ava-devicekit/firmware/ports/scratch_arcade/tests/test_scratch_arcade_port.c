#include "ava_scratch_arcade_port.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct sink { char last[1024]; int count; };

static int send_text(const char *json, void *user)
{
    struct sink *s = (struct sink *)user;
    snprintf(s->last, sizeof(s->last), "%s", json);
    s->count++;
    return 1;
}

int main(void)
{
    ava_scratch_arcade_port_t port;
    struct sink s = {{0}, 0};
    ava_scratch_arcade_init(&port, NULL);
    ava_dk_runtime_set_transport(&port.runtime, send_text, &s);
    ava_dk_runtime_on_network_event(&port.runtime, AVA_DK_NET_CONNECTED);
    ava_dk_runtime_set_state(&port.runtime, AVA_DK_STATE_IDLE);

    assert(strcmp(ava_scratch_arcade_default_ota_path(), "/ava/ota/") == 0);
    assert(strcmp(ava_scratch_arcade_default_ws_path(), "/ava/v1/") == 0);
    assert(strcmp(ava_scratch_arcade_action_for_button(AVA_SA_BUTTON_Y, "feed"), "portfolio") == 0);
    assert(strcmp(ava_scratch_arcade_action_for_button(AVA_SA_BUTTON_A, "confirm"), "confirm") == 0);
    assert(ava_scratch_arcade_handle_button(&port, AVA_SA_BUTTON_X, "{\"selected\":{\"symbol\":\"SOL\"}}") == 1);
    assert(strstr(s.last, "\"action\":\"buy\"") != NULL);
    assert(strstr(s.last, "\"selected\"") != NULL);
    return 0;
}
