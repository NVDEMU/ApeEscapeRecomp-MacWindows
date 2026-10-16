#!/usr/bin/env python3
"""Validate the bundled Monkey Book catalogue and opt-in recording safety contract."""
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalogue = ROOT / "recomp" / "launcher" / "monkepedia.tsv"
rows = []
for raw in catalogue.read_text(encoding="utf-8").splitlines():
    if not raw or raw.startswith("#"):
        continue
    fields = raw.split("\t")
    if len(fields) < 5:
        raise SystemExit(f"Malformed Monkepedia row: {raw!r}")
    stage_id, stage_name, entry_index, name, alias = fields[:5]
    rows.append((int(stage_id), stage_name, int(entry_index), name, alias))

main_entries = [r for r in rows if r[2] > 0]
if len(main_entries) != 204:
    raise SystemExit(f"Expected 204 main-game entry slots, found {len(main_entries)}")
expected = {
    0: 4, 1: 6, 2: 7, 10: 14, 11: 13, 12: 8, 20: 8, 21: 8, 22: 11,
    30: 6, 31: 9, 32: 9, 40: 12, 41: 10, 42: 20, 50: 13, 51: 10,
    52: 12, 60: 24,
}
counts = Counter(r[0] for r in main_entries)
if dict(counts) != expected:
    raise SystemExit(f"Stage entry totals mismatch: {dict(counts)!r}")
seen = set()
for stage, stage_name, index, name, _alias in main_entries:
    key = (stage, index)
    if key in seen:
        raise SystemExit(f"Duplicate Monkepedia slot: {stage_name} #{index}")
    seen.add(key)
    if not name.strip():
        raise SystemExit(f"Empty Monkepedia display name: {stage_name} #{index}")

manifest = (ROOT / "mods/preloaded/packages/ape.enhancement.progress-journal/1.0.0/manifest.toml").read_text(encoding="utf-8")
if "default_enabled = false" not in manifest:
    raise SystemExit("Progress Journal must remain opt-in by default.")
plugin = (ROOT / "src/mods/ape_progress_journal_plugin.c").read_text(encoding="utf-8")
if "psx_mod_write" in plugin:
    raise SystemExit("Progress Journal must not write to game RAM.")
if "if(g_in_play) append_snapshot();" not in plugin:
    raise SystemExit("Progress Journal no longer defers file writes until active play has stopped.")
print(f"Monkepedia catalogue valid: {len(main_entries)} main-game slots across {len(expected)} stages; journal remains opt-in and read-only.")
