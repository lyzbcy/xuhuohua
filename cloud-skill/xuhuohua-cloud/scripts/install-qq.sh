#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "QQ 云端安装目前只支持 Linux x86_64" >&2; exit 2
fi
for command_name in docker python3 crontab; do
  command -v "$command_name" >/dev/null || { echo "缺少 $command_name" >&2; exit 2; }
done
docker compose version >/dev/null || { echo "需要 Docker Compose v2" >&2; exit 2; }
docker info >/dev/null || { echo "当前用户无法访问 Docker；请配置 Docker 权限" >&2; exit 2; }

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
skill="$here/xuhuohua-cloud"
config="$skill/qq-data/config"
plugin_id=napcat-plugin-auto-tasks
target="$skill/qq-data/plugins/$plugin_id"
if [[ ! -f "$skill/scripts/compose.qq.yaml" ]]; then
  echo "缺少 QQ Docker Compose 文件" >&2; exit 2
fi
mkdir -p "$config/plugins/$plugin_id" "$skill/qq-data/plugins" "$skill/qq-data/QQ" "$skill/qq-data/cache" "$here/logs"
chmod 700 "$skill/qq-data" "$config" "$skill/qq-data/QQ" "$skill/qq-data/cache"
if [[ -d "$target" ]]; then
  mv "$target" "$skill/qq-data/retired-plugin-$(date +%s)-$$"
fi

# 仅给新安装写入关闭状态。用户通过私有通道导入已有配置时不覆盖。
python3 - "$config/plugins.json" "$config/plugins/$plugin_id/config.json" "$plugin_id" <<'PY'
import json, os, pathlib, sys
enabled_path, settings_path = map(pathlib.Path, sys.argv[1:3])
plugin_id = sys.argv[3]
if enabled_path.exists():
    enabled = json.loads(enabled_path.read_text(encoding="utf-8"))
    if not isinstance(enabled, dict):
        raise SystemExit("plugins.json 必须是 JSON 对象")
else:
    enabled = {}
enabled[plugin_id] = False
enabled_path.write_text(json.dumps(enabled, ensure_ascii=False, indent=2), encoding="utf-8")
os.chmod(enabled_path, 0o600)
if settings_path.exists():
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise SystemExit("QQ 插件 config.json 必须是 JSON 对象")
else:
    settings = {"enabled": True, "friendSpark_enable": False,
                "friendSpark_time": "10:00:00", "friendSpark_targets": "",
                "friendSpark_message": "✨"}
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
os.chmod(settings_path, 0o600)
PY

if [[ ! -f "$skill/.env" ]]; then
  printf 'NAPCAT_UID=%s\nNAPCAT_GID=%s\n' "$(id -u)" "$(id -g)" > "$skill/.env"
  chmod 600 "$skill/.env"
fi
python3 - "$skill/.env" <<'PY'
import json, pathlib, re, secrets, subprocess, sys
path = pathlib.Path(sys.argv[1])
content = path.read_text(encoding="utf-8")
keys = {line.split("=", 1)[0] for line in content.splitlines() if "=" in line}
try:
    existing = json.loads(subprocess.check_output(
        ["docker", "inspect", "xuhuohua-napcat"], stderr=subprocess.DEVNULL))[0]
except (OSError, subprocess.CalledProcessError, ValueError):
    existing = None
networks = list(existing["NetworkSettings"]["Networks"].values()) if existing else []
mac = networks[0].get("MacAddress", "") if len(networks) == 1 else ""
host = existing["Config"].get("Hostname", "") if existing else ""
if not re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac, re.I):
    mac = "02:" + ":".join(secrets.token_hex(1) for _ in range(5))
if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{0,62}", host):
    host = "xuhuohua-napcat"
with path.open("a", encoding="utf-8") as out:
    if content and not content.endswith("\n"):
        out.write("\n")
    if "NAPCAT_MAC_ADDRESS" not in keys:
        out.write(f"NAPCAT_MAC_ADDRESS={mac}\n")
    if "NAPCAT_HOSTNAME" not in keys:
        out.write(f"NAPCAT_HOSTNAME={host}\n")
path.chmod(0o600)
PY
docker compose -f "$skill/scripts/compose.qq.yaml" --project-directory "$skill" up -d

# 删除旧版常驻拉起规则。QQ 从本版起只在任务时间内登录。
existing="$(crontab -l 2>/dev/null || true)"
printf '%s\n' "$existing" | sed '/# xuhuohua-cloud-qq-watchdog$/d' | crontab -
notify_tag="# xuhuohua-cloud-qq-result"
notify_entry="* * * * * $(command -v python3) '$skill/scripts/notify-result.py' qq >> '$here/logs/qq-result.log' 2>&1 $notify_tag"
existing="$(crontab -l 2>/dev/null || true)"
printf '%s\n' "$existing" | sed '/# xuhuohua-cloud-qq-result$/d' | { cat; printf '%s\n' "$notify_entry"; } | crontab -
run_tag="# xuhuohua-cloud-qq-send"
run_entry="* * * * * $(command -v python3) '$skill/scripts/qq-run.py' >> '$here/logs/qq-run.log' 2>&1 $run_tag"
existing="$(crontab -l 2>/dev/null || true)"
printf '%s\n' "$existing" | sed '/# xuhuohua-cloud-qq-send$/d' | { cat; printf '%s\n' "$run_entry"; } | crontab -
echo "NapCat 已启动供首次扫码；完成登录验收后应停止容器。"
echo "cron 每分钟核对 QQ 设定时间：到点启动容器、自动快登、发送并退出。"
echo "WebUI 仅监听服务器 127.0.0.1:6099；请通过 SSH 隧道访问并扫码。"
echo "扫码后运行 configure-onebot.py 并重启容器，执行 verify-qq.sh，再用 qq-run.py --session-check 验收自动收摊。"
