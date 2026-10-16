# Ape Escape Challenge Pack

Five standalone challenge rules plus the combined Nightmare Mode are available on the launcher's Mods page. Every feature is off by default; select the exact rules you want, or enable Nightmare Mode for the complete hardcore set.

- **Timed Monkey Hunt** — race the game's own stage timer against a 3-, 5- or 10-minute limit. Expiration sets health to zero so the normal death path handles failure. The stage timer's own reset/restart behavior stays authoritative.
- **No-Damage Run** — any observed decrease in health fails the attempt and triggers normal death handling. Healing is allowed; damage is not. Tracking resets when gameplay leaves the active-play state.
- **Limited Starting Lives** — set the life allowance to 1, 3 or 5 when active gameplay first begins in the app session. It does not refill lives on every stage or after each death. Start a fresh run for the intended rules.
- **Random Challenge Rules** — choose one of those rules when gameplay begins and keep it fixed for the session. Set the time-limit and starting-lives options to configure the corresponding random variants.

- **Monkey Mayhem** — on every active-play frame, the feature forces a community-reported monkey-action cooldown at RAM address `0x800B4980` to zero, intended to make monkeys' actions/alert behavior recur far more often. The address and effect are not verified in this build, so expect possible unusual behavior until tested. Background: [Ape Escape speedrunning community notes](https://apewiki.siontea.com/AE1/RNG).

A compact in-game challenge HUD appears in the upper-left corner for timed, no-damage, limited-lives, random and Nightmare challenges. Monkey Mayhem itself does not add a second HUD panel. All features are disabled by default. Native callbacks are compiled into the runtime; no downloaded code or extra game files are needed.

These are initial implementations and need in-game validation. They rely on the project's current mapping for gameplay state, health, lives and stage-timer fields. The stage timer, save-state loads, restarts and other active mods can affect a challenge run; this is not a certified speedrun timer.


- **Nightmare Mode** — the combined full-game hardcore ruleset automatically includes Monkey Mayhem. You get at most three lives for the entire run (extra-life pickups are capped), health is capped to a single hit (healing cannot raise it above one), each stage has a three-minute limit using the game's own timer, and monkeys use the experimental zero-cooldown behavior rule. The in-game HUD shows NIGHTMARE and the remaining time. This remains off unless selected.

Nightmare Mode is a first implementation: timer/death interactions, life-counter semantics and healing behavior must still be verified during a real gameplay run. Its life allowance is set once when the feature first reaches active gameplay in an application session; it is not refreshed every stage.
