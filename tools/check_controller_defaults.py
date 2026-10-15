#!/usr/bin/env python3
"""Prevent drift between bundled input defaults and Ape Escape's tested stick curve."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def table(text: str, name: str, source: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*\n(.*?)(?=^\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"{source}: missing [{name}] section")
    return match.group(1)


def integer_value(text: str, key: str, source: str) -> int:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*(\d+)\b", text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"{source}: missing integer setting {key}")
    return int(match.group(1))


def enum_value(text: str, key: str, source: str) -> int:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*(\d+)\b", text)
    if not match:
        raise ValueError(f"{source}: missing tested constant {key}")
    return int(match.group(1))


def main() -> int:
    input_text = (ROOT / "packaging/release/input.ini").read_text(encoding="utf-8")
    game_text = (ROOT / "game.toml").read_text(encoding="utf-8")
    test_text = (ROOT / "tests/test_stick_response.c").read_text(encoding="utf-8")

    input_controller = table(input_text, "controller", "input.ini")
    game_controller = table(game_text, "controller", "game.toml")
    input_deadzone = integer_value(input_controller, "deadzone", "input.ini")
    game_deadzone = integer_value(game_controller, "deadzone", "game.toml")
    anti_deadzone = integer_value(game_controller, "anti_deadzone", "game.toml")
    tested_deadzone = enum_value(test_text, "APE_HOST_DEADZONE", "test_stick_response.c")
    tested_anti_deadzone = enum_value(test_text, "APE_ANTI_DEADZONE", "test_stick_response.c")

    if len({input_deadzone, game_deadzone, tested_deadzone}) != 1:
        print(
            "Controller deadzone mismatch: "
            f"input.ini={input_deadzone}, game.toml={game_deadzone}, "
            f"stick-response test={tested_deadzone}.",
            file=sys.stderr,
        )
        return 1
    if anti_deadzone != tested_anti_deadzone:
        print(
            "Controller anti-deadzone mismatch: "
            f"game.toml={anti_deadzone}, stick-response test={tested_anti_deadzone}.",
            file=sys.stderr,
        )
        return 1

    print(
        "Controller defaults are aligned: "
        f"deadzone={input_deadzone}, anti_deadzone={anti_deadzone}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
