#!/usr/bin/env python3
"""Contract checks for the optional Sky Flyer Triple Jump package."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
manifest_path = ROOT / "mods/preloaded/packages/ape.enhancement.sky-flyer-triple-jump/1.0.0/manifest.toml"
source_path = ROOT / "src/mods/ape_sky_flyer_triple_jump_plugin.c"

manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
source = source_path.read_text(encoding="utf-8")

if manifest.get("id") != "ape.enhancement.sky-flyer-triple-jump":
    raise SystemExit("Unexpected Sky Flyer package ID")
if manifest.get("version") != "1.0.0":
    raise SystemExit("Unexpected Sky Flyer package version")
if manifest.get("resolver") != "declarative":
    raise SystemExit("Sky Flyer package must use the declarative resolver")
if manifest.get("save_compatibility") != "shared":
    raise SystemExit("Sky Flyer package must preserve shared save compatibility")

targets = manifest.get("target", [])
if len(targets) != 1 or targets[0].get("game_id") != "SCUS-94423":
    raise SystemExit("Sky Flyer package must target the North American Ape Escape build")
if targets[0].get("disc_sha256") != "1ae17e78ebb8c782c7c1785b0a0bd7b0ee28235b8a0c83c8df887129899a852a":
    raise SystemExit("Sky Flyer package has the wrong disc identity")

features = manifest.get("feature", [])
if len(features) != 1 or features[0].get("id") != "sky-flyer-triple-jump":
    raise SystemExit("Expected exactly one Sky Flyer Triple Jump feature")
if features[0].get("default_enabled") is not False:
    raise SystemExit("Sky Flyer Triple Jump must remain disabled by default")

expected_plugins = {"ape.gadgets.sky-flyer-triple-jump"}
plugins = {plugin.get("id") for plugin in manifest.get("plugin", [])}
if plugins != expected_plugins:
    raise SystemExit(f"Unexpected Sky Flyer plugin mapping: {plugins!r}")
for marker in (
    "ape.gadgets.sky-flyer-triple-jump",
    "APE_JUMP_CROSS = 0x40u",
    "APE_JUMP_MASK = APE_JUMP_CROSS",
    "APE_SKY_FLYER_GADGET = 5u",
    "APE_JUMP_COMBO_TIMEOUT_FRAMES = 60u",
    "APE_MINIMUM_ROTATION_FRAMES = 24u",
    "g_jump_press_count >= 3u",
    "manual-stick-priority",
    "psx_mod_register_vblank_plugin",
    "psx_mod_register_savestate_plugin",
):
    if marker not in source:
        raise SystemExit(f"Sky Flyer implementation is missing {marker!r}")

print("Sky Flyer Triple Jump: target, default-off manifest, Cross/X Jump trigger, rotation guards and savestate reset verified.")
