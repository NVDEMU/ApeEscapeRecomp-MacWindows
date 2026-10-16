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


if __name__ == "__main__":
    unittest.main(verbosity=2)
