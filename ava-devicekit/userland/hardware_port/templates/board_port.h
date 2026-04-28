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
    int sample_rate;
    int channels;
    ava_board_audio_format_t audio_format;
} ava_board_config_t;

typedef struct {
    void (*send_json)(const char *json);
    void (*send_binary)(const uint8_t *data, size_t len);
    void (*render_json)(const char *display_json);
    void (*play_audio)(const uint8_t *data, size_t len, const char *content_type);
    void (*start_ota_check)(void);
    void (*log)(const char *message);
} ava_board_io_t;

void ava_board_init(const ava_board_config_t *config, const ava_board_io_t *io);
void ava_board_on_network_ready(void);
void ava_board_on_button(const char *action);
void ava_board_on_cursor(int cursor, const char *selected_json);
void ava_board_on_audio_frame(const uint8_t *data, size_t len);
void ava_board_on_listen_start(void);
void ava_board_on_listen_stop(void);
void ava_board_on_server_json(const char *json);
void ava_board_send_ack(const char *message_id);
const char *ava_board_extract_message_id(const char *json);

#ifdef __cplusplus
}
#endif
