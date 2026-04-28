#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    AVA_BOARD_AUDIO_PCM16 = 0,
    AVA_BOARD_AUDIO_OPUS = 1,
} ava_board_audio_format_t;

typedef struct {
    const char *device_id;
    const char *app_id;
    const char *firmware_version;
    const char *websocket_url;
    const char *http_fallback_url;
    const char *bearer_token;
    const char *device_public_key;
    const char *secure_element_profile;
    int sample_rate;
    int channels;
    uint32_t heartbeat_interval_ms;
    uint32_t reconnect_interval_ms;
    ava_board_audio_format_t audio_format;
} ava_board_config_t;

typedef struct {
    void (*send_json)(const char *json);
    void (*send_binary)(const uint8_t *data, size_t len);
    int (*send_http_json)(const char *url, const char *json, const char *bearer_token);
    void (*render_json)(const char *display_json);
    void (*play_audio)(const uint8_t *data, size_t len, const char *content_type);
    void (*start_ota_check)(void);
    int (*sign_challenge)(const char *challenge_json, char *out_signature, size_t out_signature_len);
    uint32_t (*millis)(void);
    void (*log)(const char *message);
} ava_board_io_t;

void ava_board_init(const ava_board_config_t *config, const ava_board_io_t *io);
void ava_board_on_network_ready(void);
void ava_board_on_transport_connected(void);
void ava_board_on_transport_disconnected(void);
void ava_board_on_tick(void);
void ava_board_on_button(const char *action);
void ava_board_on_cursor(int cursor, const char *selected_json);
void ava_board_send_input_event(const char *source, const char *kind, const char *code, const char *semantic_action, const char *context_json);
void ava_board_on_audio_frame(const uint8_t *data, size_t len);
void ava_board_on_listen_start(void);
void ava_board_on_listen_stop(void);
void ava_board_on_server_json(const char *json);
void ava_board_send_ack(const char *message_id);
void ava_board_send_heartbeat(void);
int ava_board_send_http_fallback(const char *json);
int ava_board_send_challenge_response(const char *challenge_json);
const char *ava_board_extract_message_id(const char *json);

#ifdef __cplusplus
}
#endif
