# Quality-of-Life Tools

This package adds five independent, default-off options to the launcher's Mods page. Enabling one feature does not turn on the others.

- **Quick Retry** — press Select + L3 + R3 during active gameplay to trigger the game's normal death/respawn path and reset its displayed stage timer. It consumes a life, requires at least two remaining lives, and does not reset enemy or collectible state. This is an experimental fast respawn, not a full stage reload.
- **Camera Sensitivity** — rate-limits D-pad camera input to 25%, 50%, 75%, or 100%. Only active gameplay is filtered; menus and analog-stick axes are left alone.
- **Collectible Stats Overlay** — shows the game's monkey, triangle, and Specter-coin counters.
- **Enhanced Radar** — shows caught/uncaught pips from the game's 20-entry monkey record table. This is progress tracking, not a map of live monkey locations.
- **Speedrun Timer** — displays the game's own level timer as MM:SS.t; it follows the game timer rather than a host wall-clock stopwatch.

These are initial implementations. The build and catalog checks verify compilation and opt-in wiring, but actual in-game behavior and the memory-table assumptions still need play-testing on Windows and both macOS architectures. Every feature is disabled by default.
