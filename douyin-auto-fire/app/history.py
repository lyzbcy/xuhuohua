from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AlreadyRunningError(RuntimeError):
    pass


class History:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._load()

    def run_date(self, timezone: str) -> str:
        try:
            return datetime.now(ZoneInfo(timezone)).date().isoformat()
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"未知时区: {timezone}，请安装 tzdata 或修正配置") from exc

    def key(self, task_id: str, run_date: str, target: str, message_id: str) -> str:
        return f"{task_id}:{run_date}:{target}:{message_id}"

    def contains(self, key: str) -> bool:
        return key in self.entries

    def reserve(self, key: str) -> None:
        self.entries[key] = {"status": "unknown", "started_at": datetime.now().astimezone().isoformat()}
        self._save()

    def mark_success(self, key: str) -> None:
        self.entries[key] = {"status": "success", "finished_at": datetime.now().astimezone().isoformat()}
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"发送历史损坏，为避免重复发送，任务已停止: {self.path}") from exc


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AlreadyRunningError(f"已有任务正在运行；如确认没有进程，请删除 {path}") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
