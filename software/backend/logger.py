# -*- coding: utf-8 -*-
"""软件日志系统（依据 软件组件/日志系统.md）：
1. 开发视角：结构化落盘 logs/日期-software.log
2. 用户视角：事件总线，前端状态栏实时展示"正在干什么"
"""
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional

from backend.paths import LOG_DIR

_lock = threading.Lock()
_events: deque = deque(maxlen=2000)   # (seq, ts, level, message)
_seq = 0


def log(level: str, message: str, source: str = "app") -> int:
    """记录一条事件：落盘 + 进事件总线。返回序号。"""
    global _seq
    with _lock:
        _seq += 1
        seq = _seq
        ts = datetime.now().strftime("%H:%M:%S")
        _events.append((seq, ts, level, message, source))
    line = "[{0}] [{1}] [{2}] {3}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, source, message)
    try:
        logfile = LOG_DIR / ("{0}-software.log".format(datetime.now().strftime("%Y-%m-%d")))
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return seq


def info(msg, source="app"): log("INFO", msg, source)
def ok(msg, source="app"): log("OK", msg, source)
def warn(msg, source="app"): log("WARN", msg, source)
def fail(msg, source="app"): log("FAIL", msg, source)


def get_events(since: int = 0, limit: int = 200):
    """取 since 之后的事件（前端轮询用）。"""
    with _lock:
        items = [e for e in _events if e[0] > since]
    return [dict(seq=e[0], time=e[1], level=e[2], message=e[3], source=e[4])
            for e in items[-limit:]]


def today_log_text(tail: int = 200) -> str:
    logfile = LOG_DIR / ("{0}-software.log".format(datetime.now().strftime("%Y-%m-%d")))
    if not logfile.exists():
        return "今天还没有日志"
    lines = logfile.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-tail:])
