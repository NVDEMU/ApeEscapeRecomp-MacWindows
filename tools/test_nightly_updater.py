#!/usr/bin/env python3
"""Offline tests for the Nightly updater's checksum and archive-path checks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nvd123_in_app_updater", ROOT / "tools" / "in_app_updater.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not import updater helpers")
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


class NightlyUpdaterTests(unittest.TestCase):
    def test_checksum_parser_selects_exact_asset(self):
        text = "a" * 64 + "  other.zip\n" + "b" * 64 + "  current.zip\n"
        self.assertEqual(UPDATER.checksum_for_asset(text, "current.zip"), "b" * 64)

    def test_checksum_parser_rejects_missing_asset(self):
        with self.assertRaises(RuntimeError):
            UPDATER.checksum_for_asset("c" * 64 + "  other.zip\n", "current.zip")

    def test_archive_accepts_normal_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "valid.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("ApeEscapeRecomp.exe", "dummy")
                archive.writestr("saves/keep.txt", "save")
            UPDATER.verify_archive_paths(path, allow_symlinks=False)

    def test_archive_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape.txt", "must not escape")
            with self.assertRaises(RuntimeError):
                UPDATER.verify_archive_paths(path, allow_symlinks=False)

    def test_archive_rejects_windows_backslash_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(r"folder\..\escape.txt", "must not escape")
            with self.assertRaises(RuntimeError):
                UPDATER.verify_archive_paths(path, allow_symlinks=False)


    def test_windows_update_preserves_player_configuration_but_updates_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install_root = root / "installed"
            staging_parent = root / "update-staging"
            install_root.mkdir()
            staging_parent.mkdir()

            preserved = {
                "disc.cfg": "/Users/player/Games/Ape Escape.cue",
                "bios.cfg": "/Users/player/BIOS/SCPH1001.BIN",
                "keybinds.ini": "[player1]\ncross = X\nrs_up = UP\n",
                "input.ini": "[controller]\ndevice = 0\n",
                "settings.toml": '[video]\ninternal_resolution = "1080p"\n',
                "config.ini": "[KeyMap]\nstart = Return\n",
                "launcher-window.ini": "width=1200\n",
                "ape_escape_launcher.ini": "text_percent=125\nhigh_contrast=1\n",
                "mods/state.toml": "[features]\nwidescreen = false\n",
            }
            for relative, content in preserved.items():
                target = install_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            archive_path = root / "nightly.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("ApeEscapeRecomp.exe", "new runtime")
                archive.writestr("bin/runtime.dll", "new DLL")
                for relative in preserved:
                    archive.writestr(relative, "packaged default must not overwrite player data")

            UPDATER.install_windows(archive_path, install_root, staging_parent)

            self.assertEqual((install_root / "ApeEscapeRecomp.exe").read_text(encoding="utf-8"),
                             "new runtime")
            self.assertEqual((install_root / "bin/runtime.dll").read_text(encoding="utf-8"),
                             "new DLL")
            for relative, expected in preserved.items():
                with self.subTest(path=relative):
                    self.assertEqual((install_root / relative).read_text(encoding="utf-8"),
                                     expected)

    def test_windows_update_rejects_unsafe_archive_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install_root = root / "installed"
            staging_parent = root / "staging"
            install_root.mkdir()
            staging_parent.mkdir()
            archive_path = root / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("ApeEscapeRecomp.exe", "new runtime")
                archive.writestr("../outside.txt", "must not escape")
            with self.assertRaises(RuntimeError):
                UPDATER.install_windows(archive_path, install_root, staging_parent)
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
