#!/usr/bin/env python3
"""Guard Extended Draw Distance's default-off catalog entry and EXE sites."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SITES = (
    "0x800591DC", "0x80069A24", "0x8006ADE0", "0x8006D2B8",
    "0x8006D868", "0x8006DE28", "0x8006E488", "0x8006E7AC",
    "0x8006F134", "0x8007074C",
)

def main() -> int:
    game = (ROOT / "game.toml").read_text(encoding="utf-8")
    manifest = (ROOT / "mods/preloaded/packages/ape.enhancement.extended-draw-distance/1.0.0/manifest.toml").read_text(encoding="utf-8")
    plugin = (ROOT / "src/mods/ape_extended_draw_distance_plugin.c").read_text(encoding="utf-8")

    blocks = re.findall(r"(?ms)^\[\[draw_distance\.clamp\]\]\s*\n(.*?)(?=^\[\[|\Z)", game)
    found = []
    for block in blocks:
        address = re.search(r'^address\s*=\s*"(0x[0-9A-Fa-f]+)"\s*$', block, re.M)
        expected = re.search(r'^expected\s*=\s*"(0x[0-9A-Fa-f]+)', block, re.M)
        reg = re.search(r'^reg\s*=\s*(\d+)\s*$', block, re.M)
        maximum = re.search(r'^max\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*$', block, re.M)
        if not all((address, expected, reg, maximum)):
            raise SystemExit("Malformed [[draw_distance.clamp]] block")
        if expected.group(1).lower() != "0x000c6083" or reg.group(1) != "12" or int(maximum.group(1), 0) != 0x3FFC:
            raise SystemExit(f"Unexpected clamp parameters at {address.group(1)}")
        found.append(address.group(1).upper())

    expected = [s.upper() for s in EXPECTED_SITES]
    if found != expected:
        raise SystemExit(f"Draw-distance sites drifted: found={found}, expected={expected}")
    feature_block = re.search(
        r'(?ms)^\[\[feature\]\]\s*\n(.*?)(?=^\[\[|\Z)', manifest
    )
    if not feature_block or not re.search(r'^id\s*=\s*"extended-draw-distance"\s*$', feature_block.group(1), re.M):
        raise SystemExit("Extended Draw Distance feature missing from manifest")
    if not re.search(r'^default_enabled\s*=\s*false\s*$', feature_block.group(1), re.M):
        raise SystemExit("Extended Draw Distance must remain disabled by default")
    if 'id = "ape.draw-distance.extended"' not in manifest:
        raise SystemExit("Extended Draw Distance activation plugin missing from manifest")
    if "psx_mod_set_draw_distance_clamp(1)" not in plugin:
        raise SystemExit("Extended Draw Distance plugin does not enable the framework clamp")

    print(f"Extended Draw Distance: {len(found)} guarded sites; launcher default is off.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
