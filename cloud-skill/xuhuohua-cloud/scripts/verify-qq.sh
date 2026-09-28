#!/usr/bin/env bash
set -euo pipefail
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="$skill/qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
python3 - "$config" <<'PY'
import json, pathlib, re, sys
p = pathlib.Path(sys.argv[1])
cfg = json.loads(p.read_text(encoding="utf-8"))
if not cfg.get("enabled") or not cfg.get("friendSpark_enable"):
    raise SystemExit("QQ 好友续火花尚未启用；请先通过私有通道配置")
targets = [x.strip() for x in str(cfg.get("friendSpark_targets", "")).split(",") if x.strip()]
if not targets or not all(x.isdigit() for x in targets):
    raise SystemExit("QQ 好友目标为空或格式错误")
if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", str(cfg.get("friendSpark_time", ""))):
    raise SystemExit("QQ 时间必须是 HH:MM:SS")
print(f"QQ 配置有效：{len(targets)} 位好友，每日北京时间 {cfg['friendSpark_time']}；未发送消息")
PY
if [[ "$(docker inspect -f '{{.State.Running}}' xuhuohua-napcat 2>/dev/null || true)" != "true" ]]; then
  echo "NapCat 容器未运行" >&2; exit 1
fi
echo "请在 NapCat WebUI 核对 QQ 已登录、插件已加载；此检查不会发消息。"
