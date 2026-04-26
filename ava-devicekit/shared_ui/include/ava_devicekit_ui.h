#ifndef AVA_DEVICEKIT_UI_H
#define AVA_DEVICEKIT_UI_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    AVA_DK_KEY_LEFT = 0,
    AVA_DK_KEY_RIGHT = 1,
    AVA_DK_KEY_UP = 2,
    AVA_DK_KEY_DOWN = 3,
    AVA_DK_KEY_X = 4,
    AVA_DK_KEY_Y = 5,
    AVA_DK_KEY_A = 6,
    AVA_DK_KEY_B = 7,
    AVA_DK_KEY_FN = 8,
} ava_dk_key_t;

typedef enum {
    AVA_DK_SCREEN_FEED = 0,
    AVA_DK_SCREEN_BROWSE,
    AVA_DK_SCREEN_SPOTLIGHT,
    AVA_DK_SCREEN_PORTFOLIO,
    AVA_DK_SCREEN_CONFIRM,
    AVA_DK_SCREEN_LIMIT_CONFIRM,
    AVA_DK_SCREEN_RESULT,
    AVA_DK_SCREEN_NOTIFY,
    AVA_DK_SCREEN_DISAMBIGUATION,
    AVA_DK_SCREEN_UNKNOWN,
} ava_dk_screen_id_t;

typedef struct {
    void (*show)(const char *json_data, void *user);
    void (*key)(ava_dk_key_t key, void *user);
    int (*selection_context_json)(char *out, size_t out_n, void *user);
    void (*cancel_timers)(void *user);
    void *user;
} ava_dk_screen_vtable_t;

typedef void (*ava_dk_send_json_fn)(const char *json, void *user);

typedef struct {
    ava_dk_screen_vtable_t screens[AVA_DK_SCREEN_UNKNOWN];
    ava_dk_send_json_fn send_json;
    void *send_user;
    ava_dk_screen_id_t current;
    ava_dk_screen_id_t back_target;
} ava_dk_ui_runtime_t;

void ava_dk_ui_init(ava_dk_ui_runtime_t *rt);
void ava_dk_ui_set_transport(ava_dk_ui_runtime_t *rt, ava_dk_send_json_fn send_json, void *user);
void ava_dk_ui_register_screen(ava_dk_ui_runtime_t *rt, ava_dk_screen_id_t id, ava_dk_screen_vtable_t screen);
ava_dk_screen_id_t ava_dk_ui_screen_from_name(const char *name);
const char *ava_dk_ui_screen_name(ava_dk_screen_id_t id);
ava_dk_screen_id_t ava_dk_ui_current_screen(const ava_dk_ui_runtime_t *rt);
int ava_dk_ui_handle_display_json(ava_dk_ui_runtime_t *rt, const char *json);
int ava_dk_ui_key_press(ava_dk_ui_runtime_t *rt, ava_dk_key_t key);
int ava_dk_ui_build_key_action_json(const char *action, const char *extra_fields_json, char *out, size_t out_n);
int ava_dk_ui_build_listen_detect_json(const char *text, const char *selection_context_json, char *out, size_t out_n);
int ava_dk_ui_json_escape(const char *src, char *out, size_t out_n);

#ifdef __cplusplus
}
#endif

#endif /* AVA_DEVICEKIT_UI_H */
