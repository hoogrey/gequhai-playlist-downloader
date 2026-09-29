#!/usr/bin/env bash
set -euo pipefail

# One-click launcher for macOS/Linux. Run from any working directory.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "[1/3] Creating Python virtual environment..."
  command -v python3 >/dev/null 2>&1 || {
    echo "Python 3.10+ was not found. Install it and try again." >&2
    exit 1
  }
  python3 -m venv "$PROJECT_DIR/.venv"
else
  echo "[1/3] Virtual environment is ready."
fi

echo "[2/3] Checking Python dependencies..."
"$PYTHON" -m pip install --disable-pip-version-check -r "$PROJECT_DIR/requirements.txt"

if [[ ! -f "$PROJECT_DIR/.venv/.chromium-ready" ]]; then
  echo "[3/3] Installing Playwright Chromium browser..."
  "$PYTHON" -m playwright install chromium
  touch "$PROJECT_DIR/.venv/.chromium-ready"
else
  echo "[3/3] Playwright Chromium is ready."
fi

if [[ ! -f "$PROJECT_DIR/playlist.csv" && $# -eq 0 ]]; then
  echo "No playlist.csv was found in the project folder." >&2
  echo "Export a playlist CSV, save it as playlist.csv, and run this script again." >&2
  exit 2
fi

SKIP_CONVERSION=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|--help|-h) SKIP_CONVERSION=1 ;;
  esac
done

set +e
"$PYTHON" "$PROJECT_DIR/gequhai_downloader.py" "$@"
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 && $SKIP_CONVERSION -eq 0 ]]; then
  echo "Converting downloaded .acc/.aac files to MP3 with FFmpeg..."
  if ! "$PYTHON" "$PROJECT_DIR/convert_aac_to_mp3.py" --dir "$PROJECT_DIR/downloads" --download-args "$@"; then
    [[ $EXIT_CODE -eq 0 ]] && EXIT_CODE=1
  fi
else
  echo "Skipping audio conversion for dry-run/help or failed download."
fi

exit "$EXIT_CODE"
