import argparse
import csv
import os
import re
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.gequhai.com"
PROJECT_DIR = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class PlayInfo:
    play_numeric_id: str
    play_api_id: str
    mp3_type: int
    title: str
    author: str
    extra_url_raw: str


TITLE_COLUMNS = ("歌曲标题", "歌名", "Track Name")
ARTIST_COLUMNS = ("歌手", "Artist Name(s)")


def read_playlist_queries(path: Path) -> list[str]:
    """从常见歌单导出 CSV 的歌名、歌手列生成搜索词。"""

    def search_text(value: str) -> str:
        value = value.strip()
        # Playlist Out 为防 CSV 公式注入会给这些值添加前导单引号。
        if len(value) > 1 and value[0] == "'" and value[1] in "=+-@":
            return value[1:]
        return value

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        for header in reader:
            if not header or not any(cell.strip() for cell in header):
                continue
            # Playlist Out 的增强 CSV 可在表头前附加单列元数据行。
            if header[0].lstrip().startswith("#"):
                continue
            break
        else:
            raise ValueError("CSV 为空或没有表头")

        columns = {name.strip().casefold(): index for index, name in enumerate(header)}

        def find_column(aliases: tuple[str, ...], label: str) -> int:
            for alias in aliases:
                if alias.casefold() in columns:
                    return columns[alias.casefold()]
            raise ValueError(f"CSV 缺少{label}列；现有列：{', '.join(header)}")

        title_index = find_column(TITLE_COLUMNS, "歌名")
        artist_index = find_column(ARTIST_COLUMNS, "歌手")
        queries: list[str] = []
        for row in reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) <= max(title_index, artist_index):
                raise ValueError(f"CSV 第 {reader.line_num} 行缺少歌名或歌手字段")
            title = search_text(row[title_index])
            artist = search_text(row[artist_index])
            if not title or not artist:
                print(f"跳过 CSV 第 {reader.line_num} 行：歌名或歌手为空")
                continue
            queries.append(f"{title} {artist}")
        return queries


_invalid_filename_chars = re.compile(r"[<>:\\/*?\"|\x00-\x1F]")


def sanitize_filename(name: str) -> str:
    name = _invalid_filename_chars.sub("_", name)
    name = name.rstrip(" .")
    return name or "unnamed"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 9999):
        p = path.with_name(f"{stem} ({i}){suffix}")
        if not p.exists():
            return p
    raise RuntimeError(f"Too many duplicates for {path.name}")


def extract_play_ids_from_search_html(html: str) -> list[str]:
    # 搜索结果的链接可能是相对或绝对地址，也可能带查询参数。
    ids = re.findall(
        r"href\s*=\s*['\"](?:https?://(?:www\.)?gequhai\.com)?/play/(\d+)(?:\?[^'\"]*)?['\"]",
        html,
        flags=re.IGNORECASE,
    )
    seen: set[str] = set()
    out: list[str] = []
    for pid in ids:
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def maybe_save_debug(text: str, path: Path | None) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def ensure_utf8_bom(path: Path) -> None:
    """为已有的非空 UTF-8 文本补充 BOM，方便 Windows 工具读取。

    文件不存在、为空或已有 BOM 时不重写。
    """

    try:
        if not path.exists() or path.stat().st_size <= 0:
            return
    except OSError:
        return

    try:
        with open(path, "rb") as f:
            head = f.read(3)
        if head == b"\xef\xbb\xbf":
            return
    except OSError:
        return

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(text, encoding="utf-8-sig")


def append_line_utf8_bom(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        exists_and_nonempty = path.exists() and path.stat().st_size > 0
    except OSError:
        exists_and_nonempty = False

    if exists_and_nonempty:
        ensure_utf8_bom(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    else:
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(line + "\n")


def fetch_play_ids_for_keyword(
    *,
    request_ctx,
    keyword: str,
    use_browser_fallback: bool,
    debug_dir: Path | None,
    playwright,
    user_agent: str,
) -> list[str]:
    # 将整个关键词编码为单个 URL 路径段。
    search_url = f"{BASE_URL}/s/{urllib.parse.quote(keyword, safe='')}"

    resp = request_ctx.get(search_url)
    if not resp.ok:
        raise RuntimeError(f"搜索请求失败：HTTP {resp.status} ({search_url})")
    html = resp.text()
    maybe_save_debug(html, (debug_dir / f"search_{sanitize_filename(keyword)}.html") if debug_dir else None)

    play_ids = extract_play_ids_from_search_html(html)
    if play_ids:
        return play_ids

    if not use_browser_fallback:
        return []

    # 静态 HTML 没有结果时，再尝试浏览器渲染后的 DOM。
    browser = playwright.chromium.launch(headless=True)
    try:
        ctx = browser.new_context(user_agent=user_agent)
        page = ctx.new_page()
        page.goto(search_url, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        hrefs = page.eval_on_selector_all(
            "a[href*='/play/']",
            "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
        )
        ids: list[str] = []
        for href in hrefs:
            m = re.search(r"/play/(\d+)", href)
            if m:
                ids.append(m.group(1))
        # 保留搜索结果顺序并去重。
        seen: set[str] = set()
        out: list[str] = []
        for pid in ids:
            if pid in seen:
                continue
            seen.add(pid)
            out.append(pid)
        if out:
            return out
        # 浏览器回退仍失败时保存页面，便于排查站点结构变化。
        rendered = page.content()
        maybe_save_debug(
            rendered,
            (debug_dir / f"search_{sanitize_filename(keyword)}.rendered.html") if debug_dir else None,
        )
        return []
    finally:
        browser.close()


def parse_play_info(html: str, play_numeric_id: str) -> PlayInfo:
    def pick(pattern: str, label: str) -> str:
        m = re.search(pattern, html)
        if not m:
            raise ValueError(f"Missing {label} in play page {play_numeric_id}")
        return m.group(1)

    play_api_id = pick(r"window\.play_id\s*=\s*'([^']+)'", "window.play_id")
    mp3_type_str = pick(r"window\.mp3_type\s*=\s*(\d+)", "window.mp3_type")
    title = pick(r"window\.mp3_title\s*=\s*'([^']+)'", "window.mp3_title")
    author = pick(r"window\.mp3_author\s*=\s*'([^']+)'", "window.mp3_author")
    extra_url_raw = ""
    m_extra = re.search(r"window\.mp3_extra_url\s*=\s*'([^']*)'", html)
    if m_extra:
        extra_url_raw = m_extra.group(1)

    return PlayInfo(
        play_numeric_id=str(play_numeric_id),
        play_api_id=play_api_id,
        mp3_type=int(mp3_type_str),
        title=title,
        author=author,
        extra_url_raw=extra_url_raw,
    )


def decode_modified_base64(value: str) -> str | None:
    if not value:
        return None
    try:
        import base64

        normalized = value.replace("#", "H").replace("%", "S")
        raw = base64.b64decode(normalized)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def resolve_download_url(
    request_ctx,
    info: PlayInfo,
    *,
    preferred_types: list[int],
    max_retries: int = 3,
) -> tuple[str, str]:
    """返回 (链接类型, URL)。

    direct 表示 /api/music 返回的媒体直链；extra 表示页面提供的备用链接。
    """
    headers = {
        "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
        "X-Custom-Header": "SecretKey",
        "Referer": f"{BASE_URL}/play/{info.play_numeric_id}",
    }

    tried: list[tuple[int, object]] = []

    def parse_wait_seconds(msg: str) -> int | None:
        m = re.search(r"(\d+)\s*秒后再试", msg)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    for mp3_type in preferred_types:
        for attempt in range(1, max_retries + 1):
            resp = request_ctx.post(
                f"{BASE_URL}/api/music",
                form={"id": info.play_api_id, "type": str(mp3_type)},
                headers=headers,
            )

            try:
                data = resp.json()
            except Exception:
                data = None

            # 常见成功响应：{ code: 200, data: { url: "..." } }。
            if isinstance(data, dict) and data.get("code") == 200:
                url = (data.get("data") or {}).get("url")
                if isinstance(url, str) and url:
                    return ("direct", url)

            # 接口限流时按次数退避。
            if isinstance(data, dict) and data.get("code") == 429:
                sleep_s = 2.0 * attempt
                print(f"  /api/music 触发频控(429)，等待 {sleep_s:.1f}s 重试...")
                time.sleep(sleep_s)
                continue

            # 当前音质没有在线音源，尝试下一个类型。
            if isinstance(data, dict) and data.get("code") == 100:
                msg = data.get("msg")
                if isinstance(msg, str) and "请求过于频繁" in msg:
                    wait_s = parse_wait_seconds(msg) or int(2.0 * attempt)
                    wait_s = max(1, min(wait_s, 120))
                    print(f"  /api/music 提示等待 {wait_s}s（限流），重试...")
                    time.sleep(wait_s)
                    continue

                tried.append((mp3_type, msg))
                break

            # 未知响应交由上层记录，并尝试下一个搜索结果。
            raise RuntimeError(
                f"/api/music 获取失败(play={info.play_numeric_id}) type={mp3_type} status={resp.status} body={data}"
            )

    decoded = decode_modified_base64(info.extra_url_raw)
    if decoded:
        return ("extra", decoded)

    raise RuntimeError(
        f"/api/music 无可用直链且无 mp3_extra_url(play={info.play_numeric_id}) tried={tried}"
    )


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 部分媒体 CDN 会拒绝带 Referer 的请求。
    headers = {"User-Agent": UA, "Accept": "*/*"}
    temp_path: Path | None = None
    try:
        with requests.get(url, stream=True, headers=headers, timeout=60) as r:
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{dest.name}.", suffix=".part", dir=dest.parent, delete=False
            ) as f:
                temp_path = Path(f.name)
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        os.replace(temp_path, dest)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def convert_kuwo_antiserver_url(url: str) -> str:
    """按网页使用的 convert_url3 接口转换酷我中转地址。"""

    if "antiserver.kuwo.cn" not in url:
        return url

    parsed = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    q["type"] = "convert_url3"
    q["callback"] = "__cb"
    converted = parsed._replace(query=urllib.parse.urlencode(q))
    converted_url = urllib.parse.urlunparse(converted)

    headers = {"User-Agent": UA, "Accept": "*/*"}
    r = requests.get(converted_url, headers=headers, timeout=30)
    r.raise_for_status()
    text = r.text.strip()

    # 网页接口返回 JSONP：__cb({...})。
    m = re.match(r"^[\w$]+\((\{.*\})\)\s*;?\s*$", text)
    if not m:
        return url

    try:
        import json

        payload: Any = json.loads(m.group(1))
    except Exception:
        return url

    if isinstance(payload, dict) and payload.get("code") == 200 and isinstance(
        payload.get("url"), str
    ):
        return payload["url"]
    return url


def is_share_link(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return True
    return host.endswith("pan.quark.cn")


def guess_extension_from_url(url: str, default: str = ".mp3") -> str:
    try:
        path = urllib.parse.urlparse(url).path
        ext = Path(path).suffix
        if ext and len(ext) <= 6:
            return ext
    except Exception:
        pass
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description="gequhai.com 批量下载（Playwright）")
    parser.add_argument(
        "--csv", type=Path, default=PROJECT_DIR / "playlist.csv",
        help="歌单 CSV（默认：脚本目录下的 playlist.csv）",
    )
    parser.add_argument(
        "--out", type=Path, default=PROJECT_DIR / "downloads",
        help="输出目录（默认：脚本目录下的 downloads）",
    )
    parser.add_argument("--top", type=int, default=1, help="每首歌取前 N 条搜索结果")
    parser.add_argument(
        "--delay", type=float, default=1.0, help="请求间隔（秒），避免触发频控"
    )
    parser.add_argument(
        "--browser-fallback",
        action="store_true",
        default=True,
        help="当纯 HTML 解析不到结果时，使用浏览器模式回退抓取（默认开启）",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_false",
        dest="browser_fallback",
        help="禁用浏览器回退（更快，但可能漏掉少数结果）",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        default=False,
        help="保存搜索页 HTML 到输出目录下的 _debug 方便排查",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="只解析并输出直链/分享链接，不写入文件",
    )
    parser.add_argument(
        "--prefer-low",
        action="store_true",
        default=True,
        help="优先尝试低品质直链(type=0)，避免外部分享链接（默认开启）",
    )
    parser.add_argument(
        "--no-prefer-low",
        action="store_false",
        dest="prefer_low",
        help="禁用优先低品质；优先使用页面 type",
    )
    args = parser.parse_args()

    if args.top <= 0:
        parser.error("--top 必须 > 0")
    if args.delay < 0:
        parser.error("--delay 不能为负数")
    if not args.csv.is_file():
        parser.error(f"找不到歌单 CSV：{args.csv}（请参考 playlist.example.csv）")

    try:
        keywords = read_playlist_queries(args.csv)
    except (csv.Error, OSError, UnicodeError, ValueError) as e:
        parser.error(f"读取歌单 CSV 失败：{e}")
    if not keywords:
        parser.error(f"歌单 CSV 没有有效歌曲：{args.csv}")

    out_dir: Path = args.out
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    not_found_path = out_dir / "not_found.txt"
    not_found_seen: set[str] = set()

    def mark_not_found(keyword: str) -> None:
        key = keyword.strip()
        if not key or key in not_found_seen:
            return
        not_found_seen.add(key)
        if not args.dry_run:
            append_line_utf8_bom(not_found_path, key)

    with sync_playwright() as p:
        request_ctx = p.request.new_context(
            base_url=BASE_URL,
            extra_http_headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        )

        debug_dir = (out_dir / "_debug") if args.debug_html and not args.dry_run else None

        try:
            for kw in keywords:
                print(f"\n关键词：{kw}")
                try:
                    play_ids = fetch_play_ids_for_keyword(
                        request_ctx=request_ctx,
                        keyword=kw,
                        use_browser_fallback=args.browser_fallback,
                        debug_dir=debug_dir,
                        playwright=p,
                        user_agent=UA,
                    )
                except Exception as e:
                    print(f"  搜索失败：{e}")
                    if not args.dry_run:
                        append_line_utf8_bom(out_dir / "errors.log", f"keyword={kw} search_error={e}")
                    continue

                if not play_ids:
                    print("  未找到任何 /play/ 结果")
                    mark_not_found(kw)
                    continue

                candidates = play_ids[: args.top]
                pending_share: tuple[PlayInfo, str] | None = None
                downloaded = False

                for idx, play_id in enumerate(candidates, start=1):
                    try:
                        print(f"  [{idx}/{len(candidates)}] play_id={play_id}")
                        play_url = f"{BASE_URL}/play/{play_id}"
                        play_response = request_ctx.get(play_url)
                        if not play_response.ok:
                            raise RuntimeError(f"播放页请求失败：HTTP {play_response.status} ({play_url})")
                        play_html = play_response.text()
                        info = parse_play_info(play_html, play_numeric_id=play_id)

                        preferred_types: list[int] = []
                        if args.prefer_low:
                            preferred_types.append(0)
                        preferred_types.append(info.mp3_type)
                        preferred_types = list(dict.fromkeys(preferred_types))

                        kind, resolved_url = resolve_download_url(
                            request_ctx, info, preferred_types=preferred_types
                        )

                        print(f"    命中：{info.title} - {info.author}")

                        if kind == "extra" and is_share_link(resolved_url):
                            if pending_share is None:
                                pending_share = (info, resolved_url)
                            # 继续检查其余候选，优先选择可直接下载的链接。
                            continue

                        final_url = convert_kuwo_antiserver_url(resolved_url)
                        ext = guess_extension_from_url(final_url, default=".mp3")
                        filename = sanitize_filename(f"{info.title}-{info.author}{ext}")
                        dest = unique_path(out_dir / filename)

                        if args.dry_run:
                            print(f"    直链：{final_url}")
                        else:
                            download_file(final_url, dest)
                            print(f"    保存：{dest}")

                        downloaded = True
                        time.sleep(max(0.0, args.delay))
                        break

                    except Exception as e:
                        err_line = f"keyword={kw} play_id={play_id} error={e}"
                        print(f"    失败：{e}")
                        if not args.dry_run:
                            append_line_utf8_bom(out_dir / "errors.log", err_line)
                        continue

                if not downloaded and pending_share is not None:
                    info, share_url = pending_share
                    filename = sanitize_filename(f"{info.title}-{info.author}.link.txt")
                    dest = unique_path(out_dir / filename)
                    if args.dry_run:
                        print(f"  未找到直链，分享链接：{share_url}")
                    else:
                        dest.write_text(share_url + "\n", encoding="utf-8-sig")
                        print(f"  未找到直链，已保存分享链接：{dest}")

                if not downloaded and pending_share is None:
                    # 所有候选都没有可用资源。
                    mark_not_found(kw)

        finally:
            request_ctx.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
