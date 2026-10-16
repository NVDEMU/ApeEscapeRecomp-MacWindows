# Ape Escape Hardcore Challenges

This package adds two optional, default-off hardcore features to Ape Escape Recompiled – Enhanced Edition.

- **Monkey Mayhem** — during active gameplay, the native plugin forces a community-reported monkey-action cooldown at RAM address `0x800B4980` to zero every frame. This is intended to make some monkey actions and alert behavior recur more often, making encounters less predictable. The address and exact effect are experimental and must be verified in-game. Background: [Ape Escape speedrunning community notes](https://apewiki.siontea.com/AE1/RNG).
- **Nightmare Mode** — a full-game challenge with health capped to a single hit, a maximum of three lives for the run (extra-life pickups are capped), and a strict three-minute timer per stage. Nightmare automatically enforces the Monkey Mayhem behavior as part of its own callback, so users do not need to enable both features.

The Nightmare HUD displays the remaining time. Monkey Mayhem itself has no separate HUD panel. Both features are disabled by default and can be selected independently from the launcher's Mods page.

These are experimental reverse-engineered gameplay changes, not certified difficulty settings. Verify monkey AI, death/restart behavior, healing, life counting, timer resets and later-stage behavior during an actual game session before treating them as stable.
