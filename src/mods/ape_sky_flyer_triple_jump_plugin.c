#include "mod_plugins.h"

#include <stdint.h>

/*
 * Sky Flyer Triple Jump
 *
 * With Sky Flyer equipped, the third quick Cross/X press in a jump sequence
 * synthesizes a right-stick rotation burst. This deliberately delegates takeoff,
 * lift, steering and landing to the game's existing Sky Flyer logic instead of
 * writing player physics values directly.
 *
 * The game-side controller shadow is active-low. Axes are only available in a
 * DualShock report (0x73); the title's shipped controller profile is analog-only.
 * If the right stick is already moving, manual input wins and this plugin does
 * not take it over. All state changes are guarded to active gameplay.
 */
static const uint32_t APE_TRANSITION_PHASE_ADDRESS = 0x800F447Cu;
static const uint32_t APE_PAD_ID_ADDRESS = 0x800B87A0u;
static const uint32_t APE_JUMP_BUTTONS_ADDRESS = 0x800B87A3u;
static const uint32_t APE_RIGHT_STICK_X_ADDRESS = 0x800B87A4u;
static const uint32_t APE_RIGHT_STICK_Y_ADDRESS = 0x800B87A5u;
static const uint32_t APE_HELD_GADGET_ADDRESS = 0x800EC2D2u;
static const uint32_t APE_UNLOCKED_GADGETS_ADDRESS = 0x800F51C4u;

enum {
    APE_TRANSITION_PLAYING = 0x03u,
    APE_PAD_ID_ANALOG = 0x73u,

    /* PS1 face-button byte is active-low; Cross/X is the Jump button. */
    APE_JUMP_CROSS = 0x40u,
    APE_JUMP_MASK = APE_JUMP_CROSS,

    /* Gadget indices are the game's 0..7 inventory slots. */
    APE_SKY_FLYER_GADGET = 5u,
    APE_RIGHT_STICK_DEADZONE = 28,
    APE_AXIS_CENTER = 0x80,

    /* Three presses must arrive within roughly one second of each other. */
    APE_JUMP_COMBO_TIMEOUT_FRAMES = 60u,

    /* Ensure a tap still produces a short takeoff burst; holding Jump keeps it spinning. */
    APE_MINIMUM_ROTATION_FRAMES = 24u,
    APE_FRAMES_PER_ROTATION_STEP = 2u,
    APE_ROTATION_STEP_COUNT = 8u
};

/* One clockwise circle. Values deliberately stay inside the axis range. */
static const uint8_t APE_ROTATION_X[APE_ROTATION_STEP_COUNT] = {
    228u, 198u, 128u, 58u, 28u, 58u, 128u, 198u
};
static const uint8_t APE_ROTATION_Y[APE_ROTATION_STEP_COUNT] = {
    128u, 58u, 28u, 58u, 128u, 198u, 228u, 198u
};

static uint8_t g_previous_jump_down;
static uint8_t g_jump_press_count;
static uint16_t g_frames_since_jump_press;

static uint8_t g_rotation_active;
static uint8_t g_rotation_step;
static uint8_t g_frames_in_rotation_step;
static uint16_t g_minimum_rotation_frames;
static uint8_t g_saved_axis_x = APE_AXIS_CENTER;
static uint8_t g_saved_axis_y = APE_AXIS_CENTER;
static uint8_t g_last_written_axis_x = APE_AXIS_CENTER;
static uint8_t g_last_written_axis_y = APE_AXIS_CENTER;
static uint8_t g_last_written_valid;

static int ape_sky_flyer_gameplay_active(void) {
    return psx_mod_game_started() &&
           psx_mod_read_byte(APE_TRANSITION_PHASE_ADDRESS) ==
               APE_TRANSITION_PLAYING;
}

static int ape_sky_flyer_is_equipped_and_unlocked(void) {
    const uint8_t unlocked =
        psx_mod_read_byte(APE_UNLOCKED_GADGETS_ADDRESS);
    return psx_mod_read_byte(APE_HELD_GADGET_ADDRESS) ==
               APE_SKY_FLYER_GADGET &&
           (unlocked & (uint8_t)(1u << APE_SKY_FLYER_GADGET)) != 0u;
}

static int ape_axis_delta(uint8_t value) {
    const int delta = (int)value - APE_AXIS_CENTER;
    return delta < 0 ? -delta : delta;
}

static int ape_right_stick_is_centered(uint8_t x, uint8_t y) {
    return ape_axis_delta(x) <= APE_RIGHT_STICK_DEADZONE &&
           ape_axis_delta(y) <= APE_RIGHT_STICK_DEADZONE;
}

static int ape_right_stick_matches_last_write(uint8_t x, uint8_t y) {
    const int dx = (int)x - (int)g_last_written_axis_x;
    const int dy = (int)y - (int)g_last_written_axis_y;
    return g_last_written_valid && dx >= -6 && dx <= 6 &&
           dy >= -6 && dy <= 6;
}

static int ape_jump_button_is_down(void) {
    const uint8_t pressed =
        (uint8_t)~psx_mod_read_byte(APE_JUMP_BUTTONS_ADDRESS);
    return (pressed & APE_JUMP_MASK) != 0u;
}

static void ape_sky_flyer_clear_combo(void) {
    g_jump_press_count = 0u;
    g_frames_since_jump_press = 0u;
}

/*
 * If controller polling has replaced our synthetic sample with centered axes,
 * returning to the original centered values is harmless. If it contains a
 * different non-centered value, leave it alone so a player's manual stick
 * movement is never overwritten during cleanup.
 */
static void ape_sky_flyer_stop_rotation(int restore_if_safe) {
    if (g_rotation_active && restore_if_safe) {
        const uint8_t x = psx_mod_read_byte(APE_RIGHT_STICK_X_ADDRESS);
        const uint8_t y = psx_mod_read_byte(APE_RIGHT_STICK_Y_ADDRESS);
        if (ape_right_stick_is_centered(x, y) ||
            ape_right_stick_matches_last_write(x, y)) {
            psx_mod_write_byte(APE_RIGHT_STICK_X_ADDRESS, g_saved_axis_x);
            psx_mod_write_byte(APE_RIGHT_STICK_Y_ADDRESS, g_saved_axis_y);
        }
    }

    g_rotation_active = 0u;
    g_rotation_step = 0u;
    g_frames_in_rotation_step = 0u;
    g_minimum_rotation_frames = 0u;
    g_last_written_valid = 0u;
}

static void ape_sky_flyer_start_rotation(void) {
    const uint8_t x = psx_mod_read_byte(APE_RIGHT_STICK_X_ADDRESS);
    const uint8_t y = psx_mod_read_byte(APE_RIGHT_STICK_Y_ADDRESS);

    if (psx_mod_read_byte(APE_PAD_ID_ADDRESS) != APE_PAD_ID_ANALOG) {
        psx_mod_counter_add("ape.gadgets.sky-flyer-triple-jump.no-analog-pad", 1u);
        return;
    }

    /* Don't steal a stick already being used to control a gadget. */
    if (!ape_right_stick_is_centered(x, y)) {
        psx_mod_counter_add("ape.gadgets.sky-flyer-triple-jump.manual-stick-priority", 1u);
        return;
    }

    g_saved_axis_x = x;
    g_saved_axis_y = y;
    g_rotation_active = 1u;
    g_rotation_step = 0u;
    g_frames_in_rotation_step = 0u;
    g_minimum_rotation_frames = APE_MINIMUM_ROTATION_FRAMES;
    g_last_written_valid = 0u;
    psx_mod_counter_add("ape.gadgets.sky-flyer-triple-jump.activated", 1u);
}

static void ape_sky_flyer_rotation_vblank(int jump_down) {
    uint8_t x;
    uint8_t y;

    if (!g_rotation_active)
        return;

    x = psx_mod_read_byte(APE_RIGHT_STICK_X_ADDRESS);
    y = psx_mod_read_byte(APE_RIGHT_STICK_Y_ADDRESS);

    /*
     * Polling may restore the physical stick's centered value before every
     * callback. Accept centered values or the previous synthetic sample.
     * A different active value means the player has taken manual control.
     */
    if (!ape_right_stick_is_centered(x, y) &&
        !ape_right_stick_matches_last_write(x, y)) {
        ape_sky_flyer_stop_rotation(0);
        psx_mod_counter_add("ape.gadgets.sky-flyer-triple-jump.manual-override", 1u);
        return;
    }

    if (g_minimum_rotation_frames == 0u && !jump_down) {
        ape_sky_flyer_stop_rotation(1);
        return;
    }

    x = APE_ROTATION_X[g_rotation_step];
    y = APE_ROTATION_Y[g_rotation_step];
    psx_mod_write_byte(APE_RIGHT_STICK_X_ADDRESS, x);
    psx_mod_write_byte(APE_RIGHT_STICK_Y_ADDRESS, y);
    g_last_written_axis_x = x;
    g_last_written_axis_y = y;
    g_last_written_valid = 1u;

    if (++g_frames_in_rotation_step >= APE_FRAMES_PER_ROTATION_STEP) {
        g_frames_in_rotation_step = 0u;
        g_rotation_step =
            (uint8_t)((g_rotation_step + 1u) % APE_ROTATION_STEP_COUNT);
    }
    if (g_minimum_rotation_frames > 0u)
        --g_minimum_rotation_frames;
}

static void ape_sky_flyer_triple_jump_vblank(void) {
    const int playing = ape_sky_flyer_gameplay_active();
    const int equipped = playing && ape_sky_flyer_is_equipped_and_unlocked();
    const int jump_down = ape_jump_button_is_down();
    const int jump_edge = jump_down && !g_previous_jump_down;

    if (!playing || !equipped) {
        ape_sky_flyer_stop_rotation(1);
        ape_sky_flyer_clear_combo();
        g_previous_jump_down = (uint8_t)jump_down;
        return;
    }

    if (g_jump_press_count != 0u) {
        if (g_frames_since_jump_press >= APE_JUMP_COMBO_TIMEOUT_FRAMES) {
            ape_sky_flyer_clear_combo();
        } else {
            ++g_frames_since_jump_press;
        }
    }

    if (jump_edge) {
        if (g_jump_press_count < 3u)
            ++g_jump_press_count;
        g_frames_since_jump_press = 0u;

        if (g_jump_press_count >= 3u) {
            ape_sky_flyer_clear_combo();
            ape_sky_flyer_start_rotation();
        }
    }

    g_previous_jump_down = (uint8_t)jump_down;
    ape_sky_flyer_rotation_vblank(jump_down);
}

static void ape_sky_flyer_after_savestate_restore(void) {
    /* Plugin statics aren't savestate data; never carry a stale press sequence across a restore. */
    ape_sky_flyer_stop_rotation(1);
    ape_sky_flyer_clear_combo();
    g_previous_jump_down = (uint8_t)ape_jump_button_is_down();
}

PSX_MOD_CONSTRUCTOR(ape_register_sky_flyer_triple_jump_plugin) {
    (void)psx_mod_register_vblank_plugin(
        "ape.gadgets.sky-flyer-triple-jump",
        ape_sky_flyer_triple_jump_vblank);
    (void)psx_mod_register_savestate_plugin(
        "ape.gadgets.sky-flyer-triple-jump",
        ape_sky_flyer_after_savestate_restore);
}
