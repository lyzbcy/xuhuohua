"""Persist a verified session without replacing newer manual login state."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


class SessionSaveError(RuntimeError):
    pass


def state_file(source: str | None) -> Path | None:
    # Inline JSON and cookie-only users have no authorized writable state file.
    if not source or source.lstrip().startswith(('{', '[')):
        return None
    return Path(source).expanduser().resolve()


def revision(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None


def validate_state(state: Any) -> None:
    if not isinstance(state, dict) or not isinstance(state.get('cookies'), list):
        raise SessionSaveError('登录态结构无效，原文件已保留')
    if not isinstance(state.get('origins', []), list):
        raise SessionSaveError('登录态结构无效，原文件已保留')
    if not any(isinstance(c, dict) and c.get('name') == 'sessionid'
               and c.get('value') and c.get('domain', '').lstrip('.') in ('douyin.com', 'www.douyin.com')
               and (c.get('expires', -1) == -1 or c.get('expires', 0) > time.time())
               for c in state['cookies']):
        raise SessionSaveError('缺少有效会话 Cookie，原登录态已保留')


def atomic_private_write(path: Path, data: bytes, owner=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.chmod(tmp, 0o600)
            if owner and hasattr(os, 'chown'):
                os.chown(tmp, owner.st_uid, owner.st_gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


async def save_verified_state(context, path: Path | None, expected: str | None) -> str | None:
    """Caller must verify the private-message page, under the shared run lock."""
    if path is None:
        return None
    try:
        state = await context.storage_state()
        validate_state(state)
        data = json.dumps(state, ensure_ascii=False).encode('utf-8')
        if revision(path) != expected:
            raise SessionSaveError('登录态已被其他进程更新，停止覆盖；请重新验证')
        owner = path.stat() if path.exists() else None
        if owner:
            atomic_private_write(path.with_name(path.name + '.last-good'), path.read_bytes(), owner)
        atomic_private_write(path, data, owner)
        return hashlib.sha256(data).hexdigest()
    except SessionSaveError:
        raise
    except Exception:
        # Do not include state, browser exceptions or secret-bearing paths in logs.
        raise SessionSaveError('保存会话更新失败，原登录态已保留；请检查权限和磁盘') from None
