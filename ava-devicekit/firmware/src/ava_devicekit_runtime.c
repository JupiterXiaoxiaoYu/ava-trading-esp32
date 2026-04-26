#include "ava_devicekit_runtime.h"

#include <stdio.h>
#include <string.h>

static ava_dk_runtime_config_t default_config(void);
static int emit(ava_dk_runtime_t *rt, const char *json);
static const char *safe_str(const char *value, const char *fallback);

void ava_dk_runtime_init(ava_dk_runtime_t *rt, const ava_dk_runtime_config_t *config)
{
    if (!rt) return;
    memset(rt, 0, sizeof(*rt));
    rt->config = config ? *config : default_config();
    if (!rt->config.app_id) rt->config.app_id = "ava_box";
    if (!rt->config.transport) rt->config.transport = "websocket";
    if (rt->config.protocol_version <= 0) rt->config.protocol_version = 1;
    if (rt->config.sample_rate <= 0) rt->config.sample_rate = 16000;
    if (rt->config.channels <= 0) rt->config.channels = 1;
    if (rt->config.frame_duration_ms <= 0) rt->config.frame_duration_ms = 60;
    rt->state = AVA_DK_STATE_STARTING;
}

void ava_dk_runtime_set_transport(ava_dk_runtime_t *rt, ava_dk_send_text_fn send_text, void *user)
{
    if (!rt) return;
    rt->send_text = send_text;
    rt->send_user = user;
}

ava_dk_device_state_t ava_dk_runtime_state(const ava_dk_runtime_t *rt)
{
    return rt ? rt->state : AVA_DK_STATE_ERROR;
}

void ava_dk_runtime_set_state(ava_dk_runtime_t *rt, ava_dk_device_state_t state)
{
    if (!rt) return;
    rt->state = state;
}

int ava_dk_runtime_on_network_event(ava_dk_runtime_t *rt, ava_dk_network_event_t event)
{
    if (!rt) return 0;
    switch (event) {
    case AVA_DK_NET_CONNECTED:
        rt->network_connected = 1;
        if (rt->state == AVA_DK_STATE_STARTING || rt->state == AVA_DK_STATE_WIFI_CONFIGURING) {
            rt->state = AVA_DK_STATE_ACTIVATING;
        }
        return 1;
    case AVA_DK_NET_DISCONNECTED:
        rt->network_connected = 0;
        rt->audio_channel_open = 0;
        if (rt->state == AVA_DK_STATE_CONNECTING || rt->state == AVA_DK_STATE_LISTENING || rt->state == AVA_DK_STATE_SPEAKING) {
            rt->state = AVA_DK_STATE_IDLE;
        }
        return 1;
    case AVA_DK_NET_WIFI_CONFIG_ENTER:
        rt->state = AVA_DK_STATE_WIFI_CONFIGURING;
        return 1;
    case AVA_DK_NET_WIFI_CONFIG_EXIT:
        rt->state = AVA_DK_STATE_STARTING;
        return 1;
    default:
        return 1;
    }
}

int ava_dk_runtime_send_hello(ava_dk_runtime_t *rt)
{
    char msg[384];
    if (!rt) return 0;
    if (!ava_dk_runtime_build_hello_json(&rt->config, msg, sizeof(msg))) return 0;
    return emit(rt, msg);
}

int ava_dk_runtime_start_listening(ava_dk_runtime_t *rt, const char *selection_context_json)
{
    char msg[768];
    if (!rt || !rt->network_connected) return 0;
    if (!rt->audio_channel_open) {
        rt->state = AVA_DK_STATE_CONNECTING;
        rt->audio_channel_open = 1;
        if (!ava_dk_runtime_send_hello(rt)) return 0;
    }
    rt->state = AVA_DK_STATE_LISTENING;
    if (!ava_dk_runtime_build_listen_json("start", NULL, selection_context_json, msg, sizeof(msg))) return 0;
    return emit(rt, msg);
}

int ava_dk_runtime_stop_listening(ava_dk_runtime_t *rt)
{
    char msg[256];
    if (!rt || !rt->audio_channel_open) return 0;
    rt->state = AVA_DK_STATE_IDLE;
    if (!ava_dk_runtime_build_listen_json("stop", NULL, NULL, msg, sizeof(msg))) return 0;
    return emit(rt, msg);
}

int ava_dk_runtime_send_wake_detect(ava_dk_runtime_t *rt, const char *wake_word, const char *selection_context_json)
{
    char msg[1024];
    if (!rt || !rt->network_connected) return 0;
    if (!rt->audio_channel_open && !ava_dk_runtime_start_listening(rt, selection_context_json)) return 0;
    if (!ava_dk_runtime_build_listen_json("detect", wake_word, selection_context_json, msg, sizeof(msg))) return 0;
    return emit(rt, msg);
}

int ava_dk_runtime_build_hello_json(const ava_dk_runtime_config_t *config, char *out, size_t out_n)
{
    ava_dk_runtime_config_t cfg = config ? *config : default_config();
    if (!out || out_n == 0) return 0;
    return snprintf(
        out,
        out_n,
        "{\"type\":\"hello\",\"version\":%d,\"transport\":\"%s\",\"features\":{\"mcp\":false,\"devicekit\":true},\"audio_params\":{\"format\":\"opus\",\"sample_rate\":%d,\"channels\":%d,\"frame_duration\":%d},\"app_id\":\"%s\"}",
        cfg.protocol_version > 0 ? cfg.protocol_version : 1,
        safe_str(cfg.transport, "websocket"),
        cfg.sample_rate > 0 ? cfg.sample_rate : 16000,
        cfg.channels > 0 ? cfg.channels : 1,
        cfg.frame_duration_ms > 0 ? cfg.frame_duration_ms : 60,
        safe_str(cfg.app_id, "ava_box")) < (int)out_n;
}

int ava_dk_runtime_build_listen_json(const char *state, const char *text, const char *selection_context_json, char *out, size_t out_n)
{
    if (!out || out_n == 0) return 0;
    if (text && text[0] && selection_context_json && selection_context_json[0]) {
        return snprintf(out, out_n, "{\"type\":\"listen\",\"state\":\"%s\",\"text\":\"%s\",\"context\":%s}", safe_str(state, "start"), text, selection_context_json) < (int)out_n;
    }
    if (text && text[0]) {
        return snprintf(out, out_n, "{\"type\":\"listen\",\"state\":\"%s\",\"text\":\"%s\"}", safe_str(state, "start"), text) < (int)out_n;
    }
    if (selection_context_json && selection_context_json[0]) {
        return snprintf(out, out_n, "{\"type\":\"listen\",\"state\":\"%s\",\"context\":%s}", safe_str(state, "start"), selection_context_json) < (int)out_n;
    }
    return snprintf(out, out_n, "{\"type\":\"listen\",\"state\":\"%s\"}", safe_str(state, "start")) < (int)out_n;
}

static ava_dk_runtime_config_t default_config(void)
{
    ava_dk_runtime_config_t cfg;
    cfg.app_id = "ava_box";
    cfg.transport = "websocket";
    cfg.protocol_version = 1;
    cfg.sample_rate = 16000;
    cfg.channels = 1;
    cfg.frame_duration_ms = 60;
    return cfg;
}

static int emit(ava_dk_runtime_t *rt, const char *json)
{
    if (!rt || !rt->send_text || !json) return 0;
    return rt->send_text(json, rt->send_user);
}

static const char *safe_str(const char *value, const char *fallback)
{
    return value && value[0] ? value : fallback;
}
