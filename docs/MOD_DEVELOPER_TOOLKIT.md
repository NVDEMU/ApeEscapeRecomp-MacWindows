# Ape Escape Recompiled — Mod Developer Toolkit

This guide describes the project-owned native plugin interface and the launcher tools added for mod authors. The launcher includes a **Mod Toolkit** page with a copyable read-only plugin example. The matching source template is in `templates/mod-plugin/example_plugin.c`.

## Start with a read-only plugin

1. Copy the template and give the plugin a unique ID for this project.
2. Keep the corresponding feature disabled by default in its `manifest.toml`.
3. Build with the runtime's `runtime/include` headers. The release workflow syntax-checks the example plugin.
4. Add a small, specific regression check for the manifest, callback registration, and any constants used.
5. Test from a backed-up save and a clean test profile. Record the game version, stage, setup, and observed behavior.
6. Only enable the feature on a normal playthrough after in-game behavior has been checked.

## Callback and game-state rules

- Prefer observation and logging before writes. Read-only access is not automatically proof that an address means what its name suggests.
- Use the project's exported `psx_mod_*` functions and supported callbacks. Do not copy undocumented runtime internals into a plugin without pinning and verifying the dependency.
- Gate stage-specific behavior on an independently verified gameplay phase. Loading screens, transitions, pauses, and game-over phases can share memory with gameplay.
- Clear timers, edge-detection latches, counters, and transient state when a stage exits or the plugin is reactivated. Consider savestate loads as a discontinuity.
- Avoid writing control-flow values, object pointers, boss phase variables, or broad RAM ranges unless the address, width, valid range, and lifecycle are known.
- Never assume that forcing health to zero, changing a timer, or rewriting a few values constitutes a full stage reset.
- Every feature should be opt-in, independently disableable, and should not change the original game when disabled.
- Make save compatibility explicit in the manifest. Test enabling and disabling the feature against a backed-up test card.

## Manifest and test expectations

Every distributable package belongs under `mods/preloaded/packages/<package-id>/<version>/` or the separately documented external-mod flow. Keep the package ID, plugin ID, feature IDs, and option IDs consistent. For built-in mods:

- Default every feature to off.
- Add a check that reads the manifest through the runtime's package parser.
- Check the resolved plugin plan and any declarative guest writes, not just that the manifest parses.
- Add syntax checks to CI for native code.
- Keep experimental or unverified behavior labeled as such in the manifest and README.
- Do not embed retail game images, BIOS files, saves, or user-specific paths in a plugin.

## Save Protection Center

The launcher dashboard provides **Create Backup Now** and **Restore Latest Backup**. Backup snapshots contain user-writable application data and the install-local `saves/` directory when present. The restore confirmation first creates a safety snapshot, then merges files from the chosen backup. It does not delete files that were added after the backup, and matching files may be overwritten. Keep external copies of important memory-card files as well.

## Daily Challenge and Stage Guide

Daily challenges are generated deterministically from the local calendar date and offer combinations of the existing timed-hunt, no-damage, and limited-lives challenge rules. The launcher never silently enables mods; players must enable matching Challenge Pack features manually. Completion marks are self-reported and stored locally. There is no online leaderboard or automatic gameplay verification.

Stage Knowledge Cards read stage names, counts, and reference links from the project's existing North-American `monkepedia.tsv` catalogue. The briefings are general tactics, not route-verified walkthroughs or live tracking of monkeys.

## Reporting a bug

Include the installed build information from **Quick Tools**, the OS and controller, the selected challenge/mod settings, and whether the issue reproduces with all mods disabled. Do not attach disc images or retail BIOS files. If a bug involves saves, reproduce on a copy and retain the untouched original.
