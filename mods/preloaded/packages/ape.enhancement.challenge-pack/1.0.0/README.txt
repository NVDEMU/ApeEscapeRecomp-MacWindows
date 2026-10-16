# Ape Escape Challenge Pack

Four independent, default-off challenge rules are available in the launcher's Mods page. Enable one rule at a time, or deliberately combine modes for a harder run.

- **Timed Monkey Hunt** — race the game's own stage timer against a 3-, 5- or 10-minute limit. Expiration sets health to zero so the normal death path handles failure. The stage timer's own reset/restart behavior stays authoritative.
- **No-Damage Run** — any observed decrease in health fails the attempt and triggers normal death handling. Healing is allowed; damage is not. Tracking resets when gameplay leaves the active-play state.
- **Limited Starting Lives** — set the life allowance to 1, 3 or 5 when active gameplay first begins in the app session. It does not refill lives on every stage or after each death. Start a fresh run for the intended rules.
- **Random Challenge Rules** — choose one of those rules when gameplay begins and keep it fixed for the session. Set the time-limit and starting-lives options to configure the corresponding random variants.

A compact in-game challenge HUD appears in the upper-left corner. All features are disabled by default. Native callbacks are compiled into the runtime; no downloaded code or extra game files are needed.

These are initial implementations and need in-game validation. They rely on the project's current mapping for gameplay state, health, lives and stage-timer fields. The stage timer, save-state loads, restarts and other active mods can affect a challenge run; this is not a certified speedrun timer.


- **Nightmare Mode** — a combined full-game hardcore ruleset. You get at most three lives for the entire run (extra-life pickups are capped), health is capped to a single hit (healing cannot raise it above one), and each stage has a three-minute limit using the game's own timer. The in-game HUD shows NIGHTMARE and the remaining time. This is deliberately brutal and remains off unless selected.

Nightmare Mode is a first implementation: timer/death interactions, life-counter semantics and healing behavior must still be verified during a real gameplay run. Its life allowance is set once when the feature first reaches active gameplay in an application session; it is not refreshed every stage.
