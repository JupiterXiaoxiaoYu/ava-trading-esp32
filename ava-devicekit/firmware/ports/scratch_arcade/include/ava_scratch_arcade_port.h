#ifndef AVA_SCRATCH_ARCADE_PORT_H
#define AVA_SCRATCH_ARCADE_PORT_H

#include "ava_devicekit_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    AVA_SA_BUTTON_UP = 0,
    AVA_SA_BUTTON_DOWN,
    AVA_SA_BUTTON_LEFT,
    AVA_SA_BUTTON_RIGHT,
    AVA_SA_BUTTON_A,
    AVA_SA_BUTTON_B,
    AVA_SA_BUTTON_X,
    AVA_SA_BUTTON_Y,
    AVA_SA_BUTTON_FN,
} ava_sa_button_t;

typedef struct {
    int gpio_up;
    int gpio_down;
    int gpio_left;
    int gpio_right;
    int gpio_a;
    int gpio_b;
    int gpio_x;
    int gpio_y;
    int gpio_fn;
    const char *ota_url;
    const char *websocket_url;
} ava_scratch_arcade_config_t;

typedef struct {
    ava_dk_runtime_t runtime;
    ava_scratch_arcade_config_t config;
} ava_scratch_arcade_port_t;

void ava_scratch_arcade_init(ava_scratch_arcade_port_t *port, const ava_scratch_arcade_config_t *config);
const char *ava_scratch_arcade_action_for_button(ava_sa_button_t button, const char *current_screen);
int ava_scratch_arcade_handle_button(ava_scratch_arcade_port_t *port, ava_sa_button_t button, const char *selection_context_json);
const char *ava_scratch_arcade_default_ota_path(void);
const char *ava_scratch_arcade_default_ws_path(void);

#ifdef __cplusplus
}
#endif

#endif /* AVA_SCRATCH_ARCADE_PORT_H */
