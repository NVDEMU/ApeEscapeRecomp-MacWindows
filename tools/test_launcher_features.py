#!/usr/bin/env python3
"""Static integration checks for project-owned launcher features."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
patch = (ROOT / "tools/apply_recomp_ui_update_patch.py").read_text(encoding="utf-8")
helper = (ROOT / "tools/launcher_extra_views.inc").read_text(encoding="utf-8")
guide = (ROOT / "docs/MOD_DEVELOPER_TOOLKIT.md").read_text(encoding="utf-8")
template = (ROOT / "templates/mod-plugin/example_plugin.c").read_text(encoding="utf-8")

required_views = (
    "LNG_VIEW_DAILY_CHALLENGE",
    "LNG_VIEW_STAGE_GUIDE",
    "LNG_VIEW_MOD_TOOLKIT",
    "ape_escape_draw_daily_challenge",
    "ape_escape_draw_stage_guide",
    "ape_escape_draw_mod_toolkit",
    "ape_escape_draw_save_protection_center",
    "APE_ESCAPE_EXTRA_LAUNCHER_BODY",
)
for token in required_views:
    if token not in patch:
        raise SystemExit(f"launcher patch is missing integration marker: {token}")
if "EXTRA_HELPERS_PATH = Path(\"tools/launcher_extra_views.inc\")" not in patch:
    raise SystemExit("launcher patch does not load the project-owned feature source")
if "ape_escape_draw_save_protection_center(th, quick_button_w, quick_gap);" not in patch:
    raise SystemExit("Save Protection Center is not connected to Quick Tools")
if patch.count("const auto safety_snapshot = ape_escape_create_save_backup();") != 2:
    raise SystemExit("updater and rollback must each create a safety snapshot before launch")

for token in (
    "ape_escape_create_save_backup",
    "ape_escape_restore_save_backup",
    "BACKUP_INFO.txt",
    "ape_escape_latest_save_backup",
    "ape_escape_prune_save_backups",
    "Create Safety Backup and Restore",
    "APE_ESCAPE_NEW_FEATURES_HELPER",
):
    if token not in helper:
        raise SystemExit(f"launcher helper is missing: {token}")
restore = helper[helper.index("static bool ape_escape_restore_save_backup"):helper.index("/* SAVE PROTECTION CENTER")]
if restore.index("ape_escape_create_save_backup()") > restore.index("ape_escape_copy_regular_tree("):
    raise SystemExit("restore must create a pre-restore safety backup before copying snapshot files")
if "skip_save_protection" not in helper:
    raise SystemExit("backup creation does not exclude its own backup directory")
if "backups.size() <= 20u" not in helper:
    raise SystemExit("backup history has no retention limit")
if "does not delete files" not in helper:
    raise SystemExit("save restore safety behavior is not described")

for token in (
    "ape_escape_today_challenge",
    "ape_escape_daily_next",
    "ape_escape_save_daily_history",
    "ape_escape_daily_challenges.tsv",
    "Enable matching Challenge Pack features",
    "no scores are uploaded",
):
    # The stored history helper is intentionally local-only and uses a date-derived seed.
    if token not in helper:
        raise SystemExit(f"Daily Challenge implementation is missing: {token}")
if "*state ^= *state << 13u" not in helper or "*state ^= *state >> 17u" not in helper or "*state ^= *state << 5u" not in helper:
    raise SystemExit("daily challenge generator is missing its deterministic xorshift steps")

stage_ids = {int(value) for value in re.findall(r"case (\d+): return \"", helper)}
expected_stage_ids = {0, 1, 2, 10, 11, 12, 20, 21, 22, 30, 31, 32, 40, 41, 42, 50, 51, 52, 60}
if stage_ids != expected_stage_ids:
    raise SystemExit(f"Stage Guide tips do not cover the expected roster IDs: {stage_ids!r}")
if "source_url" not in patch or "f[6]" not in patch:
    raise SystemExit("Stage Guide cannot access the catalogue's source-page URLs")

for token in ("PSX_MOD_CONSTRUCTOR", "psx_mod_game_started", "psx_mod_read_half", "psx_mod_register_vblank_plugin"):
    if token not in template:
        raise SystemExit(f"read-only plugin template is missing API usage: {token}")
if "psx_mod_write" in template:
    raise SystemExit("minimal plugin example must remain read-only")
for token in ("Save Protection Center", "Daily Challenge", "Stage Guide", "Mod Developer Toolkit"):
    if token not in guide:
        raise SystemExit(f"developer guide missing integration context: {token}")

for filename in ("tools/package_macos.sh", "tools/package_release.ps1", "tools/package_appimage.sh"):
    package = (ROOT / filename).read_text(encoding="utf-8")
    if "MOD_DEVELOPER_TOOLKIT.md" not in package or "example_plugin.c" not in package:
        raise SystemExit(f"{filename} does not ship the mod developer guide and template")

print("Launcher feature integration, save-restore guardrails, daily challenge seed, stage guide data, and mod template checks passed.")
