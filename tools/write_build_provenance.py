#!/usr/bin/env python3
"""Write machine-readable build/channel metadata for the in-app updater."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "BUILD_PROVENANCE.json"
version = (ROOT / "packaging/release/VERSION").read_text(encoding="utf-8").strip()
ref = os.environ.get("GITHUB_REF", "")
channel = "nightly" if ref == "refs/heads/master" else (
    "stable" if ref.startswith("refs/tags/") else "branch"
)
commit = os.environ.get("GITHUB_SHA", "")
if not commit:
    try:
        commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
payload = {
    "schema_version": 1,
    "repository": "NVDEMU/ApeEscapeRecomp-MacWindows",
    "channel": channel,
    "version": version,
    "commit": commit,
    "ref": ref or "local",
    "run_id": os.environ.get("GITHUB_RUN_ID", ""),
    "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
    "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {OUT}: channel={channel}, version={version}, commit={commit[:12]}")
