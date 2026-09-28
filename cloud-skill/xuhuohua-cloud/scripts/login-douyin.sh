#!/usr/bin/env bash
set -euo pipefail
umask 077
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="$here/douyin-auto-fire"
if [[ ! -x "$engine/.venv/bin/python" ]]; then
  echo "请先运行 prepare-douyin.sh" >&2; exit 2
fi
if ! pgrep -f '(^|/)Xvfb :99 ' >/dev/null; then
  echo "请先运行 start-douyin-desktop.sh" >&2; exit 2
fi
export DISPLAY=:99
cd "$engine"
"$engine/.venv/bin/python" scripts/login.py
chmod 600 storage-state.json
echo "抖音登录态已保存；请先做 dry-run，再注册每日任务。"
