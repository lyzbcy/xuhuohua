#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || -z "$1" ]]; then
  echo "用法: bash xuhuohua-cloud/scripts/install-skill.sh <Agent 的 skills 目录>" >&2
  exit 2
fi
source_skill="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
release_root="$(cd "$source_skill/.." && pwd)"
target="$1/xuhuohua-cloud"
mkdir -p "$target"
if [[ "$(realpath "$source_skill")" != "$(realpath "$target")" ]]; then
  cp "$source_skill/SKILL.md" "$target/SKILL.md"
fi
version_file="$source_skill/VERSION"
if [[ ! -f "$version_file" ]]; then
  release_root="$(cd "$source_skill/../.." && pwd)"
  version_file="$release_root/VERSION"
fi
cp "$version_file" "$target/VERSION"
cp "$source_skill/scripts/check-update.sh" "$target/check-update.sh"
cp "$source_skill/scripts/update-skill.py" "$target/update-skill.py"
chmod 755 "$target/check-update.sh"
printf '%s\n' "$release_root" > "$target/release-path.txt"
echo "Skill 已安装到 $target；执行程序保留在 $release_root。按 Agent 的机制重新加载 Skill 后生效。"
