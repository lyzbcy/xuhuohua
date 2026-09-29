#!/usr/bin/env bash
set -euo pipefail
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for name in novnc x11vnc fluxbox xvfb; do
  pid_file="$skill/desktop-logs/$name.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && [[ -r "/proc/$pid/cmdline" ]]; then
      command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
      case "$name" in
        novnc) pattern='*websockify*127.0.0.1:6080*' ;;
        x11vnc) pattern='*x11vnc*-display :99*-rfbport 5901*' ;;
        fluxbox) pattern='*fluxbox*-display :99*' ;;
        xvfb) pattern='*Xvfb :99 *' ;;
      esac
      # PID files may outlive their process; only stop our known command.
      if [[ "$command_line" == $pattern ]]; then
        kill "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
done
echo "已停止本次启动的抖音虚拟桌面进程。"
