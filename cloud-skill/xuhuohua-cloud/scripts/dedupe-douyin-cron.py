"""Remove only this release's Douyin cron entries, preserving QQ and other jobs."""
import os
import shlex
import subprocess
import sys
from pathlib import Path


def remove_entries(text: str, root: Path) -> str:
    legacy = root.as_posix().rstrip('/') + '/douyin-auto-fire/run-cron.sh'
    due = root.as_posix().rstrip('/') + '/xuhuohua-cloud/run-if-due.sh'
    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith('#'):
            lines.append(line)
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            lines.append(line)
            continue
        command = tokens[5:]
        direct = bool(command) and command[0] in {legacy, due}
        shell = (len(command) > 1 and Path(command[0]).name in {'bash', 'sh'}
                 and command[1] in {legacy, due})
        if direct or shell:
            continue
        lines.append(line)
    return ''.join(lines)


def main():
    import pwd
    root = Path(sys.argv[1]).resolve()
    current = pwd.getpwuid(os.getuid()).pw_name
    users = {current}
    if os.geteuid() == 0:
        users.update(p.pw_name for p in pwd.getpwall())
    for user in sorted(users):
        command = ['crontab', '-u', user] if os.geteuid() == 0 else ['crontab']
        result = subprocess.run(command + ['-l'], capture_output=True, text=True)
        if result.returncode:
            continue
        cleaned = remove_entries(result.stdout, root)
        if cleaned != result.stdout:
            subprocess.run(command + ['-'], input=cleaned, text=True, check=True)
            print(f'已清除 {user} 的本目录旧抖音入口；QQ 与其他任务保持不变。')


if __name__ == '__main__':
    main()
