# -*- coding: utf-8 -*-
"""抖音引擎：登录（界面内自动检测）/ 运行（正式与演练）/ 配置读写 / 状态。"""
import json
import os
import subprocess
import threading
from pathlib import Path

from backend import logger
from backend.paths import (DOUYIN_BOOTSTRAP, DOUYIN_CONFIG, DOUYIN_DEPS,
                           DOUYIN_DIR, DOUYIN_ENV, DOUYIN_LOCK,
                           DOUYIN_RUNTIME_PY, DOUYIN_STATE, DOUYIN_VENV_PY,
                           FETCH_FRIENDS_SCRIPT, LOGIN_GUI_SCRIPT,
                           PLACEHOLDER_PREFIX, SOFTWARE_DIR)
from backend.winproc import CREATE_NO_WINDOW, run_cmd

_procs: dict[str, subprocess.Popen] = {}
_lock = threading.Lock()


def _venv_ready() -> bool:
    return DOUYIN_VENV_PY.exists()


def engine_python() -> str:
    """抖音引擎解释器：开发机用 venv；分发包用嵌入式 runtime（免装 Python）。
    runtime 是 _pth 隔离模式（无视 PYTHONPATH），确保 deps 路径已写入 _pth。"""
    if DOUYIN_VENV_PY.exists():
        return str(DOUYIN_VENV_PY)
    if DOUYIN_RUNTIME_PY.exists():
        _ensure_pth_deps()
        return str(DOUYIN_RUNTIME_PY)
    return ""


def _ensure_pth_deps() -> None:
    """把 douyin-auto-fire/deps 追加进 runtime 的 _pth（幂等，缺失才写）。"""
    pth = DOUYIN_RUNTIME_PY.parent / "python312._pth"
    if not pth.exists() or not DOUYIN_DEPS.exists():
        return
    try:
        lines = pth.read_text(encoding="utf-8", errors="replace").splitlines()
        rel = ".." / DOUYIN_DEPS.relative_to(DOUYIN_RUNTIME_PY.parent.parent)
        rel_win = str(rel).replace("/", chr(92))
        if any("deps" in ln for ln in lines):
            return
        pth.write_text(chr(10).join(lines + [rel_win]) + chr(10), encoding="utf-8")
        logger.info("[抖音] 已把引擎依赖路径写入 runtime _pth（自动修复）", source="douyin")
    except OSError:
        pass


def env_ready() -> bool:
    """引擎环境就绪 = 有解释器（依赖由引导脚本保证装齐）。"""
    return bool(engine_python())


def setup_env() -> dict:
    """启动「①一键安装引擎.bat」：下载嵌入式 Python + 装依赖 + 浏览器组件。"""
    import subprocess
    if not DOUYIN_BOOTSTRAP.exists():
        return {"started": False, "msg": "找不到安装脚本：" + str(DOUYIN_BOOTSTRAP)}
    if env_ready():
        return {"started": False, "msg": "运行环境已装好，无需重复安装"}
    subprocess.Popen(["cmd", "/c", str(DOUYIN_BOOTSTRAP)],
                     cwd=str(DOUYIN_BOOTSTRAP.parent),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    logger.info("[抖音] 引擎安装已启动（弹出的黑窗是安装进度，请等它跑完，约 5-10 分钟）", source="douyin")
    return {"started": True, "msg": "安装程序已弹出，请在那个窗口等进度跑完（约 5-10 分钟），完成后回来点「演练」验证"}


def logged_in() -> bool:
    if DOUYIN_STATE.exists():
        return True
    if DOUYIN_ENV.exists():
        for line in DOUYIN_ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DOUYIN_COOKIE=") and len(line.strip()) > 20:
                return True
    return False


def friends() -> list[str]:
    try:
        return [t.get("name", "") for t in get_config().get("targets", [])]
    except Exception:
        return []


def save_friends(names: list[str]) -> dict:
    """用给定的好友列表重建 config.json 的 targets（话术从共享池生成）。
    列表即全部：UI 里删掉的这里就消失（修复过"删除后又回来"的 bug）。"""
    from backend import pool as pool_mod
    from backend.paths import PLACEHOLDER_PREFIX
    names = [n.strip() for n in names if n and n.strip()]
    names = [n for n in names if not n.startswith(PLACEHOLDER_PREFIX)]
    if not names:
        return {"ok": False, "msg": "至少保留一位好友"}
    choices = pool_mod.douyin_choices()
    if not choices:
        return {"ok": False, "msg": "话术库是空的：请先到「话术库」页添加文字或表情"}
    cfg = get_config() or _default_config()
    # 每位好友的消息序列：随机抽 1 条 + 固定签名结尾（用户规范）
    cfg["targets"] = [{"name": n,
                       "messages": [{"type": "random", "choices": choices},
                                    pool_mod.douyin_signature_message()]}
                      for n in names]
    try:
        save_config(cfg)
    except ValueError as exc:
        return {"ok": False, "msg": str(exc)}
    logger.ok("[抖音] 好友列表已更新（{0} 位）".format(len(names)), source="douyin")
    return {"ok": True, "friends": names}


def _default_config() -> dict:
    return {
        "timezone": "Asia/Shanghai", "task_id": "spark-daily",
        "targets": [], "stickers": {
            "比心": {"category": "常用", "accessible_name": "比心", "fallback_index": 3},
            "开心": {"category": "常用", "accessible_name": "开心", "fallback_index": 5},
        },
        "send_interval_seconds": {"min": 3, "max": 8},
        "continue_on_error": True, "prevent_duplicates": True,
        "target_open_retries": 1, "target_open_timeout_seconds": 15,
    }


def rebuild_from_pool() -> dict:
    """话术池变化后，重建所有 target 的 choices（好友名单不变）。"""
    from backend import pool as pool_mod
    names = [n for n in friends() if not n.startswith(PLACEHOLDER_PREFIX)]
    if not names:
        return {"ok": True, "friends": []}
    return save_friends(names)


def has_placeholder() -> bool:
    return any(f.startswith(PLACEHOLDER_PREFIX) for f in friends())


def _engine_env() -> dict:
    """子引擎环境：强制 UTF-8；嵌入式 runtime 时加 PYTHONPATH 指向 deps。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if engine_python() == str(DOUYIN_RUNTIME_PY) and DOUYIN_DEPS.exists():
        env["PYTHONPATH"] = str(DOUIN_DEPS)
    return env


def _clear_stale_lock() -> None:
    """引擎异常被杀会残留 run.lock（O_EXCL 锁）。pid 已死则代为清理。"""
    if not DOUYIN_LOCK.exists():
        return
    pid = None
    try:
        pid = int(DOUYIN_LOCK.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    alive = False
    if pid:
        r = run_cmd(["tasklist", "/FI", "PID eq {0}".format(pid)])
        alive = (".exe" in r.stdout and "INFO:" not in r.stdout)
    if not alive:
        try:
            DOUYIN_LOCK.unlink()
            logger.warn("[抖音] 检测到上次异常残留的任务锁，已自动清理", source="douyin")
        except OSError:
            pass


def get_config() -> dict:
    if not DOUYIN_CONFIG.exists():
        return {}
    try:
        return json.loads(DOUYIN_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.fail("[抖音] config.json 损坏无法读取，请到「话术库」页重新保存一次: {0}".format(exc), source="douyin")
        return {}


def save_config(cfg: dict) -> None:
    """先写临时文件 → 用引擎解析器校验 → 通过才原子替换。绝不留下坏配置。"""
    if not env_ready():
        raise RuntimeError("运行环境还没安装：请点「一键安装引擎」")
    tmp = DOUYIN_CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    env = _engine_env()
    env["TASK_CONFIG"] = str(tmp)
    r = run_cmd([engine_python(), "-c",
                 "from app.config import load_settings, load_task;"
                 "load_task(load_settings())"], cwd=DOUYIN_DIR, env=env)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        lines = [ln.strip() for ln in (r.stderr or r.stdout).splitlines() if ln.strip()]
        reason = lines[-1] if lines else "原因未知"
        raise ValueError("配置未通过校验: " + reason[-200:])
    import os as _os
    _os.replace(tmp, DOUYIN_CONFIG)


def _spawn(key: str, args: list[str]) -> dict:
    with _lock:
        p = _procs.get(key)
        if p and p.poll() is None:
            return {"started": False, "msg": "已有同名任务在运行中"}
        proc = subprocess.Popen(
            [engine_python()] + args, cwd=DOUYIN_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=_engine_env(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
        _procs[key] = proc
    threading.Thread(target=_pump, args=(key, proc), daemon=True).start()
    return {"started": True, "msg": "已启动"}


def _pump(key: str, proc: subprocess.Popen) -> None:
    logger.info("[抖音] {0} 开始，输出实时转入日志".format(key), source="douyin")
    # 上游日志出于隐私把好友名打码成 好友01/02…，这里翻译回真实名字
    import re
    name_map = {}
    for idx, name in enumerate(friends(), start=1):
        name_map["好友{0:02d}".format(idx)] = name
        name_map["好友{0}".format(idx)] = name
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        m = re.search(r"好友处理失败: (好友\d+)", line)
        if m:
            alias = m.group(1)
            real = name_map.get(alias, "")
            logger.fail("[抖音] 好友「{0}」发送失败（日志别名 {1}）：请确认这个名字与抖音搜索面板显示的完全一致（含表情符号）。推荐在「抖音」页用「从抖音拉取最近会话」重新勾选".format(real or alias, alias), source="douyin")
            continue
        m2 = re.search(r"跳过当天已处理或结果不确定的消息: (好友\d+)", line)
        if m2:
            alias = m2.group(1)
            real = name_map.get(alias, "")
            logger.warn("[抖音] 好友「{0}」今天已发过（或上次尝试结果不确定），本轮跳过。若是『不确定』残留，可点「补发」按钮".format(real or alias), source="douyin")
            continue
        logger.log("OUT", line, source="douyin")
    code = proc.wait()
    if code == 0:
        logger.ok("[抖音] {0} 完成（退出码 0）".format(key), source="douyin")
    else:
        logger.fail("[抖音] {0} 没有成功（退出码 {1}）。点左侧「日志」页看第二个框可定位原因".format(key, code), source="douyin")


def start_login() -> dict:
    """打开可见浏览器让用户扫码；后台轮询登录 Cookie，成功自动保存凭证。"""
    if not env_ready():
        return {"started": False, "msg": "运行环境还没装：请先点上面的「一键安装引擎」（约 5-10 分钟，只需一次）"}
    if not LOGIN_GUI_SCRIPT.exists():
        return {"started": False, "msg": "登录组件缺失（安装包不完整，请重新下载）"}
    logger.info("[抖音] 打开浏览器等待扫码（5 分钟内有效，登录后自动保存）", source="douyin")
    return _spawn("login", [str(LOGIN_GUI_SCRIPT)])


def run(dry_run: bool = False) -> dict:
    if not env_ready():
        return {"started": False, "msg": "运行环境还没装：请先点上面的「一键安装引擎」（约 5-10 分钟，只需一次）"}
    if not logged_in():
        return {"started": False, "msg": "还没有登录抖音，请先在「抖音」页点「打开扫码登录」"}
    if has_placeholder():
        return {"started": False,
                "msg": "话术库里还是示例名字「{0}」，请先到「话术库」页改成真实好友昵称".format(friends()[0])}
    _clear_stale_lock()
    mode = "演练(dry-run)" if dry_run else "正式发送"
    logger.info("[抖音] 启动{0}……".format(mode), source="douyin")
    # 演练与正式共用一个槽位，避免同时跑撞引擎锁
    return _spawn("run", ["run.py"] + (["--dry-run"] if dry_run else []))


def proc_status() -> dict:
    with _lock:
        return {k: (p.poll() is None) for k, p in _procs.items()}


def fix_uncertain() -> dict:
    """清除"结果不确定"的发送占位记录并立即补发。
    只清今天、且最近一轮结果证实 sent=0（确认没发出去）的好友；
    绝不动 success 记录（防重复发送）。"""
    from backend.paths import DOUYIN_DIR
    hist_path = DOUYIN_DIR / "artifacts" / "history.json"
    result_path = DOUYIN_DIR / "artifacts" / "result.json"
    today = __import__("datetime").date.today().isoformat()
    if not hist_path.exists():
        return {"ok": False, "msg": "还没有发送历史记录"}
    try:
        hist = json.loads(hist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "msg": "发送历史文件损坏"}
    # 最近一轮里"确实没发出去"的目标名单（sent=0）
    not_sent = set()
    if result_path.exists():
        try:
            res = json.loads(result_path.read_text(encoding="utf-8"))
            if res.get("finished_at", "").startswith(today):
                for r in res.get("results", []):
                    if r.get("sent") == 0:
                        not_sent.add(r.get("target", ""))
        except (OSError, json.JSONDecodeError):
            pass
    removed, kept = [], []
    for k in list(hist.keys()):
        parts = k.split(":")
        if len(parts) < 4 or parts[1] != today:
            continue
        if hist[k].get("status") == "unknown":
            target = parts[2]
            # 引擎打码名也按"今天确实没发出"处理（防重复宁可保守）；有实名证据的更稳
            if target in not_sent or not target.startswith("好友"):
                del hist[k]
                removed.append(target)
            else:
                kept.append(target)
    if removed:
        hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.ok("[抖音] 已清除 {0} 条『未发出』的残留记录（{1}），准备补发".format(
            len(removed), "、".join(removed)), source="douyin")
    else:
        logger.info("[抖音] 没有『确认未发出』的残留记录，无需补发", source="douyin")
    r = run(dry_run=False)
    return {"ok": True, "removed": removed, "kept_unknown": kept, "run": r,
            "msg": "已清除 {0} 条残留并启动补发".format(len(removed)) if removed else "无残留，已照常启动一轮发送"}
