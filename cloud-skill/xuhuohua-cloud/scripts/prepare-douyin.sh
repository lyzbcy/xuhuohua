#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "当前抖音云端安装只支持 Linux x86_64" >&2; exit 2
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"' || exit 2
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="$here/douyin-auto-fire"
skill="$here/xuhuohua-cloud"
if [[ ! -f "$engine/run.py" || ! -f "$engine/requirements.txt" || ! -f "$engine/scripts/login.py" ]]; then
  echo "抖音引擎不完整，请重新下载云端 Release 包" >&2; exit 2
fi
find_browser() {
  find "$engine/.playwright-browsers" "$HOME/.cache/ms-playwright" /home/*/.cache/ms-playwright \
    -type f -path '*/chromium-*/chrome-linux*/chrome' -perm -111 2>/dev/null | sort -V | tail -1 || true
}
browser="$(find_browser)"
if [[ -x "$engine/.venv/bin/python" ]] \
   && "$engine/.venv/bin/python" -c 'import dotenv, playwright, tzdata' >/dev/null 2>&1 \
   && [[ -n "$browser" ]]; then
  printf '%s\n' "$browser" > "$skill/douyin-browser-path"
  chmod 600 "$skill/douyin-browser-path"
  echo "抖音环境已可用，保留现有依赖与 Chromium；尚未注册定时任务。"
  exit 0
fi
python3 -m venv "$engine/.venv"
"$engine/.venv/bin/python" -m pip install -r "$engine/requirements.txt"
PLAYWRIGHT_BROWSERS_PATH="$engine/.playwright-browsers" \
  "$engine/.venv/bin/python" -m playwright install chromium
browser="$(find_browser)"
[[ -n "$browser" ]] || { echo "Chromium 安装后仍找不到可执行文件" >&2; exit 1; }
printf '%s\n' "$browser" > "$skill/douyin-browser-path"
chmod 600 "$skill/douyin-browser-path"
echo "抖音引擎与 Chromium 已准备好；尚未注册定时任务。"
