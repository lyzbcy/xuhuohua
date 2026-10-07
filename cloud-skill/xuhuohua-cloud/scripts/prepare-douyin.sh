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
if [[ ! -x "$engine/.venv/bin/python" ]] || ! "$engine/.venv/bin/python" -c 'import dotenv, playwright, tzdata' >/dev/null 2>&1; then
  python3 -m venv "$engine/.venv"
  "$engine/.venv/bin/python" -m pip install -r "$engine/requirements.txt"
fi
# Select the revision required by THIS venv, not another installation's newest.
# Login uses full Chromium; cron uses the verified Headless Shell variant.
revision="$("$engine/.venv/bin/python" -c 'from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(Path(p.chromium.executable_path).parents[1].name.removeprefix("chromium-")); p.stop()')"
[[ "$revision" =~ ^[0-9]+$ ]] || { echo "Playwright 浏览器版本解析失败" >&2; exit 1; }
find_browser() {
  find "$engine/.playwright-browsers" "$HOME/.cache/ms-playwright" /home/*/.cache/ms-playwright \
    -type f -path "*/chromium-$revision/chrome-linux*/chrome" -perm -111 2>/dev/null | head -1 || true
}
find_headless() {
  find "$engine/.playwright-browsers" "$HOME/.cache/ms-playwright" /home/*/.cache/ms-playwright \
    -type f -path "*/chromium_headless_shell-$revision/*" \( -name chrome-headless-shell -o -name headless_shell \) -perm -111 2>/dev/null | head -1 || true
}
browser="$(find_browser)"
headless="$(find_headless)"
if [[ -z "$browser" || -z "$headless" ]]; then
  PLAYWRIGHT_BROWSERS_PATH="$engine/.playwright-browsers" "$engine/.venv/bin/python" -m playwright install chromium
  browser="$(find_browser)"
  headless="$(find_headless)"
fi
[[ -n "$browser" && -n "$headless" ]] || { echo "匹配的 Chromium/Headless Shell 不完整" >&2; exit 1; }
printf '%s\n' "$browser" > "$skill/douyin-browser-path"
printf '%s\n' "$headless" > "$skill/douyin-headless-browser-path"
chmod 600 "$skill/douyin-browser-path" "$skill/douyin-headless-browser-path"
echo "抖音登录 Chromium 与定时 Headless Shell 已匹配 Playwright；尚未注册定时任务。"
