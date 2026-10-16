#!/usr/bin/env python3
"""Check and install the latest nvd123 Ape Escape Recompiled Nightly.

The launcher starts this helper as a separate process. Downloads are verified
against the SHA256SUMS asset from the same GitHub release. Installation begins
only after the launcher process exits. macOS installs a whole .app bundle via
an atomic rename; Windows merges packaged files while preserving settings/saves.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

REPOSITORY = "NVDEMU/ApeEscapeRecomp-Mac"
RELEASE_TAG = "macos-nightly"
API_RELEASE = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{RELEASE_TAG}"
USER_AGENT = "nvd123-ApeEscapeRecomp-Updater/1.0"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
RUNTIME_TEMP_ENV = "NVD123_UPDATER_RUNTIME_TEMP"
BOOTSTRAPPED_ENV = "NVD123_UPDATER_BOOTSTRAPPED"


def _apple_script_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def notify(message: str, title: str = "Ape Escape Recompiled Updater",
           kind: str = "info") -> None:
    if os.name == "nt":
        icon = {"error": 0x10, "warning": 0x30}.get(kind, 0x40)
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000000 | icon)
        return
    if sys.platform == "darwin":
        script = (
            f'display alert "{_apple_script_string(title)}" '
            f'message "{_apple_script_string(message)}" '
            f'as {"critical" if kind == "error" else "warning" if kind == "warning" else "informational"}'
        )
        subprocess.run(["/usr/bin/osascript", "-e", script],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
        return
    print(f"{title}: {message}", file=sys.stderr if kind == "error" else sys.stdout)


def ask_yes_no(message: str, title: str = "Ape Escape Recompiled Updater") -> bool:
    if os.name == "nt":
        result = ctypes.windll.user32.MessageBoxW(
            None, message, title, 0x00000004 | 0x00000020 | 0x00010000
        )
        return result == 6  # IDYES
    if sys.platform == "darwin":
        script = (
            f'display dialog "{_apple_script_string(message)}" '
            f'with title "{_apple_script_string(title)}" '
            'buttons {"Cancel", "Continue"} default button "Continue" cancel button "Cancel"'
        )
        result = subprocess.run(["/usr/bin/osascript", "-e", script],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, check=False)
        return result.returncode == 0 and "button returned:Continue" in result.stdout
    return False


def http_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_json(url: str) -> dict[str, Any]:
    data = json.loads(http_bytes(url).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("GitHub returned an unexpected JSON response.")
    return data


def local_provenance(install_root: Path) -> dict[str, Any]:
    if os.name == "nt":
        provenance = install_root / "BUILD_PROVENANCE.json"
    else:
        provenance = install_root.parent / "Resources" / "BUILD_PROVENANCE.json"
    try:
        data = json.loads(provenance.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def platform_suffixes() -> tuple[str, str]:
    if os.name == "nt":
        return "-windows-x64.zip", "SHA256SUMS-windows-x64.txt"
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            arch = "arm64"
        elif machine in ("x86_64", "amd64"):
            arch = "x86_64"
        else:
            raise RuntimeError(f"Unsupported Mac architecture: {machine}")
        return f"-macos-{arch}.zip", f"SHA256SUMS-macos-{arch}.txt"
    raise RuntimeError("The Nightly updater currently supports macOS and Windows only.")


def download_to(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("GitHub returned an empty download.")


def checksum_for_asset(text: str, filename: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pieces = stripped.split(None, 1)
        if len(pieces) != 2:
            continue
        digest, listed_name = pieces
        listed_name = listed_name.strip().lstrip("*")
        if listed_name == filename and len(digest) == 64:
            try:
                int(digest, 16)
                return digest.lower()
            except ValueError:
                pass
    raise RuntimeError(f"The release checksum file does not contain {filename}.")


def verify_archive_paths(archive_path: Path, allow_symlinks: bool) -> None:
    seen: set[str] = set()
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            name = info.filename
            if not name or "\\" in name:
                raise RuntimeError("The update archive has an invalid path.")
            rel = PurePosixPath(name)
            if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
                raise RuntimeError("The update archive contains a path outside its install folder.")
            if rel.parts and ":" in rel.parts[0]:
                raise RuntimeError("The update archive contains a drive-qualified path.")
            normalized = str(rel)
            if normalized in seen:
                raise RuntimeError("The update archive contains duplicate paths.")
            seen.add(normalized)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                if not allow_symlinks:
                    raise RuntimeError("Windows updates must not contain symbolic links.")
                try:
                    target = archive.read(info).decode("utf-8")
                except (UnicodeDecodeError, OSError) as exc:
                    raise RuntimeError("The update archive contains an invalid symbolic link.") from exc
                if not target or PurePosixPath(target).is_absolute() or "\\" in target:
                    raise RuntimeError("The update archive contains an unsafe symbolic link.")
                # Resolve the relative symlink target lexically within the package root.
                stack = list(rel.parent.parts)
                for part in PurePosixPath(target).parts:
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if not stack:
                            raise RuntimeError("The update archive contains an escaping symbolic link.")
                        stack.pop()
                    else:
                        stack.append(part)


def windows_wait_for_parent(pid: int) -> None:
    if pid <= 0:
        return
    process = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not process:
        return
    try:
        ctypes.windll.kernel32.WaitForSingleObject(process, 0xFFFFFFFF)
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not process:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(process, 0) == 0x102
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_parent_exit(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        windows_wait_for_parent(pid)
        return
    while parent_alive(pid):
        time.sleep(1.0)


def app_bundle_from_root(install_root: Path) -> Path:
    candidates = [install_root, *install_root.parents]
    for candidate in candidates:
        if candidate.name.endswith(".app") and candidate.is_dir():
            return candidate
    raise RuntimeError("Could not locate the installed .app bundle above Contents/MacOS.")


def validate_single_app_bundle(staging: Path) -> Path:
    apps = list(staging.glob("*.app"))
    if len(apps) != 1 or not apps[0].is_dir():
        raise RuntimeError("The Mac update ZIP did not contain exactly one .app bundle.")
    if not (apps[0] / "Contents" / "Info.plist").is_file():
        raise RuntimeError("The downloaded .app bundle is missing Contents/Info.plist.")
    return apps[0]


def install_macos(archive_path: Path, install_root: Path, staging_parent: Path) -> Path:
    current = app_bundle_from_root(install_root)
    extracted = staging_parent / "extract"
    extracted.mkdir(parents=True, exist_ok=True)
    # ditto preserves the bundle's internal relative symlinks and resource metadata.
    subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive_path), str(extracted)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    candidate = validate_single_app_bundle(extracted)
    candidate_name = extracted / current.name
    if candidate != candidate_name:
        candidate.rename(candidate_name)
        candidate = candidate_name

    backup = current.parent / f".{current.name}.backup-{os.getpid()}"
    try:
        os.replace(current, backup)
        try:
            os.replace(candidate, current)
        except Exception:
            os.replace(backup, current)
            raise
    except OSError as exc:
        raise RuntimeError(
            "The new build is verified, but macOS could not replace this app bundle. "
            "Move the app into a folder you can write to (for example ~/Applications) and retry."
        ) from exc
    shutil.rmtree(backup, ignore_errors=True)
    return current


def install_windows(archive_path: Path, install_root: Path, staging_parent: Path) -> Path:
    extracted = staging_parent / "extract"
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as archive:
        archive.extractall(extracted)
    if not (extracted / "ApeEscapeRecomp.exe").is_file():
        raise RuntimeError("The Windows update ZIP is missing ApeEscapeRecomp.exe.")

    # Merge only files shipped by the new package. Never overwrite user data,
    # and do not delete unknown/user-installed files from the installation.
    protected = {"saves", "settings.toml"}
    for source in extracted.rglob("*"):
        relative = source.relative_to(extracted)
        if not relative.parts or relative.parts[0] in protected:
            continue
        target = install_root / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f".nvd123-update-{os.getpid()}.tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    return install_root / "ApeEscapeRecomp.exe"


def detached_runtime_bootstrap(argv: list[str]) -> bool:
    """Run from a temp copy of bundled Python so Windows can replace that runtime."""
    if os.environ.get(BOOTSTRAPPED_ENV) == "1":
        return False
    exe = Path(sys.executable).resolve()
    parts = [part.lower() for part in exe.parts]
    try:
        overlay_index = parts.index("overlay_toolchain")
        if overlay_index + 1 >= len(parts) or parts[overlay_index + 1] != "python":
            return False
    except ValueError:
        return False

    source_python = exe.parent if os.name == "nt" else exe.parent.parent
    temp_root = Path(tempfile.mkdtemp(prefix="ape-escape-updater-runtime-"))
    target_python_root = temp_root / "python"
    shutil.copytree(source_python, target_python_root, dirs_exist_ok=True)
    staged_script = temp_root / "updater.py"
    shutil.copy2(Path(__file__).resolve(), staged_script)
    interpreter = target_python_root / ("python.exe" if os.name == "nt" else "bin/python3")
    if not interpreter.is_file():
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError("Could not start the updater from its temporary runtime copy.")

    env = os.environ.copy()
    env[BOOTSTRAPPED_ENV] = "1"
    env[RUNTIME_TEMP_ENV] = str(temp_root)
    command = [str(interpreter), str(staged_script), *argv]
    creationflags = (DETACHED_PROCESS | CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    try:
        subprocess.Popen(
            command, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags, start_new_session=(os.name != "nt"),
            close_fds=(os.name != "nt"),
        )
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return True


def cleanup_bootstrap_runtime() -> None:
    temp_path = os.environ.get(RUNTIME_TEMP_ENV)
    if not temp_path:
        return
    path = Path(temp_path)
    if os.name == "nt":
        # Windows cannot remove the running interpreter/DLLs; schedule cleanup
        # after this process exits. No shell-supplied user path is interpolated.
        command = f'for /L %i in (1,1,4) do @ping 127.0.0.1 -n 2 >nul & rmdir /s /q "{path}"'
        subprocess.Popen(["cmd.exe", "/c", command], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS)
    else:
        shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    install_root = args.install_root.resolve()

    try:
        suffix, checksum_name = platform_suffixes()
        local = local_provenance(install_root)
        local_commit = str(local.get("commit", "")).lower()

        release = get_json(API_RELEASE)
        if release.get("draft") or release.get("tag_name") != RELEASE_TAG:
            raise RuntimeError("The repository did not return the expected Nightly release.")
        assets_list = release.get("assets", [])
        if not isinstance(assets_list, list):
            raise RuntimeError("GitHub returned an invalid Nightly asset list.")
        assets = {str(item.get("name", "")): item for item in assets_list if isinstance(item, dict)}

        manifest_asset = assets.get("nightly-manifest.json")
        if not manifest_asset:
            raise RuntimeError(
                "This Nightly does not yet publish updater metadata. Install a newer Nightly after the updater pipeline is enabled."
            )
        manifest = get_json(str(manifest_asset.get("browser_download_url", "")))
        if manifest.get("repository") != REPOSITORY or manifest.get("channel") != "nightly":
            raise RuntimeError("The release metadata is not for the official nvd123 Nightly channel.")
        remote_commit = str(manifest.get("commit", "")).lower()
        if len(remote_commit) != 40 or any(ch not in "0123456789abcdef" for ch in remote_commit):
            raise RuntimeError("The Nightly metadata contains an invalid commit ID.")
        if local_commit and local_commit == remote_commit:
            notify(f"You are already up to date.\nInstalled commit: {remote_commit[:12]}")
            return 0

        package_matches = [item for item in assets_list
                           if isinstance(item, dict) and str(item.get("name", "")).endswith(suffix)]
        package_matches.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        if not package_matches:
            raise RuntimeError(f"The Nightly release does not include this platform package ({suffix}).")
        package = package_matches[0]
        checksum_asset = assets.get(checksum_name)
        if not checksum_asset:
            raise RuntimeError(f"The Nightly release is missing {checksum_name}.")

        version = str(manifest.get("version", "Nightly"))
        summary = (
            f"An Ape Escape Recompiled Nightly update is available.\n\n"
            f"Latest version: {version}\n"
            f"Latest commit: {remote_commit[:12]}\n"
            f"Installed commit: {local_commit[:12] if local_commit else 'unknown'}\n\n"
            "Download and verify the platform-specific update now?"
        )
        if not ask_yes_no(summary):
            return 0

        work = Path(tempfile.mkdtemp(prefix="ape-escape-nightly-update-"))
        archive_path = work / str(package.get("name", "update.zip"))
        checksum_path = work / checksum_name
        try:
            notify("Downloading the Nightly package and its SHA-256 checksum. This may take a little while.")
            download_to(str(package["browser_download_url"]), archive_path)
            download_to(str(checksum_asset["browser_download_url"]), checksum_path)
            expected_hash = checksum_for_asset(
                checksum_path.read_text(encoding="utf-8"),
                str(package.get("name", "")),
            )
            hasher = hashlib.sha256()
            with archive_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.hexdigest().lower() != expected_hash:
                raise RuntimeError("The downloaded ZIP failed SHA-256 verification and will not be installed.")

            is_macos = sys.platform == "darwin"
            verify_archive_paths(archive_path, allow_symlinks=is_macos)
            notify(
                "The Nightly ZIP is downloaded and SHA-256 verified.\n\n"
                "Click OK/Continue, then close Ape Escape Recompiled. "
                "The updater will wait for the app to exit before installing.",
            )
            wait_for_parent_exit(args.parent_pid)

            if is_macos:
                app = install_macos(archive_path, install_root, work)
                notify("Update installed successfully. Ape Escape Recompiled will reopen.")
                subprocess.Popen(["/usr/bin/open", str(app)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            else:
                exe = install_windows(archive_path, install_root, work)
                notify("Update installed successfully. Ape Escape Recompiled will reopen.")
                subprocess.Popen([str(exe)], cwd=str(install_root),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
            return 0
        finally:
            shutil.rmtree(work, ignore_errors=True)
    except Exception as exc:
        notify(
            f"The update was not installed.\n\n{exc}\n\n"
            "Your existing installation and saves have been left in place.",
            kind="error",
        )
        return 1
    finally:
        cleanup_bootstrap_runtime()


if __name__ == "__main__":
    raw_args = sys.argv[1:]
    try:
        if detached_runtime_bootstrap(raw_args):
            raise SystemExit(0)
        raise SystemExit(main())
    except Exception as exc:
        notify(f"The updater could not start safely:\n{exc}", kind="error")
        raise SystemExit(1)
