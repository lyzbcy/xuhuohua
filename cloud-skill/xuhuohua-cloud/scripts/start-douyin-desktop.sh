#!/usr/bin/env bash
set -euo pipefail
for program in Xvfb x11vnc; do
  command -v "$program" >/dev/null || {
    echo "缺少 $program；Debian/Ubuntu 可安装 xvfb x11vnc（建议同时安装 fluxbox）" >&2
    exit 2
  }
done
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$skill/desktop-logs"
chmod 700 "$skill/desktop-logs"
if ! pgrep -f '(^|/)Xvfb :99 ' >/dev/null; then
  nohup Xvfb :99 -screen 0 1280x800x24 -nolisten tcp \
    > "$skill/desktop-logs/xvfb.log" 2>&1 < /dev/null &
  echo $! > "$skill/desktop-logs/xvfb.pid"
  sleep 2
fi
if command -v fluxbox >/dev/null && ! pgrep -f '^fluxbox.*-display :99' >/dev/null; then
  DISPLAY=:99 nohup fluxbox -display :99 \
    > "$skill/desktop-logs/fluxbox.log" 2>&1 < /dev/null &
  echo $! > "$skill/desktop-logs/fluxbox.pid"
fi
if ! pgrep -f '(^|/)x11vnc .* -rfbport 5901' >/dev/null; then
  nohup x11vnc -display :99 -localhost -forever -shared -rfbport 5901 -nopw \
    > "$skill/desktop-logs/x11vnc.log" 2>&1 < /dev/null &
  echo $! > "$skill/desktop-logs/x11vnc.pid"
  sleep 2
fi
if ! pgrep -f '(^|/)x11vnc .* -rfbport 5901' >/dev/null; then
  echo "虚拟桌面启动失败，请检查 desktop-logs/x11vnc.log" >&2; exit 1
fi
echo "虚拟桌面已启动，仅监听服务器本机 5901。请建立 SSH 隧道后连接 VNC。"
