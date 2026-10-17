#include "mod_plugins.h"
#include <stdint.h>

/*
 * Minimal read-only observer for Ape Escape Recompiled.
 *
 * Replace the sample plugin ID before distributing a mod. This deliberately
 * does not write guest RAM or alter gameplay; verify any address mapping
 * independently before building a feature around it.
 */
static void example_vblank(void) {
    if (!psx_mod_game_started())
        return;

    /* Example telemetry only: the meaning/lifecycle of this address still
     * needs to be verified for the exact game build before relying on it. */
    const uint16_t observed_word = psx_mod_read_half(0x800F4490u);
    (void)observed_word;
}

PSX_MOD_CONSTRUCTOR(register_example_plugin) {
    (void)psx_mod_register_vblank_plugin(
        "example.timer-observer",
        example_vblank);
}
