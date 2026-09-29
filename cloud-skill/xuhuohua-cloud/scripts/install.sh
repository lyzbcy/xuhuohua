#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^([01]?[0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  echo "用法: bash xuhuohua-cloud/scripts/install.sh HH:MM" >&2
  exit 2
fi
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "当前安装脚本只支持 Linux x86_64" >&2
  exit 2
fi
command -v crontab >/dev/null || { echo "缺少 crontab，请先安装 cron" >&2; exit 2; }
python3 -c 'import sys; assert sys.version_info >= (3, 11), "需要 Python 3.11+"' || exit 2

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
engine="$here/douyin-auto-fire"
if [[ ! -f "$engine/run.py" || ! -f "$engine/requirements.txt" ]]; then
  echo "缺少 douyin-auto-fire 引擎目录" >&2
  exit 2
fi
if [[ ! -f "$engine/config.json" ]]; then
  echo "请先通过私有通道放入好友与话术配置 config.json" >&2
  exit 2
fi
if [[ ! -f "$engine/storage-state.json" && ! -f "$engine/.env" ]]; then
  echo "请先通过私有通道放入登录态 storage-state.json 或 .env" >&2
  exit 2
fi
chmod 600 "$engine/config.json"
[[ ! -f "$engine/storage-state.json" ]] || chmod 600 "$engine/storage-state.json"
[[ ! -f "$engine/.env" ]] || chmod 600 "$engine/.env"

bash "$here/xuhuohua-cloud/scripts/prepare-douyin.sh"

runner="$here/xuhuohua-cloud/run.sh"
cat > "$runner" <<'RUNNER'
#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here/douyin-auto-fire"
export HEADLESS=true
export TZ=Asia/Shanghai
export XUHUOHUA_SIGNATURE='来自捞鱼自动续火花'
browser_path_file="$here/xuhuohua-cloud/douyin-browser-path"
if [[ -f "$browser_path_file" ]]; then export BROWSER_PATH="$(cat "$browser_path_file")"; fi
exec .venv/bin/python run.py
RUNNER
chmod 700 "$runner"
due_runner="$here/xuhuohua-cloud/run-if-due.sh"
cat > "$due_runner" <<'DUE'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$(TZ=Asia/Shanghai date +%H:%M)" != "$1" ]]; then exit 0; fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rm -f "$here/douyin-auto-fire/artifacts/notification-result.json"
set +e
/bin/bash "$here/xuhuohua-cloud/run.sh"
result=$?
set -e
python3 "$here/xuhuohua-cloud/scripts/notify-result.py" douyin --exit-code "$result" || echo "续火花汇总通知失败，请检查企业微信群机器人 webhook" >&2
exit "$result"
DUE
chmod 700 "$due_runner"
mkdir -p "$here/logs"

hour="${1%%:*}"
minute="${1##*:}"
hour="$((10#$hour))"
minute="$((10#$minute))"
schedule="$here/xuhuohua-cloud/douyin-schedule.json"
printf '{"enabled":true,"time":"%02d:%02d"}\n' "$hour" "$minute" > "$schedule"
chmod 600 "$schedule"
tag="# xuhuohua-cloud-daily"
entry="* * * * * /bin/bash '$due_runner' '$(printf '%02d:%02d' "$hour" "$minute")' >> '$here/logs/cron.log' 2>&1 $tag"
existing="$(crontab -l 2>/dev/null || true)"
printf '%s\n' "$existing" | sed '/# xuhuohua-cloud-daily$/d' | { cat; printf '%s\n' "$entry"; } | crontab -
echo "已注册每天 $(printf '%02d:%02d' "$hour" "$minute") (Asia/Shanghai) 的抖音任务；未立即发送。"
