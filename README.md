# 歌曲海歌单 CSV 批量下载脚本

[English](README_EN.md) | 简体中文

读取音乐软件导出的歌单 CSV，按歌名和歌手在 `gequhai.com` 搜索，并保存站点提供的可用音频直链。若只有夸克网盘分享链接，脚本会将链接保存为 `.link.txt` 文件，不会自动下载网盘内容。本项目不提供音频资源；使用前请确认你有权获取和处理相关内容，详见[免责声明与版权](#免责声明与版权)。

## 功能

- 支持常见歌单导出 CSV，按“歌名 + 歌手”逐首搜索，无需向脚本提供音乐平台账号或 Cookie。
- 静态页面没有搜索结果时，可使用 Playwright Chromium 回退；接口限流时会按提示等待并重试。
- 一键启动器自动准备 Python 依赖和浏览器，并在下载后使用 FFmpeg 将 `.aac` / `.acc` 音频真正转码为 MP3。
- 将下载失败和未找到的歌曲分别记录，单首歌曲失败不会中断整份歌单。

## 环境要求

- Python 3.10 或更新版本。
- 首次安装需要网络连接；运行时需能访问目标站点及媒体链接。
- 首次运行一键启动器会安装 Playwright Chromium 和 `imageio-ffmpeg` 提供的 FFmpeg 可执行文件。无需手动配置系统 FFmpeg。

## 快速开始

1. 使用下文的[歌单导出工具](#歌单-csv)取得 CSV，确认有“歌名/歌曲标题”和“歌手”列，将文件放在项目目录并命名为 `playlist.csv`。可参考 [`playlist.example.csv`](playlist.example.csv)。
2. 在 Windows 上双击 [`start.bat`](start.bat)。在 macOS / Linux 上运行：

   ```bash
   chmod +x ./start.sh
   ./start.sh
   ```

3. 完成后在 `downloads/` 查看音频、分享链接或日志。首次启动会创建 `.venv` 并下载依赖，后续启动会复用该环境。

CSV 位于其他位置时，可在终端中传入路径。例如 Windows PowerShell：

```powershell
.\start.bat --csv "C:\Music\playlist.csv" --out "C:\Music\output"
```

只想检查解析结果、不下载或转码文件：

```powershell
.\start.bat --dry-run --top 3
```

macOS / Linux 将上述 `start.bat` 换成 `./start.sh`；参数相同。一键启动器会在下载成功后扫描本次输出目录中的 `.aac` / `.acc` 文件并转码，`--dry-run` 和 `--help` 不会触发转码。

## 歌单 CSV

可按音乐平台选择第三方导出工具；这些工具与本项目无关联，格式和适用范围可能变化：

| 来源 | 导出工具 | 支持的列名 |
| --- | --- | --- |
| QQ 音乐、网易云音乐等 | [Playlist Out](https://playlistout.lengxiqwq.com/)（[源码](https://github.com/LengxiQwQ/playlistout)） | `歌曲标题`、`歌手` |
| QQ 音乐、网易云音乐 | [Music Playlist Exporter](https://github.com/xsjason38/Music-Playlist-Exporter) | `歌名`、`歌手` |
| Spotify | [Exportify](https://exportify.app/)（[源码](https://github.com/watsonbox/exportify)） | `Track Name`、`Artist Name(s)` |

Playlist Out 的酷狗公开歌单未登录时可能只显示部分曲目；请按导出工具自身的说明操作，并核对平台授权条件。本项目只读取导出的 CSV，不负责获取歌单数据。

最简单的 CSV 内容如下：

```csv
歌曲标题,歌手
示例歌曲,示例歌手
```

文件须为 UTF-8，支持 UTF-8 BOM。脚本会跳过空行以及歌名或歌手为空的记录，保留歌单中的重复歌曲；Playlist Out 为防止表格公式注入而添加的特定前导单引号会在搜索前还原。旧版 `keywords.txt` 已不再作为输入。

`playlist.csv`、其他本地 CSV、下载内容和运行日志已由 `.gitignore` 排除；仓库仅提供不含个人歌单的示例文件。

## 手动安装与运行

一键启动器以外，也可以自行安装并直接运行下载脚本。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe .\gequhai_downloader.py --csv .\playlist.csv
```

macOS / Linux：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
./.venv/bin/python ./gequhai_downloader.py --csv ./playlist.csv
```

直接运行 `gequhai_downloader.py` **不会自动转码**；需要 MP3 时请使用一键启动器，或在下载后手动运行转换脚本。

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--csv PATH` | 歌单 CSV；默认是项目目录下的 `playlist.csv` |
| `--out PATH` | 输出目录；默认是项目目录下的 `downloads` |
| `--top N` | 每首歌最多检查前 N 条搜索结果，默认 1 |
| `--delay SECONDS` | 成功解析直链后的间隔，默认 1 秒 |
| `--dry-run` | 显示解析出的链接，不写入文件 |
| `--no-browser-fallback` | 禁用搜索失败时的 Chromium 回退 |
| `--no-prefer-low` | 不优先尝试低品质直链，改用页面标记的音质类型 |
| `--debug-html` | 将搜索页 HTML 保存到输出目录的 `_debug/`；`--dry-run` 时不保存 |

完整参数见 `gequhai_downloader.py --help`。默认 CSV 和输出目录以项目目录为基准；显式传入的相对路径以当前工作目录为基准。一键启动器会先切换到项目目录。

## 输出与转码

| 文件 | 含义 |
| --- | --- |
| `downloads/歌名-歌手.<扩展名>` | 下载的音频；重名时自动添加序号 |
| `downloads/歌名-歌手.link.txt` | 没有可用直链时保存的夸克网盘分享链接 |
| `downloads/errors.log` | 搜索、解析或下载失败记录 |
| `downloads/not_found.txt` | 没有可用结果的搜索词 |

日志和分享链接文件使用带 BOM 的 UTF-8，便于 Windows 工具读取。默认输出目录会随 `--out` 改变。

一键启动器会调用 [`convert_aac_to_mp3.py`](convert_aac_to_mp3.py)，使用 FFmpeg 将 `.aac` / `.acc` 音频重新编码为 MP3；成功后删除源文件，失败时保留源文件。AAC 转 MP3 是有损重编码，音质可能下降。也可以手动运行：

```powershell
.\.venv\Scripts\python.exe .\convert_aac_to_mp3.py --dir .\downloads
```

追加 `--keep-source` 可保留原文件，`--recursive` 可处理子目录，`--ffmpeg PATH` 可指定自己的 FFmpeg。旧文件名 `rename_acc_to_mp3.py` 保留为兼容入口，执行的同样是真正的转码，而非只修改扩展名。

## 已知限制

- 搜索页面、接口和媒体链接由第三方维护，站点改版、限流或链接失效都可能导致失败。可尝试增大 `--delay`，必要时使用 `--debug-html` 排查页面结构。
- 下载文件的扩展名根据直链 URL 推断，脚本不会检测每个文件的真实编码。无扩展名或后缀错误的链接可能需要手动检查，自动转码仅处理 `.aac` / `.acc` 文件。
- 脚本不会自动下载网盘文件，也不处理受 DRM 等技术保护的内容。

## 测试

安装依赖后运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 免责声明与版权

本项目仅供个人学习和技术实验，不用于商业服务。仓库不提供、托管或授权任何歌曲及其他第三方内容，也不代表与音乐平台、下载站点或歌单导出工具存在合作关系。

使用前请自行确认对相关内容拥有合法的下载、保存和格式转换权限，并遵守适用法律、著作权人的授权条件及相关网站的服务条款。请勿使用本项目获取无权使用的内容、规避付费或技术保护措施，亦勿出售、上传、公开分享或以其他方式传播未经授权的音频文件及下载链接。

第三方资源的权属、授权范围、准确性和可用性不由本项目保证。使用者应对自己的使用行为和所处理的内容负责；本说明不能代替权利人的授权，也不能保证任何具体使用行为不构成侵权。如权利人认为仓库内容涉及其合法权益，请通过仓库 Issue 联系维护者核实处理。

本仓库目前没有附带代码许可证。上述学习实验用途说明不授予代码再分发或商业使用许可；如需此类许可，请先联系维护者。
