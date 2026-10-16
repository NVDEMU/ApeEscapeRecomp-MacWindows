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

# Expected North-American first-game roster counts by stage. On the two
# expanded stages below, compare names, levels, and profile summaries row by row.
expected = {
    0: 4, 1: 6, 2: 7, 10: 14, 11: 13, 12: 8, 20: 8, 21: 8, 22: 11,
    30: 6, 31: 9, 32: 9, 40: 12, 41: 10, 42: 20, 50: 13, 51: 10,
    52: 12, 60: 24,
}
counts = Counter(r[0] for r in rows)
if dict(counts) != expected:
    raise SystemExit(f"Verified source-profile totals mismatch: {dict(counts)!r}")
if len(rows) != 204:
    raise SystemExit(f"Expected 204 source-confirmed profiles, found {len(rows)}")

verified_rosters = {
    40: [
        ("Taku", 2, "Gangsta rapper."),
        ("Rocka", 2, "Slick DJ."),
        ("Mara-Iea", 1, "Rocking VJ."),
        ("Wog", 3, "Hurt playing Super Hero."),
        ("Mayi", 4, "Paints surreal landscapes."),
        ("Owyang", 1, "Quietly daydreaming."),
        ("Long", 4, "Unlucky with the ladies."),
        ("Elly", 4, "Wets the bed at night."),
        ("Chunky", 1, "Can't stand all the noise."),
        ("Voti", 2, "Always getting in trouble."),
        ("Quel", 2, "Can't wait to go home."),
        ("Phaldo", 2, "Likes strawberry shakes."),
    ],
    60: [
        ("Goopo", 3, "Control freak."),
        ("Porto", 4, "Talks to himself."),
        ("Slam", 5, "Terrified of ghosts."),
        ("Junk", 5, "Excited by monsters."),
        ("Crib", 5, "Wants out immediately."),
        ("Nak", 6, "Cool coolio."),
        ("Cloy", 6, "Can't stand the suspense."),
        ("Shaw", 6, "Feeling a little edgy."),
        ("Flea", 6, "Has a pet boa back home."),
        ("Schafette", 6, "Tired soldier."),
        ("Donovan", 6, "Never flown a UFO before."),
        ("Laura", 6, "Was expecting a vacation."),
        ("Uribe", 4, "Math wizard."),
        ("Gordo", 4, "A real pool shark."),
        ("Raeski", 4, "Mix master RAY."),
        ("Poo-pie", 3, "Too young for this."),
        ("Teacup", 4, "Very tidy and retentive."),
        ("Shine", 4, "Can't hit a moving target."),
        ("Wrench", 4, "Likes ketchup on eggs."),
        ("Bronson", 4, "Sees the end of the world."),
        ("Bungee", 5, "Can flip like a gymnast."),
        ("Carro", 4, "Total pyromaniac."),
        ("Carlito", 4, "Don't mess with him."),
        ("BG Whopper", 4, "Senses danger."),
    ],
}
source_urls = {
    40: "https://apeescape.fandom.com/wiki/Sushi_Temple",
    60: "https://apeescape.fandom.com/wiki/Monkey_Madness",
}
for stage_id, expected_profiles in verified_rosters.items():
    actual_profiles = [
        (r[3], r[4], r[5]) for r in rows if r[0] == stage_id
    ]
    if actual_profiles != expected_profiles:
        raise SystemExit(
            f"Source-verified roster mismatch for stage {stage_id}: {actual_profiles!r}"
        )
    for row in (r for r in rows if r[0] == stage_id):
        if row[6] != source_urls[stage_id]:
            raise SystemExit(f"Wrong source URL for {row[1]} #{row[2]}")
seen = set()
for stage, stage_name, index, name, _level, _description, _source in rows:
    key = (stage, index)
    if key in seen:
        raise SystemExit(f"Duplicate Monkepedia slot: {stage_name} #{index}")
    seen.add(key)
if "Unverified entry" in catalogue.read_text(encoding="utf-8"):
    raise SystemExit("Unverified placeholder entries must not be shipped.")

patcher = (ROOT / "tools/apply_recomp_ui_update_patch.py").read_text(encoding="utf-8")
for marker in (
    "ape_escape_caught_checklist.tsv",
    "ImGui::Checkbox(\"##caught\", &caught)",
    "Caught checkboxes are manual",
    "s_ape_caught_checklist",
):
    if marker not in patcher:
        raise SystemExit(f"Monkepedia manual checklist implementation missing {marker!r}.")
for obsolete in (
    "ape_escape_load_run_history",
    "ape_escape_journal.tsv",
    "PLAY HISTORY & PROGRESS",
    "TIME TRIALS",
    "s_ape_ever_caught",
    "append_snapshot",
):
    if obsolete in patcher:
        raise SystemExit(f"Removed play-history feature is still present in launcher patch: {obsolete!r}")
print(f"Monkepedia source validation passed: {len(rows)} profiles across {len(expected)} stages; all profiles have source links; caught status is user-controlled only.")
