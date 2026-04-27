#include "ava_scratch_arcade_port.h"

#include <stdio.h>
#include <string.h>

static int emit_action(ava_scratch_arcade_port_t *port, const char *action, const char *context);

void ava_scratch_arcade_init(ava_scratch_arcade_port_t *port, const ava_scratch_arcade_config_t *config)
{
    ava_dk_runtime_config_t runtime_config;
    if (!port) return;
    memset(port, 0, sizeof(*port));
    if (config) port->config = *config;
    runtime_config.app_id = "ava_box";
    runtime_config.transport = "websocket";
    runtime_config.protocol_version = 1;
    runtime_config.sample_rate = 16000;
    runtime_config.channels = 1;
    runtime_config.frame_duration_ms = 60;
    ava_dk_runtime_init(&port->runtime, &runtime_config);
}

const char *ava_scratch_arcade_action_for_button(ava_sa_button_t button, const char *current_screen)
{
    int on_confirm = current_screen && (strcmp(current_screen, "confirm") == 0 || strcmp(current_screen, "limit_confirm") == 0);
    switch (button) {
    case AVA_SA_BUTTON_UP: return "cursor_up";
    case AVA_SA_BUTTON_DOWN: return "cursor_down";
    case AVA_SA_BUTTON_LEFT: return "back";
    case AVA_SA_BUTTON_RIGHT: return "watch";
    case AVA_SA_BUTTON_A: return on_confirm ? "confirm" : "watch";
    case AVA_SA_BUTTON_B: return on_confirm ? "cancel" : "back";
    case AVA_SA_BUTTON_X: return "buy";
    case AVA_SA_BUTTON_Y: return "portfolio";
    case AVA_SA_BUTTON_FN: return "listen";
    default: return "";
    }
}

int ava_scratch_arcade_handle_button(ava_scratch_arcade_port_t *port, ava_sa_button_t button, const char *selection_context_json)
{
    const char *action;
    if (!port) return 0;
    action = ava_scratch_arcade_action_for_button(button, NULL);
    if (strcmp(action, "listen") == 0) {
        return ava_dk_runtime_start_listening(&port->runtime, selection_context_json);
    }
    if (strcmp(action, "confirm") == 0 || strcmp(action, "cancel") == 0) {
        return emit_action(port, action, selection_context_json);
    }
    return emit_action(port, action, selection_context_json);
}

const char *ava_scratch_arcade_default_ota_path(void)
{
    return "/ava/ota/";
}

const char *ava_scratch_arcade_default_ws_path(void)
{
    return "/ava/v1/";
}

static int emit_action(ava_scratch_arcade_port_t *port, const char *action, const char *context)
{
    char msg[768];
    if (!port || !port->runtime.send_text || !action || !action[0]) return 0;
    if (context && context[0]) {
        snprintf(msg, sizeof(msg), "{\"type\":\"key_action\",\"action\":\"%s\",\"context\":%s}", action, context);
    } else {
        snprintf(msg, sizeof(msg), "{\"type\":\"key_action\",\"action\":\"%s\"}", action);
    }
    return port->runtime.send_text(msg, port->runtime.send_user);
}
