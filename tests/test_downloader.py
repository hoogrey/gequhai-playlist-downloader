import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

import gequhai_downloader as downloader


class DownloaderTests(unittest.TestCase):
    def test_supported_playlist_csv_exports(self):
        exports = (
            ("\ufeff歌曲标题,歌手\n\"歌名,现场版\",歌手甲\n", ["歌名,现场版 歌手甲"]),
            ("# 歌单: 示例,备份\n序号,歌曲标题,歌手\n1,示例歌曲,歌手乙\n", ["示例歌曲 歌手乙"]),
            ("序号,歌名,副标题,歌手\n1,示例歌曲,,歌手丙\n", ["示例歌曲 歌手丙"]),
            ("Track URI,Track Name,Artist Name(s)\nspotify:track:123,Example Song,Example Artist\n", ["Example Song Example Artist"]),
            ("歌曲标题,歌手\n'-特别版,'+歌手甲\n", ["-特别版 +歌手甲"]),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "playlist.csv"
            for content, expected in exports:
                with self.subTest(header=content.splitlines()[0]):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(downloader.read_playlist_queries(path), expected)

    def test_playlist_csv_requires_title_and_artist_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "playlist.csv"
            path.write_text("歌名,专辑\n示例歌曲,示例专辑\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "缺少歌手列"):
                downloader.read_playlist_queries(path)

    def test_search_http_error_is_not_treated_as_no_results(self):
        response = MagicMock(ok=False, status=503)
        request_ctx = MagicMock()
        request_ctx.get.return_value = response

        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            downloader.fetch_play_ids_for_keyword(
                request_ctx=request_ctx,
                keyword="测试",
                use_browser_fallback=False,
                debug_dir=None,
                playwright=None,
                user_agent=downloader.UA,
            )

    def test_interrupted_download_removes_partial_file(self):
        response = MagicMock()

        def chunks():
            yield b"partial"
            raise requests.ConnectionError("interrupted")

        response.iter_content.return_value = chunks()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "song.mp3"
            with patch.object(downloader.requests, "get") as get:
                get.return_value.__enter__.return_value = response
                with self.assertRaises(requests.ConnectionError):
                    downloader.download_file("https://example.com/song.mp3", target)

            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_successful_download_uses_final_filename(self):
        response = MagicMock()
        response.iter_content.return_value = iter([b"first", b"second"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "song.mp3"
            with patch.object(downloader.requests, "get") as get:
                get.return_value.__enter__.return_value = response
                downloader.download_file("https://example.com/song.mp3", target)

            self.assertEqual(target.read_bytes(), b"firstsecond")
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_dry_run_does_not_create_output_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            playlist = root / "playlist.csv"
            playlist.write_text("歌曲标题,歌手\n测试歌曲,测试歌手\n", encoding="utf-8")
            output = root / "downloads"
            info = downloader.PlayInfo("123", "api-id", 0, "歌名", "歌手", "")

            with (
                patch("sys.argv", ["gequhai_downloader.py", "--csv", str(playlist), "--out", str(output), "--dry-run"]),
                patch.object(downloader, "sync_playwright") as playwright,
                patch.object(downloader, "fetch_play_ids_for_keyword", return_value=["123"]),
                patch.object(downloader, "parse_play_info", return_value=info),
                patch.object(downloader, "resolve_download_url", return_value=("direct", "https://example.com/song.mp3")),
                patch.object(downloader, "convert_kuwo_antiserver_url", return_value="https://example.com/song.mp3"),
                patch.object(downloader.time, "sleep"),
            ):
                playwright.return_value.__enter__.return_value = MagicMock()
                self.assertEqual(downloader.main(), 0)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
