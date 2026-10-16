#!/usr/bin/env python3
"""Local tests for the release-disc downloader; no network or game assets needed."""
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

# Executing this file directly puts tools/ rather than the repository root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.download_disc as download_disc
from tools.download_disc import CHD_MAGIC, MIN_CHD_BYTES, shared_url_variants, validate_chd


class DownloadDiscTests(unittest.TestCase):
    def test_valid_chd_header_and_minimum_size(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "valid.chd"
            with image.open("wb") as stream:
                stream.write(CHD_MAGIC)
                stream.write(b"\0" * (MIN_CHD_BYTES - len(CHD_MAGIC)))
            self.assertEqual(validate_chd(image), MIN_CHD_BYTES)

    def test_html_page_is_rejected_as_not_a_chd(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "bad.chd"
            image.write_bytes(b"<!DOCTYPE html>" + b" " * (MIN_CHD_BYTES + 100))
            with self.assertRaisesRegex(ValueError, "header"):
                validate_chd(image)

    def test_too_small_chd_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "small.chd"
            image.write_bytes(CHD_MAGIC + b"\0" * 32)
            with self.assertRaisesRegex(ValueError, "size"):
                validate_chd(image)

    def test_dropbox_shared_link_tries_raw_then_download(self):
        variants = shared_url_variants(
            "https://www.dropbox.com/scl/fi/example/ApeEscape.chd?rlkey=abc&dl=0"
        )
        self.assertGreaterEqual(len(variants), 2)
        self.assertEqual(variants[0][0], "Dropbox dl=1")
        self.assertIn("dl=1", variants[0][1])
        self.assertIn("rlkey=abc", variants[0][1])
        self.assertEqual(variants[1][0], "Dropbox raw=1")
        self.assertIn("raw=1", variants[1][1])

    def test_non_dropbox_url_is_preserved(self):
        url = "https://example.invalid/disc.chd?token=private"
        self.assertEqual(shared_url_variants(url), [("provided URL", url)])

    def test_old_dropbox_public_link_adds_content_host_fallback(self):
        variants = shared_url_variants("https://www.dropbox.com/s/abc123/disc.chd?dl=0")
        self.assertEqual(variants[-1][0], "Dropbox legacy content host")
        self.assertTrue(variants[-1][1].startswith("https://dl.dropboxusercontent.com/s/abc123/"))

    def test_modern_scl_link_keeps_access_key_and_uses_dl_first(self):
        variants = shared_url_variants(
            "https://www.dropbox.com/scl/fi/shareid/disc.chd?rlkey=abc&dl=0"
        )
        self.assertEqual(variants[0][0], "Dropbox dl=1")
        self.assertIn("rlkey=abc", variants[0][1])
        self.assertIn("dl=1", variants[0][1])
        self.assertEqual(len(variants), 2)

    def test_shared_download_uses_curl_default_user_agent(self):
        url = "https://www.dropbox.com/scl/fi/shareid/disc.chd?rlkey=abc&dl=1"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "disc.chd"
            with patch.object(
                download_disc.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(args=["curl"], returncode=0, stdout="", stderr=""),
            ) as run:
                download_disc.download_shared_url(url, destination)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "curl")
        self.assertIn("--location", command)
        self.assertIn("--retry", command)
        self.assertEqual(command[command.index("--output") + 1], str(destination))
        self.assertNotIn("--user-agent", " ".join(command).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
