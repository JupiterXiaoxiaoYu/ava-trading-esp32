#ifndef AVA_DEVICEKIT_RUNTIME_H
#define AVA_DEVICEKIT_RUNTIME_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    AVA_DK_STATE_STARTING = 0,
    AVA_DK_STATE_WIFI_CONFIGURING,
    AVA_DK_STATE_ACTIVATING,
    AVA_DK_STATE_IDLE,
    AVA_DK_STATE_CONNECTING,
    AVA_DK_STATE_LISTENING,
    AVA_DK_STATE_SPEAKING,
    AVA_DK_STATE_UPGRADING,
    AVA_DK_STATE_ERROR,
} ava_dk_device_state_t;

typedef enum {
    AVA_DK_NET_SCANNING = 0,
    AVA_DK_NET_CONNECTING,
    AVA_DK_NET_CONNECTED,
    AVA_DK_NET_DISCONNECTED,
    AVA_DK_NET_WIFI_CONFIG_ENTER,
    AVA_DK_NET_WIFI_CONFIG_EXIT,
} ava_dk_network_event_t;

typedef int (*ava_dk_send_text_fn)(const char *json, void *user);

typedef struct {
    const char *app_id;
    const char *transport;
    int protocol_version;
    int sample_rate;
    int channels;
    int frame_duration_ms;
} ava_dk_runtime_config_t;

typedef struct {
    ava_dk_runtime_config_t config;
    ava_dk_send_text_fn send_text;
    void *send_user;
    ava_dk_device_state_t state;
    int network_connected;
    int audio_channel_open;
} ava_dk_runtime_t;

void ava_dk_runtime_init(ava_dk_runtime_t *rt, const ava_dk_runtime_config_t *config);
void ava_dk_runtime_set_transport(ava_dk_runtime_t *rt, ava_dk_send_text_fn send_text, void *user);
ava_dk_device_state_t ava_dk_runtime_state(const ava_dk_runtime_t *rt);
void ava_dk_runtime_set_state(ava_dk_runtime_t *rt, ava_dk_device_state_t state);
int ava_dk_runtime_on_network_event(ava_dk_runtime_t *rt, ava_dk_network_event_t event);
int ava_dk_runtime_send_hello(ava_dk_runtime_t *rt);
int ava_dk_runtime_start_listening(ava_dk_runtime_t *rt, const char *selection_context_json);
int ava_dk_runtime_stop_listening(ava_dk_runtime_t *rt);
int ava_dk_runtime_send_wake_detect(ava_dk_runtime_t *rt, const char *wake_word, const char *selection_context_json);
int ava_dk_runtime_build_hello_json(const ava_dk_runtime_config_t *config, char *out, size_t out_n);
int ava_dk_runtime_build_listen_json(const char *state, const char *text, const char *selection_context_json, char *out, size_t out_n);

#ifdef __cplusplus
}
#endif

#endif /* AVA_DEVICEKIT_RUNTIME_H */
