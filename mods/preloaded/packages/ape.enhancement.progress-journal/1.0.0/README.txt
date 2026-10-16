# Ape Escape Progress Journal

The optional Progress Journal records one local row after active gameplay exits. It includes stage ID, in-game timer, captured count and flags, triangles, Specter coins, lives, and timestamp.

- It never writes guest RAM.
- Nothing is uploaded; data is stored in a local TSV file named ape_escape_journal.tsv.
- It does no file I/O while active gameplay is running.
- Era/level addresses and stage-exit behavior are not yet validated on the North American SCUS-94423 build.
- It does not distinguish successful clears from deaths, detect all assist mods, or enforce a speedrun category.
- The current probe exposes at most 20 captured-monkey flags, so later entries are catalogue-only.

Disabled by default. The static Monkepedia catalogue remains available while this feature is off.