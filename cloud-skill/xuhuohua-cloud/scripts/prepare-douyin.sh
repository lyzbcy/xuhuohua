#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "当前抖音云端安装只支持 Linux x86_64" >&2; exit 2
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"' || exit 2
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="$here/douyin-auto-fire"
if [[ ! -f "$engine/run.py" || ! -f "$engine/requirements.txt" || ! -f "$engine/scripts/login.py" ]]; then
  echo "抖音引擎不完整，请重新下载云端 Release 包" >&2; exit 2
fi
python3 -m venv "$engine/.venv"
"$engine/.venv/bin/python" -m pip install -r "$engine/requirements.txt"
"$engine/.venv/bin/python" -m playwright install chromium
echo "抖音引擎与 Chromium 已准备好；尚未注册定时任务。"
