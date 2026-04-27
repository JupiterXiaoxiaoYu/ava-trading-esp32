#include "board_port.h"

#include <stdio.h>

static ava_board_config_t g_config;
static ava_board_io_t g_io;

void ava_board_init(const ava_board_config_t *config, const ava_board_io_t *io) {
    if (config) g_config = *config;
    if (io) g_io = *io;
}

void ava_board_on_network_ready(void) {
    if (g_io.send_json) {
        char msg[256];
        snprintf(msg, sizeof(msg), "{\"type\":\"hello\",\"device_id\":\"%s\",\"app_id\":\"%s\",\"audio_params\":{\"format\":\"%s\",\"sample_rate\":%d,\"channels\":%d}}",
                 g_config.device_id ? g_config.device_id : "device",
                 g_config.app_id ? g_config.app_id : "ava_box",
                 g_config.audio_format == AVA_BOARD_AUDIO_OPUS ? "opus" : "pcm16",
                 g_config.sample_rate ? g_config.sample_rate : 16000,
                 g_config.channels ? g_config.channels : 1);
        g_io.send_json(msg);
    }
}

void ava_board_on_button(const char *action) {
    if (g_io.send_json) {
        char msg[160];
        snprintf(msg, sizeof(msg), "{\"type\":\"key_action\",\"action\":\"%s\"}", action ? action : "");
        g_io.send_json(msg);
    }
}

void ava_board_on_cursor(int cursor, const char *selected_json) {
    if (g_io.send_json) {
        char msg[512];
        snprintf(msg, sizeof(msg), "{\"type\":\"screen_context\",\"cursor\":%d,\"selected\":%s}", cursor, selected_json ? selected_json : "{}");
        g_io.send_json(msg);
    }
}

void ava_board_on_audio_frame(const uint8_t *data, size_t len) {
    if (g_io.send_binary && data && len) g_io.send_binary(data, len);
}

void ava_board_on_listen_start(void) {
    if (g_io.send_json) g_io.send_json("{\"type\":\"listen\",\"state\":\"start\"}");
}

void ava_board_on_listen_stop(void) {
    if (g_io.send_json) g_io.send_json("{\"type\":\"listen\",\"state\":\"stop\"}");
}

void ava_board_on_server_json(const char *json) {
    if (!json) return;
    if (g_io.render_json) g_io.render_json(json);
}
