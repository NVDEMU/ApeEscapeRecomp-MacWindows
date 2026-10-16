#!/usr/bin/env python3
"""Validate source-linked US Monkepedia records and opt-in journal safety."""
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
catalogue = ROOT / "recomp" / "launcher" / "monkepedia.tsv"
rows = []
for raw in catalogue.read_text(encoding="utf-8").splitlines():
    if not raw or raw.startswith("#"):
        continue
    fields = raw.split("\t")
    if len(fields) != 7:
        raise SystemExit(f"Expected 7 fields in Monkepedia row, found {len(fields)}: {raw!r}")
    stage_id, stage_name, entry_index, name, level, description, source_url = fields
    try:
        parsed = urlparse(source_url)
        numeric_level = int(level)
        numeric_id, numeric_index = int(stage_id), int(entry_index)
    except ValueError as exc:
        raise SystemExit(f"Invalid numeric profile data: {raw!r}") from exc
    if not name.strip() or not description.strip():
        raise SystemExit(f"Profile name/description must not be empty: {stage_name} #{entry_index}")
    if "unverified" in name.casefold() or "placeholder" in name.casefold():
        raise SystemExit(f"Placeholder profile found: {stage_name} #{entry_index}")
    if not 1 <= numeric_level <= 7:
        raise SystemExit(f"Invalid Monkey Level: {stage_name} #{entry_index}")
    if parsed.scheme != "https" or parsed.netloc != "apeescape.fandom.com" or "/wiki/" not in parsed.path:
        raise SystemExit(f"Profile must link to its source page: {stage_name} #{entry_index}")
    rows.append((numeric_id, stage_name, numeric_index, name, numeric_level, description, source_url))

# These are source-confirmed rows, not a claim that the original game has fewer
# monkeys. Profiles absent from the retrieved source extracts are deliberately omitted.
expected = {
    0: 4, 1: 6, 2: 7, 10: 14, 11: 13, 12: 8, 20: 8, 21: 8, 22: 11,
    30: 6, 31: 9, 32: 9, 40: 9, 41: 10, 42: 20, 50: 13, 51: 10,
    52: 12, 60: 3,
}
counts = Counter(r[0] for r in rows)
if dict(counts) != expected:
    raise SystemExit(f"Verified source-profile totals mismatch: {dict(counts)!r}")
if len(rows) != 180:
    raise SystemExit(f"Expected 180 source-confirmed profiles, found {len(rows)}")
seen = set()
for stage, stage_name, index, name, _level, _description, _source in rows:
    key = (stage, index)
    if key in seen:
        raise SystemExit(f"Duplicate Monkepedia slot: {stage_name} #{index}")
    seen.add(key)
if "Unverified entry" in catalogue.read_text(encoding="utf-8"):
    raise SystemExit("Unverified placeholder entries must not be shipped.")

manifest = (ROOT / "mods/preloaded/packages/ape.enhancement.progress-journal/1.0.0/manifest.toml").read_text(encoding="utf-8")
if "default_enabled = false" not in manifest:
    raise SystemExit("Progress Journal must remain opt-in by default.")
plugin = (ROOT / "src/mods/ape_progress_journal_plugin.c").read_text(encoding="utf-8")
if "psx_mod_write" in plugin:
    raise SystemExit("Progress Journal must not write to game RAM.")
if "if(g_in_play) append_snapshot();" not in plugin:
    raise SystemExit("Progress Journal no longer defers file writes until active play has stopped.")

patcher = (ROOT / "tools/apply_recomp_ui_update_patch.py").read_text(encoding="utf-8")
for marker in ("int monkey_level", "f.size() < 7", "e->description.c_str()", "e->source_url"):
    if marker not in patcher:
        raise SystemExit(f"Monkepedia launcher implementation missing {marker!r}.")
print(f"Monkepedia source validation passed: {len(rows)} populated US profiles across {len(expected)} stages; no placeholders; journal remains opt-in/read-only.")
