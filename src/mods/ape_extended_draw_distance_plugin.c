#include "mod_plugins.h"

/*
 * Extended Draw Distance is a default-off, trusted catalog feature. The
 * framework's main-EXE clamps cap traced SZ3 depth buckets before they are
 * stored; never widen the guest's ordering-table bounds themselves.
 */
static void ape_extended_draw_distance_activate(void) {
    (void)psx_mod_set_draw_distance_clamp(1);
}

PSX_MOD_CONSTRUCTOR(ape_register_extended_draw_distance_plugin) {
    (void)psx_mod_register_activation_plugin(
        "ape.draw-distance.extended",
        ape_extended_draw_distance_activate);
}
