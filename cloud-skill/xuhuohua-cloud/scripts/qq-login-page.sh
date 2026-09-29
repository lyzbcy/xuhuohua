#!/usr/bin/env bash
set -euo pipefail
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pid_file="$skill/qq-login-page.pid"
script="$skill/scripts/qq-login-page.py"
if [[ "${1:-start}" == stop ]]; then
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && [[ -r "/proc/$pid/cmdline" ]] &&
       tr '\0' ' ' < "/proc/$pid/cmdline" | grep -Fq "$script"; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
  echo "QQ 登录页面已关闭"
  exit 0
fi
if [[ "${1:-start}" != start ]]; then echo "用法: $0 [start|stop]" >&2; exit 2; fi
if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null &&
   [[ -r "/proc/$(cat "$pid_file")/cmdline" ]] &&
   tr '\0' ' ' < "/proc/$(cat "$pid_file")/cmdline" | grep -Fq "$script"; then
  :
else
  umask 077
  nohup python3 "$script" > "$skill/qq-login-page.log" 2>&1 < /dev/null &
  echo $! > "$pid_file"
  sleep 1
fi
if ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
  echo "QQ 登录页面启动失败，请检查私有日志 qq-login-page.log" >&2; exit 1
fi
echo "建立 ssh -L 6100:127.0.0.1:6100 用户@服务器，然后用浏览器打开 http://127.0.0.1:6100/ 。二维码自动更新；登录确认后运行 $0 stop。"
