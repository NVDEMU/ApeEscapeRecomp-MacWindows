#!/usr/bin/env python3
"""Offline tests for the Nightly updater's checksum and archive-path checks."""
import importlib.util
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nvd123_in_app_updater", ROOT / "tools" / "in_app_updater.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not import updater helpers")
UPDATER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATER)


class NightlyUpdaterTests(unittest.TestCase):
    def test_updater_tls_context_requires_certificate_and_hostname_verification(self):
        context = UPDATER._https_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_bootstrap_copies_ca_bundle_next_to_staged_helper(self):
        original_file = UPDATER.__file__
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_python = root / "overlay_toolchain" / "python"
            if UPDATER.os.name == "nt":
                fake_executable = source_python / "python.exe"
            else:
                fake_executable = source_python / "bin" / "python3"
            fake_executable.parent.mkdir(parents=True)
            fake_executable.write_text("test interpreter", encoding="utf-8")

            source_script = root / "app" / "update" / "updater.py"
            source_script.parent.mkdir(parents=True)
            source_script.write_text("# test updater", encoding="utf-8")
            (source_script.parent / "cacert.pem").write_text(
                "test CA bundle contents", encoding="utf-8"
            )

            UPDATER.__file__ = str(source_script)
            temp_runtime = None
            try:
                with mock.patch.object(UPDATER.sys, "executable", str(fake_executable)), \
                     mock.patch.dict(UPDATER.os.environ, {UPDATER.BOOTSTRAPPED_ENV: "0"}), \
                     mock.patch.object(UPDATER.subprocess, "Popen") as popen:
                    self.assertTrue(UPDATER.detached_runtime_bootstrap([]))
                    child_env = popen.call_args.kwargs["env"]
                    temp_runtime = Path(child_env[UPDATER.RUNTIME_TEMP_ENV])
                    self.assertEqual(
                        (temp_runtime / "cacert.pem").read_text(encoding="utf-8"),
                        "test CA bundle contents",
                    )
            finally:
                UPDATER.__file__ = original_file
                if temp_runtime is not None:
                    UPDATER.shutil.rmtree(temp_runtime, ignore_errors=True)

    def test_metadata_request_passes_a_verified_tls_context(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"ok": true}'

        with mock.patch.object(UPDATER.urllib.request, "urlopen", return_value=Response()) as urlopen:
            self.assertEqual(UPDATER.http_bytes("https://example.invalid/test"), b'{"ok": true}')

        context = urlopen.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

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

    def test_macos_update_preserves_user_data_without_restoring_stale_bundled_mods(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_bundle = root / "ApeEscapeRecomp.app"
            new_bundle = root / "candidate" / "ApeEscapeRecomp.app"
            old_runtime = old_bundle / "Contents" / "MacOS"
            new_runtime = new_bundle / "Contents" / "MacOS"
            old_runtime.mkdir(parents=True)
            new_runtime.mkdir(parents=True)

            # The executable and shipped runtimes are refreshed by the Nightly.
            (old_runtime / "ApeEscapeRecomp").write_text("old executable", encoding="utf-8")
            (new_runtime / "ApeEscapeRecomp").write_text("new executable", encoding="utf-8")
            (new_runtime / "runtime-new.dylib").write_text("new runtime", encoding="utf-8")

            preserved = {
                "disc.cfg": "/Users/player/Games/Ape Escape.cue\n",
                "bios.cfg": "/Users/player/BIOS/SCPH1001.BIN\n",
                "keybinds.ini": "[player1]\\ncross = X\\nrs_up = UP\\n",
                "input.ini": "[controller]\\ndevice = 0\\n",
                "settings.toml": '[video]\\ninternal_resolution = "1080p"\\n',
                "config.ini": "[KeyMap]\\nstart = Return\\n",
                "launcher-window.ini": "width=1200\\n",
                "ape_escape_launcher.ini": "text_percent=125\\nhigh_contrast=1\\n",
                "game_options.toml": "[game]\\noption = true\\n",
            }
            for relative, content in preserved.items():
                target = old_runtime / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                (new_runtime / relative).write_text(
                    "packaged default must not overwrite user data", encoding="utf-8"
                )

            (old_runtime / "saves").mkdir()
            (old_runtime / "saves" / "card1.mcd").write_bytes(b"user memory card")
            (new_runtime / "saves").mkdir()
            (new_runtime / "saves" / "default.txt").write_text("new file", encoding="utf-8")

            old_mods = old_runtime / "mods"
            (old_mods / "state.toml").parent.mkdir(parents=True)
            (old_mods / "state.toml").write_text("[features]\\nwidescreen = false\\n", encoding="utf-8")
            (old_mods / "custom" / "my-addon").mkdir(parents=True)
            (old_mods / "custom" / "my-addon" / "manifest.toml").write_text(
                'id = "my-addon"\\n', encoding="utf-8"
            )
            (old_mods / "preloaded" / "old-bundled").mkdir(parents=True)
            (old_mods / "preloaded" / "old-bundled" / "manifest.toml").write_text(
                'id = "stale-bundled"\\n', encoding="utf-8"
            )

            new_mods = new_runtime / "mods"
            (new_mods / "state.toml").parent.mkdir(parents=True)
            (new_mods / "state.toml").write_text("[features]\\nwidescreen = true\\n", encoding="utf-8")
            (new_mods / "preloaded" / "new-bundled").mkdir(parents=True)
            (new_mods / "preloaded" / "new-bundled" / "manifest.toml").write_text(
                'id = "new-bundled"\\n', encoding="utf-8"
            )

            UPDATER.preserve_macos_user_data(old_bundle, new_bundle)

            self.assertEqual((new_runtime / "ApeEscapeRecomp").read_text(encoding="utf-8"),
                             "new executable")
            self.assertEqual((new_runtime / "runtime-new.dylib").read_text(encoding="utf-8"),
                             "new runtime")
            for relative, expected in preserved.items():
                with self.subTest(path=relative):
                    self.assertEqual((new_runtime / relative).read_text(encoding="utf-8"), expected)
            self.assertEqual((new_runtime / "saves" / "card1.mcd").read_bytes(), b"user memory card")
            self.assertTrue((new_runtime / "saves" / "default.txt").is_file())
            self.assertEqual(
                (new_mods / "state.toml").read_text(encoding="utf-8"),
                "[features]\\nwidescreen = false\\n",
            )
            self.assertTrue((new_mods / "custom" / "my-addon" / "manifest.toml").is_file())
            self.assertFalse((new_mods / "preloaded" / "old-bundled").exists())
            self.assertTrue((new_mods / "preloaded" / "new-bundled" / "manifest.toml").is_file())

    def test_rollback_snapshot_and_restore_preserve_windows_user_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = root / "install"
            install.mkdir()
            (install / "ApeEscapeRecomp.exe").write_text("old runtime", encoding="utf-8")
            (install / "runtime.dll").write_text("old runtime dll", encoding="utf-8")
            (install / "config.ini").write_text("player settings", encoding="utf-8")
            (install / "saves").mkdir()
            (install / "saves" / "card.mcd").write_bytes(b"save")
            (install / "mods").mkdir()
            (install / "mods" / "state.toml").write_text("enabled=false", encoding="utf-8")
            with mock.patch.object(UPDATER, "rollback_archive_path", return_value=root / "user-data" / "rollback.zip"):
                saved = UPDATER.snapshot_windows_install(install)
                (install / "ApeEscapeRecomp.exe").write_text("new runtime", encoding="utf-8")
                (install / "runtime.dll").write_text("new runtime dll", encoding="utf-8")
                (install / "new-file.dll").write_text("new only", encoding="utf-8")
                staging = root / "staging"
                staging.mkdir()
                restored = UPDATER.restore_windows_rollback(install, staging)
                self.assertEqual(restored.read_text(encoding="utf-8"), "old runtime")
                self.assertEqual((install / "runtime.dll").read_text(encoding="utf-8"), "old runtime dll")
                self.assertFalse((install / "new-file.dll").exists())
                self.assertEqual((install / "config.ini").read_text(encoding="utf-8"), "player settings")
                self.assertEqual((install / "saves" / "card.mcd").read_bytes(), b"save")
                self.assertEqual((install / "mods" / "state.toml").read_text(encoding="utf-8"), "enabled=false")
                self.assertEqual(saved, root / "user-data" / "rollback.zip")
                self.assertTrue(saved.is_file())

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
