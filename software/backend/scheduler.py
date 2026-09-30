# -*- coding: utf-8 -*-
"""Windows 每日定时任务；源码与便携包都指向各自可执行的入口。"""
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

from backend import logger
from backend.paths import BACKEND_SCRIPT_DIR, FROZEN, PROJECT_ROOT, SOFTWARE_DIR
from backend.winproc import run_cmd

TASK_NAME = "续火花-抖音"
ROTATE_TASK_NAME = "续火花-QQ话术轮换"
QQ_START_TASK_NAME = "续火花-QQ启动"
WATCHDOG_TASK_NAME = "续火花-任务自检"
SCHEDULE_FILE = PROJECT_ROOT / "config" / "schedule.json"
TASKS = {
    TASK_NAME: "抖音每日续火花",
    QQ_START_TASK_NAME: "QQ 自动启动与续火花",
    ROTATE_TASK_NAME: "QQ 每日话术轮换",
    WATCHDOG_TASK_NAME: "定时任务自检",
}


def _preferences() -> dict:
    try:
        value = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _disabled(name: str) -> bool:
    return name in _preferences().get("disabled_tasks", [])


def _set_disabled(name: str, disabled: bool) -> None:
    value = _preferences()
    names = set(value.get("disabled_tasks", []))
    names.add(name) if disabled else names.discard(name)
    value["disabled_tasks"] = sorted(names)
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def registered_tasks() -> dict:
    """只展示本软件的已注册任务，不读取或允许删除其他应用的任务。"""
    items = []
    for name, title in TASKS.items():
        info = _task_info(name)
        if info["exists"]:
            items.append({"name": name, "title": title, **info})
    return {"tasks": items, "disabled": [{"name": name, "title": TASKS[name]}
             for name in _preferences().get("disabled_tasks", []) if name in TASKS]}


def remove_tasks(names) -> dict:
    if not isinstance(names, list) or not names or any(name not in TASKS for name in names):
        return {"ok": False, "msg": "请选择本软件已注册的定时任务"}
    results = []
    for name in dict.fromkeys(names):
        was_disabled = _disabled(name)
        _set_disabled(name, True)
        result = _run_schtasks("/Delete", "/TN", name, "/F")
        ok = result.returncode == 0
        if not ok:
            _set_disabled(name, was_disabled)
        results.append({"name": name, "ok": ok})
        (logger.ok if ok else logger.warn)("[定时] 删除 {0}: {1}".format(
            name, "成功（不会自动恢复）" if ok else "失败，请检查系统权限"), source="sched")
    return {"ok": all(item["ok"] for item in results), "results": results,
            "msg": "已删除所选任务，不会自动恢复" if all(item["ok"] for item in results)
            else "部分任务删除失败，请查看日志"}


def _app_command(argument: str) -> str:
    if FROZEN:
        return '"{0}" {1}'.format(sys.executable, argument)
    py = SOFTWARE_DIR / ".venv" / "Scripts" / "python.exe"
    return '"{0}" "{1}" {2}'.format(py, SOFTWARE_DIR / "main.py", argument)


def ensure_rotation() -> dict:
    """每日 00:05 轮换 QQ 话术（从共享池随机）。幂等：重复注册无害。"""
    if _disabled(ROTATE_TASK_NAME):
        return {"ok": True, "enabled": False}
    tr = _app_command("--rotate-qq-message")
    r = _run_schtasks("/Create", "/TN", ROTATE_TASK_NAME, "/TR", tr,
                      "/SC", "DAILY", "/ST", "00:05", "/F")
    ok = r.returncode == 0
    (logger.ok if ok else logger.warn)("[定时] QQ 话术每日轮换任务: " + ("已就绪（每天 00:05 换一条）" if ok else "注册失败"), source="sched")
    return {"ok": ok}


def rotation_status() -> dict:
    r = _run_schtasks("/Query", "/TN", ROTATE_TASK_NAME, "/V", "/FO", "LIST")
    return {"exists": r.returncode == 0}


def sync_qq_start(config: dict) -> dict:
    """好友火花启用时，每天提前五分钟拉起引擎，给快速登录留足时间。"""
    enabled = bool(not _disabled(QQ_START_TASK_NAME) and config.get("friendSpark_enable") and (config.get("friendSpark_targets") or "").strip())
    if not enabled:
        current = _run_schtasks("/Query", "/TN", QQ_START_TASK_NAME, "/V", "/FO", "LIST")
        own_app = str(sys.executable if FROZEN else SOFTWARE_DIR / "main.py").lower()
        if current.returncode == 0 and own_app in current.stdout.lower():
            _run_schtasks("/Delete", "/TN", QQ_START_TASK_NAME, "/F")
        return {"ok": True, "enabled": False}
    time_text = str(config.get("friendSpark_time") or "10:00:00")
    try:
        send_at = datetime.strptime(time_text, "%H:%M:%S")
    except ValueError:
        return {"ok": False, "msg": "QQ 发送时间格式无效"}
    launch_at = send_at - timedelta(minutes=5)
    command = _app_command("--qq-scheduled-run")
    r = _run_schtasks("/Create", "/TN", QQ_START_TASK_NAME, "/TR", command,
                      "/SC", "DAILY", "/ST", launch_at.strftime("%H:%M"),
                      "/RL", "HIGHEST", "/F")
    if r.returncode != 0:
        logger.fail("[定时] QQ 引擎自启任务注册失败: " + (r.stderr or r.stdout), source="sched")
        return {"ok": False, "msg": "QQ 自动启动任务注册失败: " + (r.stderr or r.stdout).strip()}
    logger.ok("[定时] QQ 引擎每天 {0} 自动拉起，等待 {1} 发送".format(
        launch_at.strftime("%H:%M"), time_text), source="sched")
    return {"ok": True, "enabled": True, "start_time": launch_at.strftime("%H:%M")}


def _run_schtasks(*args) -> subprocess.CompletedProcess:
    return run_cmd(["schtasks"] + list(args), timeout=20)


def _task_info(name: str) -> dict:
    r = _run_schtasks("/Query", "/TN", name, "/V", "/FO", "LIST")
    if r.returncode != 0:
        return {"exists": False}
    def field(*names):
        for label in names:
            match = re.search(r"^" + re.escape(label) + r":\s*(.*)$", r.stdout, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return ""
    return {"exists": True,
            "next_run": field("下次运行时间", "Next Run Time"),
            "last_result": field("上次结果", "Last Result"),
            "action": field("要运行的任务", "Task To Run"),
            "start_time": field("开始时间", "Start Time"),
            "state": field("计划任务状态", "Scheduled Task State", "状态", "Status")}


def _needs_repair(name: str, expected: str) -> bool:
    info = _task_info(name)
    return (not info["exists"] or expected.lower() not in info["action"].lower()
            or info["state"].lower() in {"disabled", "已禁用"})


def ensure_watchdog() -> dict:
    """独立计划任务每 30 分钟检查一次；程序被隔离时仍需用户手动加信任。"""
    if _disabled(WATCHDOG_TASK_NAME):
        return {"ok": True, "enabled": False}
    expected = _app_command("--repair-schedules")
    if not _needs_repair(WATCHDOG_TASK_NAME, expected):
        return {"ok": True}
    action = _app_command("--repair-schedules")
    r = _run_schtasks("/Create", "/TN", WATCHDOG_TASK_NAME, "/TR", action,
                      "/SC", "MINUTE", "/MO", "30", "/F")
    if r.returncode != 0:
        logger.warn("[定时] 自检任务注册失败，请检查杀毒软件或系统权限", source="sched")
    return {"ok": r.returncode == 0}


def _desired_douyin_time() -> str | None:
    try:
        value = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        return value.get("douyin_time")
    except (OSError, ValueError, AttributeError):
        return None


def ensure_douyin() -> dict:
    """注册过的任务被删除或改路径后自动修复；首次升级继承原计划时间。"""
    if _disabled(TASK_NAME):
        return {"ok": True, "configured": False}
    wanted = _desired_douyin_time()
    if not wanted:
        existing = _task_info(TASK_NAME)
        if not existing["exists"]:
            return {"ok": True, "configured": False}
        match = re.search(r"(\d{1,2}):(\d{2})", existing["start_time"])
        if not match:
            return {"ok": False, "msg": "无法读取原抖音定时时间，请手动重新注册"}
        wanted = "{0:02d}:{1}".format(int(match.group(1)), match.group(2))
        _save_desired_time(wanted)
    expected = str(BACKEND_SCRIPT_DIR / "daily_douyin.ps1")
    if _needs_repair(TASK_NAME, expected):
        logger.warn("[定时] 抖音任务丢失或路径异常，正在重新注册", source="sched")
        return register(wanted)
    return {"ok": True, "configured": True}


def _save_desired_time(value: str) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    preferences = _preferences()
    preferences["douyin_time"] = value
    SCHEDULE_FILE.write_text(json.dumps(preferences, ensure_ascii=False),
                             encoding="utf-8")


def repair_all() -> dict:
    from backend import qq
    results = [ensure_douyin()]
    if _needs_repair(ROTATE_TASK_NAME, _app_command("--rotate-qq-message")):
        results.append(ensure_rotation())
    cfg = qq.get_plugin_config()
    if cfg.get("friendSpark_enable") and (cfg.get("friendSpark_targets") or "").strip():
        if _needs_repair(QQ_START_TASK_NAME, _app_command("--qq-scheduled-run")):
            results.append(sync_qq_start(cfg))
    results.append(ensure_watchdog())
    return {"ok": all(item.get("ok") for item in results)}


def register(time_str: str = "08:30") -> dict:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(time_str).strip())
    if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59):
        return {"ok": False, "msg": "时间格式应为 HH:MM（0-23 小时，0-59 分）"}
    time_str = "{0:02d}:{1:02d}".format(int(m.group(1)), int(m.group(2)))
    ps1 = BACKEND_SCRIPT_DIR / "daily_douyin.ps1"
    if not ps1.exists():
        return {"ok": False, "msg": "定时任务脚本缺失（安装包不完整）"}
    tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"'.format(ps1)
    r = _run_schtasks("/Create", "/TN", TASK_NAME, "/TR", tr, "/SC", "DAILY", "/ST", time_str, "/F")
    if r.returncode == 0:
        _set_disabled(TASK_NAME, False)
        _save_desired_time(time_str)
        logger.ok("[定时] 已注册每日 {0} 自动续抖音火花".format(time_str), source="sched")
        return {"ok": True, "msg": "已注册每日 {0} 运行".format(time_str)}
    logger.fail("[定时] 注册失败: " + r.stdout + r.stderr, source="sched")
    return {"ok": False, "msg": "注册失败: " + (r.stderr or r.stdout).strip()}


def remove() -> dict:
    return remove_tasks([TASK_NAME])


def restore_task(name: str) -> dict:
    if name not in TASKS:
        return {"ok": False, "msg": "任务无效"}
    _set_disabled(name, False)
    result = repair_all()
    if result["ok"] and not _task_info(name)["exists"]:
        return {"ok": False, "msg": "任务尚未配置，请先在定时页注册抖音任务，或在 QQ 页启用并保存好友续火花"}
    return result


def status() -> dict:
    r = _run_schtasks("/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST")
    if r.returncode != 0:
        return {"exists": False}
    text = r.stdout
    def field(*names):
        for name in names:
            m = re.search(r"^" + re.escape(name) + r":\s*(.*)$", text, re.MULTILINE)
            if m:
                return m.group(1).strip()
        return ""
    task_to_run = field("要运行的任务", "Task To Run")
    expected = str(BACKEND_SCRIPT_DIR / "daily_douyin.ps1").lower()
    return {
        "exists": True,
        "next_run": field("下次运行时间", "Next Run Time"),
        "last_result": field("上次结果", "Last Result"),
        "status": field("计划任务状态", "Status", "状态"),
        "task_to_run": task_to_run,
        "needs_repair": bool(task_to_run and expected not in task_to_run.lower()),
    }
