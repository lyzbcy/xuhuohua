#!/usr/bin/env bash
set -euo pipefail
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
qr="$skill/qq-data/cache/qrcode.png"
if [[ ! -s "$qr" ]]; then
  echo "尚未生成 QQ 二维码，请确认 NapCat 容器正在等待扫码" >&2
  exit 1
fi
age=$(( $(date +%s) - $(stat -c %Y "$qr") ))
if (( age < 0 || age > 180 )); then
  echo "QQ 二维码已过期，请在 NapCat WebUI 刷新后重试" >&2
  exit 1
fi
if [[ "$(od -An -tx1 -N8 "$qr" | tr -d ' \n')" != "89504e470d0a1a0a" ]]; then
  echo "QQ 二维码不是有效 PNG" >&2
  exit 1
fi
printf '%s\n' "$qr"
