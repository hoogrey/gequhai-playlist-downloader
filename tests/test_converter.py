import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import convert_aac_to_mp3 as converter


class ConverterTests(unittest.TestCase):
    def test_output_dir_uses_downloaders_out_argument(self):
        self.assertEqual(
            converter.output_dir_from_download_args(
                ["--csv", "my playlist.csv", "--out", "other downloads", "--top", "3"]
            ),
            Path("other downloads"),
        )
        self.assertIsNone(converter.output_dir_from_download_args(["--dry-run"]))

    def test_prefers_bundled_ffmpeg_and_allows_explicit_override(self):
        with patch("imageio_ffmpeg.get_ffmpeg_exe", return_value="bundled-ffmpeg"):
            self.assertEqual(converter.resolve_ffmpeg(), "bundled-ffmpeg")
            self.assertEqual(converter.resolve_ffmpeg("custom-ffmpeg"), "custom-ffmpeg")

    def test_convert_file_removes_source_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "song.aac"
            src.write_bytes(b"aac")

            def fake_run(command, check):
                Path(command[-1]).write_bytes(b"mp3")

            with patch.object(converter.subprocess, "run", side_effect=fake_run) as run:
                dest = converter.convert_file(src, "ffmpeg")

            self.assertEqual(dest.suffix, ".mp3")
            self.assertEqual(dest.read_bytes(), b"mp3")
            self.assertFalse(src.exists())
            run.assert_called_once()

    def test_convert_file_can_keep_source(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "song.acc"
            src.write_bytes(b"acc")

            def fake_run(command, check):
                Path(command[-1]).write_bytes(b"mp3")

            with patch.object(converter.subprocess, "run", side_effect=fake_run):
                dest = converter.convert_file(src, "ffmpeg", keep_source=True)

            self.assertTrue(src.exists())
            self.assertTrue(dest.exists())

    def test_failed_conversion_keeps_source_and_removes_partial_target(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "song.aac"
            src.write_bytes(b"aac")

            def fake_run(command, check):
                Path(command[-1]).write_bytes(b"partial")
                raise subprocess.CalledProcessError(1, command)

            with patch.object(converter.subprocess, "run", side_effect=fake_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    converter.convert_file(src, "ffmpeg")

            self.assertTrue(src.exists())
            self.assertFalse((Path(directory) / "song.mp3").exists())

    def test_success_without_output_keeps_source(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "song.aac"
            src.write_bytes(b"aac")

            with patch.object(converter.subprocess, "run"):
                with self.assertRaisesRegex(RuntimeError, "未生成有效的 MP3"):
                    converter.convert_file(src, "ffmpeg")

            self.assertTrue(src.exists())
            self.assertFalse((Path(directory) / "song.mp3").exists())

    def test_unique_target_path_does_not_overwrite_existing_mp3(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "song.aac"
            src.write_bytes(b"aac")
            (root / "song.mp3").write_bytes(b"existing")

            def fake_run(command, check):
                Path(command[-1]).write_bytes(b"mp3")

            with patch.object(converter.subprocess, "run", side_effect=fake_run):
                dest = converter.convert_file(src, "ffmpeg")

            self.assertEqual(dest.name, "song (2).mp3")
            self.assertEqual((root / "song.mp3").read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
