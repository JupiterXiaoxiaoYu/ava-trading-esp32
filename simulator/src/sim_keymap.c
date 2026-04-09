#include "sim_keymap.h"

#include "ave_screen_manager.h"

#define AVE_SIM_FN_PTT_SCANCODE SDL_SCANCODE_F1
#define AVE_SIM_FN_PTT_LISTEN_START_JSON \
    "{\"type\":\"listen\",\"state\":\"start\",\"mode\":\"manual\"}"
#define AVE_SIM_FN_PTT_LISTEN_STOP_JSON \
    "{\"type\":\"listen\",\"state\":\"stop\",\"mode\":\"manual\"}"

int ave_sim_map_scancode_to_ave_key(SDL_Scancode scancode)
{
    switch (scancode) {
        case SDL_SCANCODE_LEFT:
            return AVE_KEY_LEFT;
        case SDL_SCANCODE_RIGHT:
            return AVE_KEY_RIGHT;
        case SDL_SCANCODE_UP:
            return AVE_KEY_UP;
        case SDL_SCANCODE_DOWN:
            return AVE_KEY_DOWN;
        case SDL_SCANCODE_X:
            return AVE_KEY_X;
        case SDL_SCANCODE_Y:
            return AVE_KEY_Y;
        case SDL_SCANCODE_A:
            return AVE_KEY_A;
        case SDL_SCANCODE_B:
            return AVE_KEY_B;
        default:
            return -1;
    }
}

int ave_sim_is_mock_scene_scancode(SDL_Scancode scancode)
{
    return scancode == SDL_SCANCODE_P;
}

int ave_sim_is_fn_ptt_scancode(SDL_Scancode scancode)
{
    return scancode == AVE_SIM_FN_PTT_SCANCODE;
}

int ave_sim_fn_ptt_apply(int *is_listening, int is_pressed)
{
    if (is_listening == NULL) return AVE_SIM_FN_PTT_NOOP;

    if (is_pressed) {
        if (*is_listening) return AVE_SIM_FN_PTT_NOOP;
        *is_listening = 1;
        return AVE_SIM_FN_PTT_START;
    }

    if (!*is_listening) return AVE_SIM_FN_PTT_NOOP;
    *is_listening = 0;
    return AVE_SIM_FN_PTT_STOP;
}

const char *ave_sim_fn_ptt_transition_json(int transition)
{
    switch (transition) {
        case AVE_SIM_FN_PTT_START:
            return AVE_SIM_FN_PTT_LISTEN_START_JSON;
        case AVE_SIM_FN_PTT_STOP:
            return AVE_SIM_FN_PTT_LISTEN_STOP_JSON;
        default:
            return NULL;
    }
}
