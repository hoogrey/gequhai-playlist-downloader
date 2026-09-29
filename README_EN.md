# Gequhai CSV Playlist Downloader

[简体中文](README.md) | English

This script reads a playlist CSV exported from a music service, searches `gequhai.com` by song title and artist, and saves available direct audio downloads. When only a Quark cloud-drive share link is available, it saves the link to a `.link.txt` file; it does not download files from the cloud drive. This project does not provide audio content. Make sure you have permission to obtain and process the content before using it. See [Disclaimer and copyright](#disclaimer-and-copyright).

## Features

- Reads common playlist CSV exports and searches for each title and artist without requiring your music-service account or cookies.
- Can fall back to Playwright Chromium when a static search page has no results; waits and retries when the site reports rate limiting.
- One-click launchers install the Python dependencies and browser, then use FFmpeg to actually transcode downloaded `.aac` / `.acc` files to MP3.
- Records failed downloads and missing songs separately. One failed song does not stop the rest of the playlist.

## Requirements

- Python 3.10 or newer.
- Internet access for the first installation, and access to the target site and media links when running the script.
- The one-click launchers install Playwright Chromium and the FFmpeg executable provided by `imageio-ffmpeg`. A separate system FFmpeg installation is not required.

## Quick start

1. Obtain a CSV using a [playlist export tool](#playlist-csv) below. Make sure it has title and artist columns, then place it in the project directory as `playlist.csv`. See [`playlist.example.csv`](playlist.example.csv) for an example.
2. On Windows, double-click [`start.bat`](start.bat). On macOS or Linux, run:

   ```bash
   chmod +x ./start.sh
   ./start.sh
   ```

3. Find downloaded audio, saved share links, and logs in `downloads/`. The first run creates `.venv` and installs dependencies; later runs reuse that environment.

To use a CSV elsewhere, pass its path in a terminal. For example, in Windows PowerShell:

```powershell
.\start.bat --csv "C:\Music\playlist.csv" --out "C:\Music\output"
```

To inspect resolved links without downloading or transcoding files:

```powershell
.\start.bat --dry-run --top 3
```

On macOS or Linux, replace `start.bat` with `./start.sh`; the options are the same. After a successful download run, the launcher scans the selected output directory for `.aac` / `.acc` files and transcodes them. `--dry-run` and `--help` skip conversion.

## Playlist CSV

Choose a third-party export tool for your music service. These tools are independent of this project, and their supported services or CSV formats may change:

| Source | Export tool | Recognized columns |
| --- | --- | --- |
| QQ Music, NetEase Cloud Music, and others | [Playlist Out](https://playlistout.lengxiqwq.com/) ([source](https://github.com/LengxiQwQ/playlistout)) | `歌曲标题`, `歌手` |
| QQ Music, NetEase Cloud Music | [Music Playlist Exporter](https://github.com/xsjason38/Music-Playlist-Exporter) | `歌名`, `歌手` |
| Spotify | [Exportify](https://exportify.app/) ([source](https://github.com/watsonbox/exportify)) | `Track Name`, `Artist Name(s)` |

An unauthenticated public Kugou playlist may show only some tracks in Playlist Out. Follow the export tool's instructions and check the music service's authorization terms. This project only reads an exported CSV; it does not retrieve your playlist from a music service.

A minimal CSV looks like this:

```csv
歌曲标题,歌手
Example Song,Example Artist
```

The file must use UTF-8; a UTF-8 BOM is also supported. The script skips empty rows and rows without a title or artist, but keeps duplicate songs. It removes the specific leading apostrophe that Playlist Out adds to protect spreadsheet software from formula injection. The older `keywords.txt` format is no longer an input.

`.gitignore` excludes `playlist.csv`, other local CSV files, downloads, and run logs. The repository includes only a sample CSV without a personal playlist.

## Manual installation and usage

You can install the dependencies and run the downloader without a one-click launcher. In Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe .\gequhai_downloader.py --csv .\playlist.csv
```

On macOS or Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
./.venv/bin/python ./gequhai_downloader.py --csv ./playlist.csv
```

Running `gequhai_downloader.py` directly **does not transcode audio automatically**. Use a launcher or run the conversion script afterward if you need MP3 files.

Common options:

| Option | Purpose |
| --- | --- |
| `--csv PATH` | Playlist CSV; defaults to `playlist.csv` in the project directory |
| `--out PATH` | Output directory; defaults to `downloads` in the project directory |
| `--top N` | Check at most the first N search results per song; defaults to 1 |
| `--delay SECONDS` | Pause after resolving a direct link; defaults to 1 second |
| `--dry-run` | Print resolved links without writing files |
| `--no-browser-fallback` | Disable the Chromium fallback for searches |
| `--no-prefer-low` | Use the quality type shown by the page instead of trying a lower-quality direct link first |
| `--debug-html` | Save search-page HTML under `_debug/` in the output directory; does not save it in `--dry-run` mode |

Run `gequhai_downloader.py --help` for all options. Default CSV and output paths are relative to the project directory; explicitly provided relative paths are resolved from the current working directory. The one-click launchers first change to the project directory.

## Output and conversion

| File | Meaning |
| --- | --- |
| `downloads/Song-Artist.<extension>` | Downloaded audio; duplicate names receive a number |
| `downloads/Song-Artist.link.txt` | Quark cloud-drive share link when no direct audio link is available |
| `downloads/errors.log` | Search, parsing, or download errors |
| `downloads/not_found.txt` | Search terms with no usable result |

Log and share-link text files use UTF-8 with a BOM for compatibility with Windows tools. `--out` changes the output directory.

The launchers call [`convert_aac_to_mp3.py`](convert_aac_to_mp3.py) to re-encode `.aac` / `.acc` audio as MP3 with FFmpeg. A successful conversion removes the source file; a failed conversion leaves it in place. AAC-to-MP3 conversion is lossy and may reduce audio quality. To run conversion manually:

```powershell
.\.venv\Scripts\python.exe .\convert_aac_to_mp3.py --dir .\downloads
```

Add `--keep-source` to retain the original file, `--recursive` to include subdirectories, or `--ffmpeg PATH` to use your own FFmpeg executable. The old `rename_acc_to_mp3.py` filename remains as a compatibility entry point. It performs actual conversion, not a filename-extension change.

## Known limitations

- Search pages, APIs, and media links are maintained by third parties. Site changes, rate limits, or expired links can cause failures. Try increasing `--delay`, or use `--debug-html` to inspect the page structure.
- The downloader infers file extensions from direct-link URLs; it does not inspect every file's actual codec. Links with missing or incorrect extensions may need manual inspection. Automatic conversion only handles `.aac` / `.acc` files.
- The script does not download cloud-drive files or handle DRM-protected content.

## Tests

After installing the dependencies, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Disclaimer and copyright

This project is provided solely for personal learning and technical experiments, not for commercial services. The repository does not provide, host, or license any songs or other third-party content, and is not affiliated with any music service, download site, or playlist export tool.

Before use, verify that you have the necessary rights to download, store, and convert the relevant content, and comply with applicable law, copyright-holder permissions, and the relevant websites' terms. Do not use this project to obtain content you are not authorized to use, bypass payment or technical protection measures, or sell, upload, publicly share, or otherwise distribute unauthorized audio files or download links.

This project does not guarantee the ownership, licensing status, accuracy, or availability of third-party resources. You are responsible for your own use and the content you process. This notice does not replace permission from a rights holder or guarantee that any particular use is non-infringing. Rights holders who believe the repository affects their rights may contact the maintainer through a repository issue for review.

This repository currently has no code license. The learning and experimental purpose stated above does not grant permission to redistribute the code or use it commercially; contact the maintainer if you need such permission.
