#!/usr/bin/env bash
set -euo pipefail
for program in Xvfb x11vnc websockify; do
  command -v "$program" >/dev/null || {
    echo "缺少 $program；Debian/Ubuntu 可安装 xvfb x11vnc novnc websockify fluxbox" >&2
    exit 2
  }
done
if [[ ! -f /usr/share/novnc/vnc_lite.html ]]; then
  echo "缺少 noVNC 网页文件；Debian/Ubuntu 可安装 novnc" >&2
  exit 2
fi
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
if [[ -f "$skill/desktop-logs/novnc.pid" ]] && kill -0 "$(cat "$skill/desktop-logs/novnc.pid")" 2>/dev/null; then
  :
else
  nohup websockify --web /usr/share/novnc 127.0.0.1:6089 127.0.0.1:5901 \
    > "$skill/desktop-logs/novnc.log" 2>&1 < /dev/null &
  echo $! > "$skill/desktop-logs/novnc.pid"
  sleep 2
fi
if ! kill -0 "$(cat "$skill/desktop-logs/novnc.pid")" 2>/dev/null; then
  echo "noVNC 启动失败，请检查 desktop-logs/novnc.log" >&2; exit 1
fi
if ! python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:6089/vnc_lite.html", timeout=3).close()'; then
  echo "noVNC 页面无法访问，请检查 desktop-logs/novnc.log" >&2; exit 1
fi
echo "noVNC 仅监听服务器本机。建立 ssh -L 6089:127.0.0.1:6089 用户@服务器 后，在浏览器打开 http://127.0.0.1:6089/vnc_lite.html?autoconnect=true"
