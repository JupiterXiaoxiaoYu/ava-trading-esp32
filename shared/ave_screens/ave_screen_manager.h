/**
 * @file ave_screen_manager.h
 * @brief AVE Xiaozhi screen dispatcher.
 *
 * Parses {"type":"display","screen":"<id>","data":{...}} JSON from server
 * and routes to the correct LVGL screen.
 *
 * Screen IDs: feed | spotlight | confirm | limit_confirm | result | portfolio | notify | disambiguation
 *
 * Scratch Arcade 创客版 button mapping:
 *   GPIO6/8 analog joystick = AVE_KEY_LEFT/RIGHT/UP/DOWN
 *     - GPIO6 high -> LEFT,  GPIO6 low -> RIGHT
 *     - GPIO8 high -> UP,    GPIO8 low -> DOWN
 *   GPIO9  X button         = AVE_KEY_X (quick sell)
 *   GPIO4  Y button         = AVE_KEY_Y (portfolio shortcut)
 *   GPIO39 A button         = AVE_KEY_A (detail / confirm / buy)
 *   GPIO5  B button         = AVE_KEY_B (back / cancel)
 *   GPIO0  FN               = system / voice wake / PTT
 */

#ifndef AVE_SCREEN_MANAGER_H
#define AVE_SCREEN_MANAGER_H

#ifdef __cplusplus
extern "C" {
#endif

#if __has_include("lvgl.h")
#include "lvgl.h"
#else
#include "lvgl/lvgl.h"
#endif

#include <stdbool.h>
#include <stddef.h>

/* ─── Key codes ─────────────────────────────────────────────────────────── */
#define AVE_KEY_LEFT   0   /* D-pad Left: list navigation / refresh */
#define AVE_KEY_RIGHT  1   /* D-pad Right: enter detail / confirm */
#define AVE_KEY_UP     2   /* D-pad Up: scroll up */
#define AVE_KEY_DOWN   3   /* D-pad Down: scroll down */
#define AVE_KEY_X      4   /* X button: quick sell (reserved) */
#define AVE_KEY_Y      5   /* Y button: portfolio shortcut */
#define AVE_KEY_A      6   /* A button: detail / confirm / buy */
#define AVE_KEY_B      7   /* B button: back / cancel */

/* ─── Screen IDs ─────────────────────────────────────────────────────────── */
typedef enum {
    AVE_SCREEN_FEED = 0,
    AVE_SCREEN_SPOTLIGHT,
    AVE_SCREEN_CONFIRM,
    AVE_SCREEN_LIMIT_CONFIRM,
    AVE_SCREEN_RESULT,
    AVE_SCREEN_PORTFOLIO,
    AVE_SCREEN_NOTIFY,   /* overlay — does not change current_screen */
    AVE_SCREEN_DISAMBIGUATION,
    AVE_SCREEN_COUNT,
} ave_screen_id_t;

typedef struct {
    const char *key;
    const char *value;
} ave_sm_json_field_t;

/* ─── Public API ──────────────────────────────────────────────────────────── */

/**
 * Initialize the screen manager.
 * Must be called once after lv_init() and display creation.
 */
void ave_sm_init(lv_display_t *disp);

/**
 * Handle a raw JSON string received from the server.
 * Parses {"type":"display","screen":"...","data":{...}} and routes.
 */
void ave_sm_handle_json(const char *json_str);

/**
 * Notify the screen manager of a physical key press.
 * key: any AVE_KEY_* constant (0-7)
 */
void ave_sm_key_press(int key);

/**
 * Go back to FEED screen (used on timeout / cancel).
 */
void ave_sm_go_to_feed(void);

/**
 * Back-timeout fallback used by screens that first ask server-side navigation.
 * Prefers restoring portfolio context when possible, otherwise falls back to FEED.
 */
void ave_sm_go_back_fallback(void);

/* ─── NOTIFY overlay helpers ─────────────────────────────────────────────── */

/**
 * Show the NOTIFY overlay from a notify JSON payload.
 */
void screen_notify_show(const char *json_data);

/**
 * Returns true while the NOTIFY overlay is on screen.
 */
bool screen_notify_is_visible(void);

/**
 * Dismiss the NOTIFY overlay immediately (any key).
 */
void screen_notify_key(int key);

/* ─── Simulator mock (PC only) ───────────────────────────────────────────── */

/**
 * Load mock scenes from mock/mock_scenes/NN_name.json files.
 * Displays the first scene immediately (offline fallback while server is down).
 * Call once at startup.
 */
void ave_sm_mock_start(void);

/**
 * Advance to the next mock scene ('P' key).
 */
void ave_sm_mock_next_scene(void);

/**
 * Build explicit current-selection context JSON for outgoing listen commands.
 * Returns 1 when context is available and written to `out`, otherwise 0.
 */
int ave_sm_get_selection_context_json(char *out, size_t out_n);

/**
 * Escape text for safe embedding inside a JSON string literal.
 * Returns 1 on success, otherwise 0.
 */
int ave_sm_json_escape_string(const char *src, char *out, size_t out_n);

/**
 * Build a key_action payload, escaping every dynamic string field.
 * Returns 1 on success, otherwise 0.
 */
int ave_sm_build_key_action_json(
    const char *action,
    const ave_sm_json_field_t *fields,
    size_t field_count,
    char *out,
    size_t out_n
);

/**
 * Build a listen.detect payload with current explicit selection when available.
 * Returns 1 on success, otherwise 0.
 */
int ave_sm_build_listen_detect_json(const char *text, char *out, size_t out_n);

#ifdef __cplusplus
}
#endif

#endif /* AVE_SCREEN_MANAGER_H */
