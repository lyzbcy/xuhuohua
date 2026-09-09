# -*- coding: utf-8 -*-
"""每日定时任务管理（Windows schtasks / Mac 提示用 crontab）。"""
import re
import subprocess

from backend import logger
from backend.paths import SOFTWARE_DIR
from backend.winproc import run_cmd

TASK_NAME = "续火花-抖音"
ROTATE_TASK_NAME = "续火花-QQ话术轮换"


def ensure_rotation() -> dict:
    """每日 00:05 轮换 QQ 话术（从共享池随机）。幂等：重复注册无害。"""
    py = SOFTWARE_DIR / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        return {"ok": False, "msg": "software/.venv 缺失"}
    script = SOFTWARE_DIR / "backend" / "rotate_qq_message.py"
    tr = '"{0}" "{1}"'.format(py, script)
    r = _run_schtasks("/Create", "/TN", ROTATE_TASK_NAME, "/TR", tr,
                      "/SC", "DAILY", "/ST", "00:05", "/F")
    ok = r.returncode == 0
    (logger.ok if ok else logger.warn)("[定时] QQ 话术每日轮换任务: " + ("已就绪（每天 00:05 换一条）" if ok else "注册失败"), source="sched")
    return {"ok": ok}


def rotation_status() -> dict:
    r = _run_schtasks("/Query", "/TN", ROTATE_TASK_NAME, "/V", "/FO", "LIST")
    return {"exists": r.returncode == 0}


def _run_schtasks(*args) -> subprocess.CompletedProcess:
    return run_cmd(["schtasks"] + list(args), timeout=20)


def register(time_str: str = "08:30") -> dict:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(time_str).strip())
    if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
        return {"ok": False, "msg": "时间格式应为 HH:MM（0-23 小时，0-59 分）"}
    time_str = "{0:02d}:{1:02d}".format(int(m.group(1)), int(m.group(2)))
    ps1 = SOFTWARE_DIR / "backend" / "daily_douyin.ps1"
    tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"'.format(ps1)
    r = _run_schtasks("/Create", "/TN", TASK_NAME, "/TR", tr, "/SC", "DAILY", "/ST", time_str, "/F")
    if r.returncode == 0:
        logger.ok("[定时] 已注册每日 {0} 自动续抖音火花".format(time_str), source="sched")
        return {"ok": True, "msg": "已注册每日 {0} 运行".format(time_str)}
    logger.fail("[定时] 注册失败: " + r.stdout + r.stderr, source="sched")
    return {"ok": False, "msg": "注册失败: " + (r.stderr or r.stdout).strip()}


def remove() -> dict:
    r = _run_schtasks("/Delete", "/TN", TASK_NAME, "/F")
    ok = r.returncode == 0
    (logger.ok if ok else logger.warn)("[定时] 删除计划任务: " + ("成功" if ok else "失败/不存在"), source="sched")
    return {"ok": ok, "msg": "已删除" if ok else "删除失败（可能不存在）"}


def status() -> dict:
    r = _run_schtasks("/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST")
    if r.returncode != 0:
        return {"exists": False}
    text = r.stdout
    def field(name):
        m = re.search(name + r":\s+(.+)", text)
        return m.group(1).strip() if m else ""
    return {
        "exists": True,
        "next_run": field("下次运行时间"),
        "last_result": field("上次结果"),
        "status": field("计划任务状态") or field("状态"),
        "task_to_run": field("要运行的任务"),
    }
