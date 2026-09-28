#!/usr/bin/env bash
# Called at the first Skill use of each Beijing day. Never delays the task.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$script_dir/release-path.txt" ]]; then
  skill_dir="$script_dir"
  updater="$script_dir/update-skill.py"
else
  skill_dir="$(cd "$script_dir/.." && pwd)"
  updater="$script_dir/update-skill.py"
fi
today="$(TZ=Asia/Shanghai date +%F)"
if [[ -f "$skill_dir/.last-update-check" ]] &&
   [[ "$(cat "$skill_dir/.last-update-check" 2>/dev/null)" == "$today" ]]; then
  exit 0
fi
command -v python3 >/dev/null 2>&1 || exit 0
nohup python3 "$updater" "$skill_dir" \
  >> "$skill_dir/.update.log" 2>&1 < /dev/null &
exit 0
