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
browser_path_file="$here/xuhuohua-cloud/douyin-browser-path"
if [[ -f "$browser_path_file" ]]; then export BROWSER_PATH="$(cat "$browser_path_file")"; fi
cd "$engine"
"$engine/.venv/bin/python" scripts/login.py
chmod 600 storage-state.json
# login.py has closed the visible browser. This independently restores the saved
# file with the same Headless Shell and user as cron, without sending messages.
bash "$here/xuhuohua-cloud/scripts/run-douyin.sh" --dry-run
echo "登录态已保存且定时入口独立演练通过；没有发送消息。"
