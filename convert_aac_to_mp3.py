"""将下载目录中的 AAC 音频转码为 MP3。

该脚本调用项目依赖提供的 FFmpeg 进行真正的音频编码转换。它不会通过修改
文件名后缀伪造 MP3；只有 FFmpeg 成功写出目标文件后，才会删除源文件。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parent / "downloads"
AAC_SUFFIXES = {".aac", ".acc"}


def unique_target_path(path: Path) -> Path:
    """为已存在的目标文件生成不冲突的文件名。"""
    if not path.exists():
        return path

    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many duplicates for: {path.name}")


def find_audio_files(base_dir: Path, recursive: bool) -> list[Path]:
    """查找待转码的 AAC 文件，按路径排序以保证输出稳定。"""
    pattern = "**/*" if recursive else "*"
    return sorted(
        (
            path
            for path in base_dir.glob(pattern)
            if path.is_file() and path.suffix.lower() in AAC_SUFFIXES
        ),
        key=lambda path: str(path).casefold(),
    )


def output_dir_from_download_args(args: list[str]) -> Path | None:
    """读取下载器收到的 --out 参数，供一键启动器定位实际输出目录。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--out", type=Path)
    parsed, _ = parser.parse_known_args(args)
    return parsed.out


def resolve_ffmpeg(explicit_path: str | None = None) -> str | None:
    """优先使用指定路径，其次使用 Python 依赖自带的 FFmpeg。"""
    if explicit_path:
        return explicit_path

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        return shutil.which("ffmpeg")


def convert_file(src: Path, ffmpeg: str, keep_source: bool = False) -> Path:
    """使用 FFmpeg 将一个 AAC 文件转成 MP3。"""
    dest = unique_target_path(src.with_suffix(".mp3"))
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-map_metadata",
        "0",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(dest),
    ]

    try:
        subprocess.run(command, check=True)
        if not dest.is_file() or dest.stat().st_size == 0:
            raise RuntimeError("FFmpeg 未生成有效的 MP3 文件")
    except (OSError, subprocess.CalledProcessError, RuntimeError):
        # FFmpeg 失败时清理可能留下的不完整目标文件，保留源文件便于重试。
        if dest.exists():
            dest.unlink()
        raise

    if not keep_source:
        src.unlink()
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="使用 FFmpeg 将 .aac/.acc 音频真正转码为 .mp3"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help="要处理的目录（默认：脚本目录下的 downloads）",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="递归处理子目录",
    )
    parser.add_argument(
        "--ffmpeg",
        default=None,
        help="FFmpeg 可执行文件路径；默认使用项目依赖提供的版本",
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="转码成功后保留原始 .aac/.acc 文件",
    )
    parser.add_argument(
        "--download-args",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    base_dir: Path = output_dir_from_download_args(args.download_args or []) or args.dir
    if not base_dir.exists() or not base_dir.is_dir():
        print(f"目录不存在或不是目录：{base_dir}")
        return 2

    files = find_audio_files(base_dir, args.recursive)
    if not files:
        print("未找到需要转码的 .aac/.acc 文件。")
        return 0

    ffmpeg = resolve_ffmpeg(args.ffmpeg)
    if not ffmpeg:
        print("未找到 FFmpeg。请重新安装 requirements.txt，或使用 --ffmpeg 指定路径。")
        return 2

    converted = 0
    failed = 0
    for src in files:
        try:
            dest = convert_file(src, ffmpeg, keep_source=args.keep_source)
            converted += 1
            print(f"转码：{src.name}  ->  {dest.name}")
        except AssertionError:
            raise
        except Exception as exc:
            failed += 1
            print(f"转码失败：{src.name}：{exc}")

    print(f"完成：成功转码 {converted} 个，失败 {failed} 个")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
