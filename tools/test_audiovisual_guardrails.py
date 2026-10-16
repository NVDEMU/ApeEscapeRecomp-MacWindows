#!/usr/bin/env python3
"""Regression checks for stock AV defaults and the frame-smoothing gameplay guard."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
frame_source = (ROOT / "src/mods/ape_frame_rate_plugin.cpp").read_text(encoding="utf-8")
guard = re.search(r"if\\s*\\(\\s*index\\s*>\\s*1\\s*\\|\\|(?P<conditions>[^)]*)\\)\\s*\\{\\s*replay\\.invalidate\\(\\)", frame_source)
if not guard:
    raise SystemExit("Could not locate frame-smoothing invalidation guard.")
conditions = guard.group("conditions")
if re.search(r"\\bmode\\s*==\\s*3\\b", conditions):
    raise SystemExit("Frame smoothing still rejects phase 3 (active gameplay).")
for phase in (4, 5, 6):
    if not re.search(rf"\\bmode\\s*==\\s*{phase}\\b", conditions):
        raise SystemExit(f"Frame smoothing must reject transition/loading phase {phase}.")
config = (ROOT / "game.toml").read_text(encoding="utf-8")
if 'aspect_ratio = "4:3"' not in config:
    raise SystemExit("The stock 4:3 presentation default was lost.")
issues = (ROOT / "ISSUES.md").read_text(encoding="utf-8")
for title in ("Widescreen: distance (draw-distance) pop-in", "circus balls pop/cull"):
    if title not in issues:
        raise SystemExit(f"Known unverified audiovisual issue was removed: {title}")
print("AV guardrails passed: active-play interpolation is reachable, stock 4:3 remains available, and known widescreen defects remain documented.")
