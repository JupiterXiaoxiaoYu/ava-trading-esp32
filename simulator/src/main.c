/**
 * @file main.c
 * Ava Box PC simulator entry point.
 *
 * Mirrors the ESP32 firmware:
 *  - Same LVGL screens via ava-devicekit/reference_apps/ava_box/ui
 *  - Same WebSocket protocol to the DeviceKit gateway
 *  - Same button key codes (arrow keys + literal A/B/X/Y map to hardware keys)
 *
 * Simulator extras (not in firmware):
 *  - Optional offline scene fixtures when AVA_SIM_ENABLE_FIXTURES=1
 *  - P key cycles fixture scenes only when fixtures are enabled
 *  - Type text commands in the terminal to bypass ASR and send directly to LLM
 */

#ifndef _DEFAULT_SOURCE
  #define _DEFAULT_SOURCE
#endif

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _MSC_VER
  #include <Windows.h>
#else
  #include <unistd.h>
  #include <pthread.h>
#endif

#include "lvgl/lvgl.h"
#include "lvgl/examples/lv_examples.h"
#include "lvgl/demos/lv_demos.h"
#include <SDL2/SDL.h>

#include "hal/hal.h"
#include "ave_screen_manager.h"
#include "sim_keymap.h"
#include "ws_client.h"

/* ── stdin thread ────────────────────────────────────────────────────────── */
/* Reads text from the terminal and forwards it to the server via WS.
 * This is the simulator substitute for the MEMS microphone + ASR. */
static void *_stdin_thread(void *arg)
{
    (void)arg;
    char buf[256];
    printf("[AVE sim] Ready. Type a command and press Enter "
           "(e.g. 帮我看热门代币 / 看我的持仓 / 买这个)\n");
    while (fgets(buf, sizeof(buf), stdin)) {
        buf[strcspn(buf, "\n")] = '\0';
        if (buf[0]) ws_client_send_text(buf);
    }
    return NULL;
}

/* ── Main ────────────────────────────────────────────────────────────────── */
#if LV_USE_OS != LV_OS_FREERTOS

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;

    lv_init();

    /* Scratch Arcade 创客版 ESP32-S3: 320×240 landscape */
    sdl_hal_init(320, 240);

    /* Initialize LVGL screen manager (same code as firmware) */
    ave_sm_init(lv_display_get_default());

    int fixtures_enabled = 0;
    const char *fixtures_env = getenv("AVA_SIM_ENABLE_FIXTURES");
    if (fixtures_env && strcmp(fixtures_env, "1") == 0) {
        fixtures_enabled = 1;
        ave_sm_mock_start();
    }

    /* Connect to DeviceKit gateway — identical flow to the ESP32 firmware.
     * Display messages are queued and applied in the main loop below. */
    ws_client_start();

    /* Start stdin reader for text-based command injection */
    pthread_t stdin_tid;
    pthread_create(&stdin_tid, NULL, _stdin_thread, NULL);

    /* Scratch Arcade button mapping (edge-detect):
     *   Left  arrow → AVE_KEY_LEFT   (D-pad Left)
     *   Right arrow → AVE_KEY_RIGHT  (D-pad Right)
     *   Up    arrow → AVE_KEY_UP     (D-pad Up)
     *   Down  arrow → AVE_KEY_DOWN   (D-pad Down)
     *   X          → AVE_KEY_X       (X button)
     *   Y          → AVE_KEY_Y       (Y button)
     *   A          → AVE_KEY_A       (A button)
     *   B          → AVE_KEY_B       (B button)
     *   F1         → FN/PTT          (voice listen / AI entry)
     *   P          → next fixture scene when AVA_SIM_ENABLE_FIXTURES=1
     */
    int prev_left = 0, prev_right = 0, prev_up = 0, prev_down = 0;
    int prev_x = 0, prev_y = 0, prev_a = 0, prev_b = 0, prev_p = 0;
    int fn_listening = 0;

    while (1) {
        /* Drain any display messages received from the server */
        while (ws_client_poll()) {}

        /* Edge-detect hardware button presses */
        const Uint8 *ks = SDL_GetKeyboardState(NULL);
        int cur_left  = ks[SDL_SCANCODE_LEFT];
        int cur_right = ks[SDL_SCANCODE_RIGHT];
        int cur_up    = ks[SDL_SCANCODE_UP];
        int cur_down  = ks[SDL_SCANCODE_DOWN];
        int cur_x     = ks[SDL_SCANCODE_X];
        int cur_y     = ks[SDL_SCANCODE_Y];
        int cur_a     = ks[SDL_SCANCODE_A];
        int cur_b     = ks[SDL_SCANCODE_B];
        int cur_p     = ks[SDL_SCANCODE_P];
        int cur_fn    = ks[SDL_SCANCODE_F1];

        if (cur_left  && !prev_left)  ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_LEFT));
        if (cur_right && !prev_right) ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_RIGHT));
        if (cur_up    && !prev_up)    ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_UP));
        if (cur_down  && !prev_down)  ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_DOWN));
        if (cur_x     && !prev_x)     ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_X));
        if (cur_y     && !prev_y)     ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_Y));
        if (cur_a     && !prev_a)     ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_A));
        if (cur_b     && !prev_b)     ave_sm_key_press(ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_B));
        if (fixtures_enabled && cur_p && !prev_p && ave_sim_is_mock_scene_scancode(SDL_SCANCODE_P)) {
            ave_sm_mock_next_scene();
        }
        if (ave_sim_is_fn_ptt_scancode(SDL_SCANCODE_F1)) {
            int fn_transition = ave_sim_fn_ptt_apply(&fn_listening, cur_fn != 0);
            const char *fn_json = ave_sim_fn_ptt_transition_json(fn_transition);
            if (fn_json != NULL) {
                ws_client_send_json(fn_json);
                printf("[AVE sim] FN/PTT -> %s\n",
                    fn_transition == AVE_SIM_FN_PTT_START ? "listen start (manual)"
                                                          : "listen stop (manual)");
            }
        }

        prev_left  = cur_left;  prev_right = cur_right;
        prev_up    = cur_up;    prev_down  = cur_down;
        prev_x     = cur_x;     prev_y     = cur_y;
        prev_a     = cur_a;     prev_b     = cur_b;   prev_p = cur_p;

        uint32_t sleep_ms = lv_timer_handler();
        if (sleep_ms == LV_NO_TIMER_READY) sleep_ms = LV_DEF_REFR_PERIOD;
#ifdef _MSC_VER
        Sleep(sleep_ms);
#else
        usleep(sleep_ms * 1000);
#endif
    }

    ws_client_stop();
    return 0;
}

#endif
