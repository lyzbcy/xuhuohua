#!/usr/bin/env bash
set -euo pipefail
skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(docker inspect -f '{{.State.Running}}' xuhuohua-napcat 2>/dev/null || true)" == "true" ]]; then
  exit 0
fi
echo "$(date -Is) NapCat 未运行，正在拉起容器"
docker compose -f "$skill/scripts/compose.qq.yaml" --project-directory "$skill" up -d
