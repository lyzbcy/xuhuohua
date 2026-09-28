"""Silently refresh Skill instructions/scripts from the latest verified Release.

Existing login state, QQ data, user settings and cron schedules are untouched.
Runtime engines and QQ plugin upgrades remain a separate maintenance action.
"""

import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

try:
    import fcntl
except ImportError:  # Windows CI tests use a stub; deployed updater is Linux-only.
    fcntl = None

API = "https://api.github.com/repos/lyzbcy/xuhuohua/releases/latest"
BEIJING = timezone(timedelta(hours=8))
MAX_ZIP = 15_000_000
PREFIX = "xuhuohua-cloud/"


def fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "xuhuohua-cloud-updater"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release 资产超过大小限制")
    return data


def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".new-{os.getpid()}")
    try:
        temp.write_bytes(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def update(skill_dir: Path) -> str:
    if fcntl is None:
        raise RuntimeError("Skill 静默更新仅支持 Linux")
    skill_dir = skill_dir.resolve()
    with (skill_dir / ".update.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "already-running"
        today = datetime.now(BEIJING).strftime("%Y-%m-%d")
        stamp = skill_dir / ".last-update-check"
        if stamp.is_file() and stamp.read_text(encoding="ascii").strip() == today:
            return "already-checked"
        root = Path((skill_dir / "release-path.txt").read_text(encoding="utf-8").strip()).resolve()
        runtime_skill = root / "xuhuohua-cloud"
        if not runtime_skill.is_dir() or not (skill_dir / "VERSION").is_file():
            raise ValueError("Skill 安装目录不完整")
        current = (skill_dir / "VERSION").read_text(encoding="ascii").strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", current):
            raise ValueError("本地 Skill 版本无效")
        release = json.loads(fetch(API, 200_000))
        tag = release.get("tag_name", "")
        if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            raise ValueError("最新 Release 版本无效")
        remote = tag.removeprefix("v")
        if tuple(map(int, remote.split("."))) <= tuple(map(int, current.split("."))):
            atomic_write(stamp, (today + "\n").encode("ascii"), 0o600)
            return "current"
        assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
        package = fetch(assets["xuhuohua-cloud.zip"], MAX_ZIP)
        checksum = fetch(assets["xuhuohua-cloud.zip.sha256"], 200)
        checksum_parts = checksum.decode("ascii").split()
        expected = checksum_parts[0] if checksum_parts else ""
        if (len(checksum_parts) != 2 or checksum_parts[1] != "xuhuohua-cloud.zip"
                or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or hashlib.sha256(package).hexdigest() != expected):
            raise ValueError("云端包 SHA-256 校验失败")
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            if archive.testzip() is not None:
                raise ValueError("云端包 CRC 校验失败")
            names = archive.namelist()
            required = {PREFIX + "VERSION", PREFIX + "SKILL.md",
                        PREFIX + "scripts/check-update.sh", PREFIX + "scripts/update-skill.py"}
            if not required.issubset(names):
                raise ValueError("云端包缺少自动更新组件")
            if archive.read(PREFIX + "VERSION").decode("ascii").strip() != remote:
                raise ValueError("云端包版本与 Release 标签不符")
            files = {}
            for name in names:
                relative = PurePosixPath(name)
                if (not name.startswith(PREFIX) or name.endswith("/")
                        or ".." in relative.parts):
                    continue
                child = relative.relative_to(PurePosixPath("xuhuohua-cloud"))
                if child.as_posix() in {"SKILL.md", "VERSION"} or (
                        len(child.parts) == 2 and child.parts[0] == "scripts"
                        and child.suffix in {".sh", ".py", ".yaml"}):
                    files[child] = archive.read(name)
        # Update the stable release directory first. Cron paths remain valid.
        for child, data in files.items():
            if child.parts[0] == "scripts":
                atomic_write(runtime_skill / child, data, 0o755 if child.suffix == ".sh" else 0o644)
        atomic_write(runtime_skill / "SKILL.md", files[PurePosixPath("SKILL.md")])
        atomic_write(runtime_skill / "VERSION", files[PurePosixPath("VERSION")])
        # Keep the installed Agent Skill in sync; version is committed last.
        for name in ("check-update.sh", "update-skill.py"):
            child = PurePosixPath("scripts") / name
            atomic_write(skill_dir / name, files[child], 0o755 if name.endswith(".sh") else 0o644)
        atomic_write(skill_dir / "SKILL.md", files[PurePosixPath("SKILL.md")])
        atomic_write(skill_dir / "VERSION", files[PurePosixPath("VERSION")])
        atomic_write(stamp, (today + "\n").encode("ascii"), 0o600)
        return "updated"


if __name__ == "__main__":
    try:
        outcome = update(Path(sys.argv[1]))
        print(f"Skill 更新检查：{outcome}")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"Skill 更新失败，继续使用原版本：{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
