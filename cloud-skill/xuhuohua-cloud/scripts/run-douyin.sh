#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$here/douyin-auto-fire"
export HEADLESS=true TZ=Asia/Shanghai
export XUHUOHUA_SIGNATURE='来自捞鱼自动续火花'
# login-douyin.sh saves here. Never let a stale inherited variable select the
# pre-upgrade login file when the canonical login exists.
if [[ -f "$PWD/storage-state.json" ]]; then
  export DOUYIN_STORAGE_STATE="$PWD/storage-state.json"
elif [[ -f "$here/storage-state.json" ]]; then
  export DOUYIN_STORAGE_STATE="$here/storage-state.json"
  echo '使用旧版登录态路径；下次登录将保存到引擎目录。' >&2
fi
browser_path_file="$here/xuhuohua-cloud/douyin-headless-browser-path"
if [[ ! -f "$browser_path_file" ]]; then
  echo '缺少定时 Headless Shell 配置，请先运行 prepare-douyin.sh。' >&2
  exit 2
fi
export BROWSER_PATH="$(cat "$browser_path_file")"
[[ -x "$BROWSER_PATH" ]] || { echo '定时浏览器不存在，请重新准备环境。' >&2; exit 2; }
exec .venv/bin/python run.py "$@"
