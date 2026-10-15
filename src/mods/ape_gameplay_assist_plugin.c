#include "mod_plugins.h"

#include <stdint.h>

/*
 * Optional North American Ape Escape gameplay assists.
 *
 * The writable RAM locations below match documented SCUS-94423 cheat-code
 * values. Keep the writes in active gameplay only: menu, title, save/load and
 * attract/demo states should retain their stock behavior. The catalog keeps
 * each assist as a separate default-off feature.
 */
static const uint32_t APE_TRANSITION_PHASE_ADDRESS = 0x800F447Cu;
static const uint8_t APE_TRANSITION_PLAYING = 0x03u;

static const uint32_t APE_LIVES_ADDRESS = 0x800F448Cu;
static const uint32_t APE_HEALTH_ADDRESS = 0x800EC2C8u;
static const uint32_t APE_AIR_ADDRESS = 0x800F4DC8u;
static const uint32_t APE_UNLOCKED_GADGETS_ADDRESS = 0x800F51C4u;

static int ape_assist_is_active(void) {
    return psx_mod_game_started() &&
           psx_mod_read_byte(APE_TRANSITION_PHASE_ADDRESS) ==
               APE_TRANSITION_PLAYING;
}

static void ape_assist_infinite_lives(void) {
    if (!ape_assist_is_active())
        return;
    psx_mod_write_half(APE_LIVES_ADDRESS, 100u);
}

static void ape_assist_infinite_health(void) {
    if (!ape_assist_is_active())
        return;
    psx_mod_write_half(APE_HEALTH_ADDRESS, 5u);
}

static void ape_assist_infinite_air(void) {
    if (!ape_assist_is_active())
        return;
    psx_mod_write_half(APE_AIR_ADDRESS, 0x0258u);
}

static void ape_assist_all_gadgets(void) {
    if (!ape_assist_is_active())
        return;

    /* A bit per gadget. Write only if needed to avoid unnecessary RAM writes. */
    if (psx_mod_read_byte(APE_UNLOCKED_GADGETS_ADDRESS) != 0xFFu)
        psx_mod_write_byte(APE_UNLOCKED_GADGETS_ADDRESS, 0xFFu);
}

PSX_MOD_CONSTRUCTOR(ape_register_gameplay_assist_plugins) {
    (void)psx_mod_register_vblank_plugin(
        "ape.assist.infinite-lives", ape_assist_infinite_lives);
    (void)psx_mod_register_vblank_plugin(
        "ape.assist.infinite-health", ape_assist_infinite_health);
    (void)psx_mod_register_vblank_plugin(
        "ape.assist.infinite-air", ape_assist_infinite_air);
    (void)psx_mod_register_vblank_plugin(
        "ape.assist.all-gadgets", ape_assist_all_gadgets);
}
