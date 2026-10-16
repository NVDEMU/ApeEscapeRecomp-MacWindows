#!/usr/bin/env python3
"""Fetch and validate the private Ape Escape CHD for CI release builds.

Authenticated Dropbox API download is preferred because shared-link pages can
return a small HTML response with HTTP 200. The shared URL is a fallback only;
every candidate must have the CHD magic and a plausible disc-image size.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DROPBOX_API_PATH = "/ApeEscapeWii-private-assets/Ape Escape (USA).chd"
MIN_CHD_BYTES = 10 * 1024 * 1024
CHD_MAGIC = b"MComprHD"


def validate_chd(path: Path) -> int:
    size = path.stat().st_size
    with path.open("rb") as stream:
        magic = stream.read(len(CHD_MAGIC))
    if magic != CHD_MAGIC or size < MIN_CHD_BYTES:
        raise ValueError(
            f"not a valid Ape Escape CHD (size={size:,} bytes, "
            f"header={magic!r}; expected MComprHD and at least "
            f"{MIN_CHD_BYTES:,} bytes)"
        )
    return size


def stream_response(request: Request, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=90) as response, destination.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def exchange_dropbox_token(app_key: str, app_secret: str, refresh_token: str) -> str:
    body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")
    basic = base64.b64encode(f"{app_key}:{app_secret}".encode("utf-8")).decode("ascii")
    request = Request(
        "https://api.dropbox.com/oauth2/token",
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ApeEscapeRecomp-CI/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("Dropbox token response did not contain an access token")
    return token


def download_dropbox_api(candidate: Path) -> None:
    key = os.environ["DROPBOX_APP_KEY"]
    secret = os.environ["DROPBOX_APP_SECRET"]
    refresh = os.environ["DROPBOX_REFRESH_TOKEN"]
    token = exchange_dropbox_token(key, secret, refresh)
    request = Request(
        "https://content.dropboxapi.com/2/files/download",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": DROPBOX_API_PATH}, separators=(",", ":")),
            "User-Agent": "ApeEscapeRecomp-CI/1.0",
        },
        method="POST",
    )
    stream_response(request, candidate)

def exchange_dropbox_app_token(app_key: str, app_secret: str) -> str:
    """Get an app-level OAuth token; this does not require a user refresh token."""
    body = urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    basic = base64.b64encode(f"{app_key}:{app_secret}".encode("utf-8")).decode("ascii")
    request = Request(
        "https://api.dropbox.com/oauth2/token",
        data=body,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ApeEscapeRecomp-CI/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("Dropbox app-token response did not contain an access token")
    return token


def download_shared_link_api(candidate: Path, shared_url: str) -> None:
    """Download through Dropbox's shared-link content API, not its HTML viewer."""
    key = os.environ["DROPBOX_APP_KEY"].strip()
    secret = os.environ["DROPBOX_APP_SECRET"].strip()
    token = exchange_dropbox_app_token(key, secret)
    # Mask token in GitHub Actions logs before it can be used in later requests.
    print(f"::add-mask::{token}")
    request = Request(
        "https://content.dropboxapi.com/2/sharing/get_shared_link_file",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"url": shared_url}, separators=(",", ":")),
            "User-Agent": "ApeEscapeRecomp-CI/1.0",
        },
        method="POST",
    )
    stream_response(request, candidate)



def shared_url_variants(url: str) -> list[tuple[str, str]]:
    """Try Dropbox's direct-render and forced-download modes without printing the URL."""
    parts = urlsplit(url)
    if not (parts.hostname and parts.hostname.lower().endswith("dropbox.com")):
        return [("provided URL", url)]

    base_query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                  if key not in {"dl", "raw"}]
    raw_query = urlencode(base_query + [("raw", "1")])
    download_query = urlencode(base_query + [("dl", "1")])
    raw_url = urlunsplit((parts.scheme, parts.netloc, parts.path, raw_query, ""))
    download_url = urlunsplit((parts.scheme, parts.netloc, parts.path, download_query, ""))
    # The proven release workflow used curl with dl=1. Try that first, then raw=1.
    variants = [("Dropbox dl=1", download_url), ("Dropbox raw=1", raw_url)]

    # Legacy /s/<id>/<name> links can use Dropbox's content host directly.
    if parts.path.startswith("/s/") and parts.hostname.lower() in {"www.dropbox.com", "dropbox.com"}:
        content_url = urlunsplit(("https", "dl.dropboxusercontent.com", parts.path, urlencode(base_query), ""))
        variants.append(("Dropbox legacy content host", content_url))

    # Keep order while deduplicating links that were already in the desired mode.
    seen: set[str] = set()
    return [(label, candidate) for label, candidate in variants
            if not (candidate in seen or seen.add(candidate))]


def download_shared_url(url: str, candidate: Path) -> None:
    """Use curl's known-good redirect/TLS behavior for Dropbox shared downloads.

    Do not set a custom User-Agent: the original successful release workflow used
    curl's default headers. Capture stderr so a failed command cannot leak a
    shared-link URL into public Actions logs.
    """
    candidate.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--retry", "3",
            "--retry-delay", "2",
            "--silent",
            "--show-error",
            url,
            "--output", str(candidate),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl download failed with exit code {result.returncode}")


def concise_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"HTTP {error.code} ({error.reason})"
    if isinstance(error, URLError):
        return f"network error ({error.reason})"
    return str(error)


def try_source(label: str, download, candidate: Path, destination: Path) -> bool:
    candidate.unlink(missing_ok=True)
    try:
        download(candidate)
        size = validate_chd(candidate)
        os.replace(candidate, destination)
        print(f"Validated Ape Escape CHD using {label} ({size:,} bytes).")
        return True
    except Exception as exc:  # report the source safely, without printing secret URLs/tokens
        candidate.unlink(missing_ok=True)
        print(f"{label} did not provide a usable CHD: {concise_error(exc)}", file=sys.stderr)
        return False


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} OUTPUT.chd", file=sys.stderr)
        return 2

    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="ape-escape-disc-", suffix=".part", dir=destination.parent, delete=False
    ) as tmp:
        candidate = Path(tmp.name)
    candidate.unlink(missing_ok=True)

    key = os.environ.get("DROPBOX_APP_KEY", "").strip()
    secret = os.environ.get("DROPBOX_APP_SECRET", "").strip()
    refresh = os.environ.get("DROPBOX_REFRESH_TOKEN", "").strip()
    shared_url = os.environ.get("DISC_URL", "").strip()

    try:
        # Prefer Dropbox's content API for the configured shared link. This avoids
        # HTML preview pages and uses app-level OAuth, so no user refresh token is
        # required. The result is still checked for a real CHD before acceptance.
        if key and secret and shared_url:
            if try_source(
                "Dropbox shared-link content API",
                lambda path: download_shared_link_api(path, shared_url),
                candidate,
                destination,
            ):
                return 0

        # Retain path-based OAuth for installations that already have a refresh token.
        if key and secret and refresh:
            if try_source(
                "authenticated Dropbox API",
                lambda path: download_dropbox_api(path),
                candidate,
                destination,
            ):
                return 0

        if shared_url:
            for label, url in shared_url_variants(shared_url):
                if try_source(
                    label,
                    lambda path, candidate_url=url: download_shared_url(candidate_url, path),
                    candidate,
                    destination,
                ):
                    return 0

        print(
            "No source produced a valid CHD. Check that the Dropbox API path "
            f"{DROPBOX_API_PATH!r} exists, or update APE_ESCAPE_DISC_URL to a direct "
            "download link. A non-empty download is not sufficient.",
            file=sys.stderr,
        )
        return 1
    finally:
        candidate.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
