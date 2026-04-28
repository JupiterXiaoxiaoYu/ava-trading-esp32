#include "board_port.h"

#include <stdio.h>
#include <string.h>

static ava_board_config_t g_config;
static ava_board_io_t g_io;
static int g_transport_connected;
static uint32_t g_last_heartbeat_ms;
static uint32_t g_last_reconnect_ms;

static const char *safe_str(const char *value, const char *fallback) {
    return value ? value : fallback;
}

static uint32_t now_ms(void) {
    return g_io.millis ? g_io.millis() : 0;
}

void ava_board_init(const ava_board_config_t *config, const ava_board_io_t *io) {
    if (config) g_config = *config;
    if (io) g_io = *io;
}

void ava_board_on_network_ready(void) {
    if (g_io.send_json) {
        char msg[512];
        snprintf(msg, sizeof(msg), "{\"type\":\"hello\",\"device_id\":\"%s\",\"app_id\":\"%s\",\"firmware_version\":\"%s\",\"device_public_key\":\"%s\",\"secure_element_profile\":\"%s\",\"audio_params\":{\"format\":\"%s\",\"sample_rate\":%d,\"channels\":%d}}",
                 safe_str(g_config.device_id, "device"),
                 safe_str(g_config.app_id, "ava_box"),
                 safe_str(g_config.firmware_version, ""),
                 safe_str(g_config.device_public_key, ""),
                 safe_str(g_config.secure_element_profile, ""),
                 g_config.audio_format == AVA_BOARD_AUDIO_OPUS ? "opus" : "pcm16",
                 g_config.sample_rate ? g_config.sample_rate : 16000,
                 g_config.channels ? g_config.channels : 1);
        g_io.send_json(msg);
    }
}

void ava_board_on_transport_connected(void) {
    g_transport_connected = 1;
    g_last_heartbeat_ms = now_ms();
    ava_board_on_network_ready();
}

void ava_board_on_transport_disconnected(void) {
    g_transport_connected = 0;
    g_last_reconnect_ms = now_ms();
}

void ava_board_on_tick(void) {
    uint32_t now = now_ms();
    uint32_t heartbeat_ms = g_config.heartbeat_interval_ms ? g_config.heartbeat_interval_ms : 15000;
    uint32_t reconnect_ms = g_config.reconnect_interval_ms ? g_config.reconnect_interval_ms : 5000;
    if (g_transport_connected && now && now - g_last_heartbeat_ms >= heartbeat_ms) {
        ava_board_send_heartbeat();
        g_last_heartbeat_ms = now;
    }
    if (!g_transport_connected && now && now - g_last_reconnect_ms >= reconnect_ms) {
        g_last_reconnect_ms = now;
        if (g_io.log) g_io.log("transport disconnected; board port should reconnect websocket");
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

void ava_board_send_input_event(const char *source, const char *kind, const char *code, const char *semantic_action, const char *context_json) {
    if (!g_io.send_json) return;
    char msg[768];
    snprintf(msg, sizeof(msg), "{\"type\":\"input_event\",\"source\":\"%s\",\"kind\":\"%s\",\"code\":\"%s\",\"semantic_action\":\"%s\",\"context\":%s}",
             safe_str(source, "button"),
             safe_str(kind, "press"),
             safe_str(code, ""),
             safe_str(semantic_action, ""),
             context_json ? context_json : "{}");
    g_io.send_json(msg);
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
    if (strstr(json, "\"type\":\"device_command\"") && strstr(json, "\"command\":\"ota_check\"")) {
        if (g_io.start_ota_check) g_io.start_ota_check();
        const char *message_id = ava_board_extract_message_id(json);
        if (message_id) ava_board_send_ack(message_id);
        return;
    }
    if (g_io.render_json) g_io.render_json(json);
    const char *message_id = ava_board_extract_message_id(json);
    if (message_id) ava_board_send_ack(message_id);
}

void ava_board_send_ack(const char *message_id) {
    if (!g_io.send_json || !message_id || !message_id[0]) return;
    char msg[192];
    snprintf(msg, sizeof(msg), "{\"type\":\"ack\",\"message_id\":\"%s\"}", message_id);
    g_io.send_json(msg);
}

void ava_board_send_heartbeat(void) {
    if (!g_io.send_json) return;
    char msg[256];
    snprintf(msg, sizeof(msg), "{\"type\":\"heartbeat\",\"device_id\":\"%s\",\"app_id\":\"%s\"}",
             safe_str(g_config.device_id, "device"),
             safe_str(g_config.app_id, "ava_box"));
    g_io.send_json(msg);
}

int ava_board_send_http_fallback(const char *json) {
    if (!g_io.send_http_json || !g_config.http_fallback_url || !json) return -1;
    return g_io.send_http_json(g_config.http_fallback_url, json, g_config.bearer_token);
}

int ava_board_send_challenge_response(const char *challenge_json) {
    if (!g_io.sign_challenge || !g_io.send_json || !challenge_json) return -1;
    char sig[256];
    if (g_io.sign_challenge(challenge_json, sig, sizeof(sig)) != 0) return -1;
    char msg[640];
    snprintf(msg, sizeof(msg), "{\"type\":\"device_identity\",\"device_id\":\"%s\",\"device_public_key\":\"%s\",\"challenge\":%s,\"signature\":\"%s\"}",
             safe_str(g_config.device_id, "device"),
             safe_str(g_config.device_public_key, ""),
             challenge_json,
             sig);
    g_io.send_json(msg);
    return 0;
}

const char *ava_board_extract_message_id(const char *json) {
    static char id[96];
    const char *key = "\"message_id\":\"";
    const char *start = strstr(json, key);
    if (!start) return NULL;
    start += strlen(key);
    const char *end = strchr(start, '"');
    if (!end) return NULL;
    size_t n = (size_t)(end - start);
    if (n == 0 || n >= sizeof(id)) return NULL;
    memcpy(id, start, n);
    id[n] = '\0';
    return id;
}
