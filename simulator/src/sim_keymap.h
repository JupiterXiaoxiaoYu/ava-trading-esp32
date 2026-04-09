#ifndef AVE_SIM_KEYMAP_H
#define AVE_SIM_KEYMAP_H

#include <SDL2/SDL.h>

#define AVE_SIM_FN_PTT_NOOP  0
#define AVE_SIM_FN_PTT_START 1
#define AVE_SIM_FN_PTT_STOP  (-1)

int ave_sim_map_scancode_to_ave_key(SDL_Scancode scancode);
int ave_sim_is_mock_scene_scancode(SDL_Scancode scancode);
int ave_sim_is_fn_ptt_scancode(SDL_Scancode scancode);
int ave_sim_fn_ptt_apply(int *is_listening, int is_pressed);
const char *ave_sim_fn_ptt_transition_json(int transition);

#endif
