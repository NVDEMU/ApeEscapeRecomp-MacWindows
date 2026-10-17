# Built-in mods for Ape Escape Recompiled

Maintained as part of the nvd123 project, these packages appear on the launcher's Mods page. Native callbacks are compiled into the runtime; package manifests describe the available features and their options.

**Every feature is disabled by default.** Select a feature explicitly before launching the game. Options inside an enabled feature choose how that feature behaves; they do not silently turn on unrelated features.

Packages target the North American SCUS-94423 release. Where a target hash is specified, it identifies the MODE2/2352 data-track BIN used by the mod loader. No disc image or retail BIOS is shipped in the catalog.

The Gameplay Assist Pack contains separate toggles for Infinite Lives, Infinite Health, Infinite Air and Unlock All Gadgets. Each is gated to active gameplay.

The Quality-of-Life Tools package adds experimental Quick Retry (fast respawn, not a full stage reload), D-pad camera sensitivity, collectible statistics, a caught-monkey progress tracker and an in-game level timer. See the package README for shortcuts and limitations.

The optional **Sky Flyer Triple Jump** package maps a third quick R1/R2 press to an automatic right-stick rotation burst while the Sky Flyer is equipped. Holding Jump keeps rotation going; manual right-stick input takes priority. It is disabled by default and needs in-game validation.

The **Challenge Pack** adds timed monkey hunts, no-damage runs, limited starting lives and random rule selection. Each feature is independently opt-in and uses its own native plugin.

The separate **Hardcore Challenges** package adds default-off **Monkey Mayhem** and **Nightmare Mode**. Monkey Mayhem experimentally zeroes a community-reported monkey-action cooldown during active play; that RAM mapping requires in-game validation. Nightmare Mode automatically includes Monkey Mayhem with one-hit health, a three-life maximum that blocks extra-life increases, and a three-minute per-stage time limit. Its HUD displays the stage countdown.

