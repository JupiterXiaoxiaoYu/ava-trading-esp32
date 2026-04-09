#include <stdio.h>
#include <string.h>
#include <SDL2/SDL.h>

#include "ave_screen_manager.h"
#include "sim_keymap.h"

static int expect_equal(int actual, int expected, const char *msg)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s (expected=%d got=%d)\n", msg, expected, actual);
        return 0;
    }
    return 1;
}

static int expect_string_equal(const char *actual, const char *expected, const char *msg)
{
    if (actual == NULL || expected == NULL || strcmp(actual, expected) != 0) {
        fprintf(stderr, "FAIL: %s (expected=\"%s\" got=\"%s\")\n",
            msg,
            expected ? expected : "(null)",
            actual ? actual : "(null)");
        return 0;
    }
    return 1;
}

static int expect_ptr_equal(const void *actual, const void *expected, const char *msg)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s\n", msg);
        return 0;
    }
    return 1;
}

static int run_keymap_expectations(void)
{
    int ok = 1;

    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_LEFT),
        AVE_KEY_LEFT,
        "LEFT arrow should map to AVE_KEY_LEFT");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_RIGHT),
        AVE_KEY_RIGHT,
        "RIGHT arrow should map to AVE_KEY_RIGHT");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_UP),
        AVE_KEY_UP,
        "UP arrow should map to AVE_KEY_UP");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_DOWN),
        AVE_KEY_DOWN,
        "DOWN arrow should map to AVE_KEY_DOWN");

    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_X),
        AVE_KEY_X,
        "keyboard X should map to AVE_KEY_X");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_Y),
        AVE_KEY_Y,
        "keyboard Y should map to AVE_KEY_Y");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_A),
        AVE_KEY_A,
        "keyboard A should map to AVE_KEY_A");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_B),
        AVE_KEY_B,
        "keyboard B should map to AVE_KEY_B");

    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_Z),
        -1,
        "legacy keyboard Z should no longer map to AVE keys");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_W),
        -1,
        "legacy keyboard W should no longer map to AVE keys");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_S),
        -1,
        "legacy keyboard S should no longer map to AVE keys");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_Q),
        -1,
        "legacy keyboard Q should no longer map to AVE keys");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_E),
        -1,
        "legacy keyboard E should no longer map to AVE keys");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_P),
        -1,
        "mock-scene P should not map to an AVE key");

    ok &= expect_equal(
        ave_sim_is_fn_ptt_scancode(SDL_SCANCODE_F1),
        1,
        "keyboard F1 should be reserved as FN/PTT");
    ok &= expect_equal(
        ave_sim_is_fn_ptt_scancode(SDL_SCANCODE_A),
        0,
        "keyboard A must not be treated as FN/PTT");
    ok &= expect_equal(
        ave_sim_map_scancode_to_ave_key(SDL_SCANCODE_F1),
        -1,
        "FN/PTT key must not collide with AVE A/B/X/Y/D-pad mapping");

    return ok;
}

static int run_fn_ptt_state_machine_expectations(void)
{
    int ok = 1;
    int is_listening = 0;

    ok &= expect_equal(
        ave_sim_fn_ptt_apply(&is_listening, 0),
        AVE_SIM_FN_PTT_NOOP,
        "FN/PTT idle should ignore repeated key-up");
    ok &= expect_equal(is_listening, 0, "FN/PTT idle should stay idle");

    ok &= expect_equal(
        ave_sim_fn_ptt_apply(&is_listening, 1),
        AVE_SIM_FN_PTT_START,
        "FN/PTT key-down should emit manual listen start");
    ok &= expect_equal(is_listening, 1, "FN/PTT key-down should enter listening state");

    ok &= expect_equal(
        ave_sim_fn_ptt_apply(&is_listening, 1),
        AVE_SIM_FN_PTT_NOOP,
        "FN/PTT hold should not repeat start messages");
    ok &= expect_equal(is_listening, 1, "FN/PTT hold should remain listening");

    ok &= expect_equal(
        ave_sim_fn_ptt_apply(&is_listening, 0),
        AVE_SIM_FN_PTT_STOP,
        "FN/PTT key-up should emit manual listen stop");
    ok &= expect_equal(is_listening, 0, "FN/PTT key-up should return to idle");

    ok &= expect_equal(
        ave_sim_fn_ptt_apply(&is_listening, 0),
        AVE_SIM_FN_PTT_NOOP,
        "FN/PTT repeated key-up should not repeat stop messages");

    ok &= expect_string_equal(
        ave_sim_fn_ptt_transition_json(AVE_SIM_FN_PTT_START),
        "{\"type\":\"listen\",\"state\":\"start\",\"mode\":\"manual\"}",
        "FN/PTT start transition should map to manual listen-start JSON");
    ok &= expect_string_equal(
        ave_sim_fn_ptt_transition_json(AVE_SIM_FN_PTT_STOP),
        "{\"type\":\"listen\",\"state\":\"stop\",\"mode\":\"manual\"}",
        "FN/PTT stop transition should map to manual listen-stop JSON");
    ok &= expect_ptr_equal(
        ave_sim_fn_ptt_transition_json(AVE_SIM_FN_PTT_NOOP),
        NULL,
        "FN/PTT noop transition should not produce JSON");

    return ok;
}

int main(void)
{
    int ok = 1;

    ok &= run_keymap_expectations();
    ok &= run_fn_ptt_state_machine_expectations();
    if (ok) {
        printf("PASS: simulator keymap + FN/PTT checks passed.\n");
        return 0;
    }
    return 1;
}
