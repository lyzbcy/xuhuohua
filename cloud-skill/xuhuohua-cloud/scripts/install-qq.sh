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
plugin="$here/qq-plugin"
config="$skill/qq-data/config"
plugin_id=napcat-plugin-auto-tasks
target="$skill/qq-data/plugins/$plugin_id"
if [[ ! -f "$plugin/index.mjs" || ! -f "$plugin/package.json" || ! -f "$plugin/LICENSE" || ! -f "$plugin/webui/index.html" ]]; then
  echo "QQ 插件产物不完整，请重新导出云端包" >&2; exit 2
fi
if [[ ! -f "$skill/scripts/compose.qq.yaml" ]]; then
  echo "缺少 QQ Docker Compose 文件" >&2; exit 2
fi
mkdir -p "$config/plugins/$plugin_id" "$target/webui" "$skill/qq-data/QQ" "$skill/qq-data/cache" "$here/logs"
chmod 700 "$skill/qq-data" "$config" "$skill/qq-data/QQ" "$skill/qq-data/cache"
cp "$plugin/index.mjs" "$plugin/package.json" "$plugin/LICENSE" "$target/"
cp "$plugin/webui/index.html" "$target/webui/"

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
enabled[plugin_id] = True
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
docker compose -f "$skill/scripts/compose.qq.yaml" --project-directory "$skill" up -d

watchdog="$skill/scripts/qq-watchdog.sh"
tag="# xuhuohua-cloud-qq-watchdog"
entry="*/5 * * * * /bin/bash '$watchdog' >> '$here/logs/qq-watchdog.log' 2>&1 $tag"
existing="$(crontab -l 2>/dev/null || true)"
printf '%s\n' "$existing" | sed '/# xuhuohua-cloud-qq-watchdog$/d' | { cat; printf '%s\n' "$entry"; } | crontab -
echo "NapCat 已启动，QQ 插件已部署；cron 每 5 分钟检查容器，不触发发送。"
echo "WebUI 仅监听服务器 127.0.0.1:6099；请通过 SSH 隧道访问并扫码。"
echo "确认好友配置和登录后，执行 bash xuhuohua-cloud/scripts/verify-qq.sh。"
