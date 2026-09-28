# -*- coding: utf-8 -*-
"""QQ 引擎：NapCat 进程启停/状态、续火花插件配置读写。

关键事实（来自 napcat.mjs 逆向确认）：
- 插件配置真实路径 = tools/napcat/shell/config/plugins/<插件id>/config.json
- 插件必须在 config/plugins.json 里有 {"<id>": true} 才会被 NapCat 加载
- 插件 id 取其 package.json 的 name，即 napcat-plugin-auto-tasks
"""
import json
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from backend import logger
from backend.paths import (BUNDLE_DIR, NAPCAT_CONFIG_DIR, NAPCAT_DIR,
                           NAPCAT_LAUNCHER, NAPCAT_LAUNCHER_WIN10,
                           PLUGIN_CONFIG_PATH, PLUGIN_DIR, PLUGIN_DIST,
                           PLUGIN_ENABLE_FILE, PLUGIN_ID,
                           LEGACY_PLUGIN_CONFIG, PLUGIN_REGISTRY)
from backend.winproc import CREATE_NO_WINDOW, run_cmd

DEFAULT_PLUGIN_CONFIG = {
    "enabled": True,
    "debug": False,
    "groupSign_enable": False,
    "groupSign_time": "08:00:00",
    "groupSign_targets": "",
    "groupSpark_enable": False,
    "groupSpark_time": "09:00:00",
    "groupSpark_message": "自动续火花",
    "groupSpark_targets": "",
    "friendSpark_enable": False,
    "friendSpark_time": "10:00:00",
    "friendSpark_message": "✨",
    "friendSpark_targets": "",
    "tasks": [],
    "groupConfigs": {},
}

_spark_keys = {k for k in DEFAULT_PLUGIN_CONFIG if k.startswith(("friendSpark", "groupSpark"))}
_running_cache = {"ts": 0.0, "val": False}
_cache_lock = threading.Lock()

# 软件直连 NapCat 的 OneBot HTTP 接口（立即发送用）
ONEBOT_HTTP_NAME = "spark-console"
ONEBOT_HTTP_PORT = 30001
_restart_in_progress = threading.Lock()


def normalize_time(v: str, fallback: str) -> str:
    """把 HH:MM / H:MM:SS 统一成插件全等比较所需的 HH:MM:SS。"""
    if not v:
        return fallback
    parts = str(v).split(":")
    if len(parts) == 2:
        parts.append("0")
    if len(parts) != 3:
        return fallback
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        return fallback
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
        return fallback
    return "{0:02d}:{1:02d}:{2:02d}".format(h, m, s)


def qq_running(max_age: float = 2.0) -> bool:
    """带 2 秒缓存的进程检测（前端 3 秒轮询一次，避免频繁拉起 tasklist）。"""
    with _cache_lock:
        now = time.time()
        if now - _running_cache["ts"] < max_age:
            return _running_cache["val"]
    r = run_cmd(["tasklist", "/FI", "IMAGENAME eq QQ.exe"])
    val = "QQ.exe" in r.stdout
    with _cache_lock:
        _running_cache.update(ts=time.time(), val=val)
    return val


def plugin_config_path() -> Path:
    return PLUGIN_CONFIG_PATH


def _ensure_plugin_enabled() -> None:
    """写 config/plugins.json 启用项；保留其他插件已有的键。"""
    PLUGIN_ENABLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PLUGIN_ENABLE_FILE.exists():
        try:
            data = json.loads(PLUGIN_ENABLE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    if data.get(PLUGIN_ID) is not True:
        data[PLUGIN_ID] = True
        PLUGIN_ENABLE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        logger.ok("[QQ] 已在 NapCat 中启用续火花插件（plugins.json）", source="qq")


def ensure_plugin_deployed() -> bool:
    """部署插件产物 + 启用项 + 旧配置迁移。
    插件来源：源码模式用 napcat-plugin-auto-tasks/dist；打包模式从 exe 内置资源释放。"""
    src_dir = plugin_source_dir()
    if not src_dir.joinpath("index.mjs").exists():
        logger.fail("[QQ] 插件产物缺失（安装包不完整）", source="qq")
        return False
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("index.mjs", "package.json"):
        src, dst = src_dir / name, PLUGIN_DIR / name
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            dst.write_bytes(src.read_bytes())
            logger.info("[QQ] 已部署插件文件 " + name, source="qq")
    _ensure_plugin_enabled()
    # 旧版本曾把配置写错位置：搬移到插件真实读取的路径；真实配置已存在时旧文件直接清掉
    if LEGACY_PLUGIN_CONFIG.exists():
        if not PLUGIN_CONFIG_PATH.exists():
            PLUGIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(LEGACY_PLUGIN_CONFIG), str(PLUGIN_CONFIG_PATH))
            logger.ok("[QQ] 已把旧配置文件迁移到插件真实读取路径", source="qq")
        else:
            LEGACY_PLUGIN_CONFIG.unlink(missing_ok=True)
            logger.info("[QQ] 清理了写错位置的旧配置文件（内容已由新路径接管）", source="qq")
    return True


def plugin_source_dir() -> Path:
    """源码运行和便携包共用同一处插件资源选择。"""
    if PLUGIN_DIST.joinpath("index.mjs").exists():
        return PLUGIN_DIST
    return BUNDLE_DIR / "backend" / "assets" / "auto-tasks"


def get_plugin_config() -> dict:
    cfg = dict(DEFAULT_PLUGIN_CONFIG)
    p = plugin_config_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warn("[QQ] 插件配置读取失败，返回默认模板: {0}".format(exc), source="qq")
    return cfg


def save_plugin_config(data: dict) -> dict:
    """合并式保存：以磁盘现有配置为底座，只更新本次提交的字段。
    绝不清空 tasks / groupConfigs / stats 等用户在别处配置的内容。
    """
    base = get_plugin_config()          # 已含磁盘现有内容（损坏时退默认模板并告警）
    if PLUGIN_CONFIG_PATH.exists():
        try:
            base.update(json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    base.update(data)
    PLUGIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLUGIN_CONFIG_PATH.write_text(json.dumps(base, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    # 清掉写错位置的旧文件（如有），避免用户误会
    if LEGACY_PLUGIN_CONFIG.exists():
        LEGACY_PLUGIN_CONFIG.unlink(missing_ok=True)
    need_restart = qq_running()
    if need_restart:
        logger.warn("[QQ] QQ 正在运行：新配置要点上方「停止」再「启动 QQ」后生效（不用重新扫码）", source="qq")
    logger.ok("[QQ] 插件配置已保存: " + str(PLUGIN_CONFIG_PATH), source="qq")
    from backend import scheduler
    schedule = scheduler.sync_qq_start(base)
    return {"saved": True, "path": str(PLUGIN_CONFIG_PATH), "need_restart": need_restart,
            "schedule_ok": schedule["ok"], "schedule_msg": schedule.get("msg", "")}


def _qq_installed() -> bool:
    r = run_cmd(["reg", "query",
                 r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ",
                 "/v", "UninstallString"])
    return r.returncode == 0 and "UninstallString" in r.stdout


def qq_account() -> str | None:
    """从 NapCat 生成的配置文件名探测已登录过的 QQ 号（onebot11_<QQ>.json）。"""
    for p in sorted(NAPCAT_CONFIG_DIR.glob("onebot11_*.json")):
        num = p.stem.replace("onebot11_", "")
        if num.isdigit():
            return num
    return None


def _kill_frontend_qq(wait_seconds: int = 10) -> bool:
    """自动关闭前台 QQ 再拉引擎。

    2026-09-17 实测：前台 QQ 与 NapCat 引擎登录同一个号会互顶——引擎报
    「当前账号已登录,无法重复登录」(ErrType 1/ErrCode 3)，扫码也会被顶回来；
    关掉前台 QQ 后 launcher -q 快速登录直接成功。聊天记录不受影响。
    （前台若是别的账号其实不冲突，但从外部探测不到前台登录的是哪个号，统一先关再拉。）
    """
    logger.warn("[QQ] 检测到前台 QQ：同账号会互相顶号，正在自动关闭前台 QQ（聊天记录不受影响，之后可随时重新登录）……", source="qq")
    run_cmd(["taskkill", "/F", "/IM", "QQ.exe"])
    run_cmd(["taskkill", "/F", "/IM", "QQEX.exe"])   # 最佳努力，失败不影响
    for _ in range(wait_seconds):
        if not qq_running(max_age=0.0):
            logger.ok("[QQ] 前台 QQ 已关闭，继续拉起续火花引擎", source="qq")
            return True
        time.sleep(1)
    logger.fail("[QQ] 前台 QQ 自动关闭超时：请手动退出 QQ（右下角图标右键→退出）后重试", source="qq")
    return False


def _webui_quick_login(account: str) -> bool:
    """WebUI 快速登录兜底（2026-09-17 实测调用链）：
    POST /api/auth/login {"hash": sha256(webui_token + ".napcat")} 换 Credential，
    再 POST /api/QQLogin/SetQuickLoginQQ {"uin": <int>} 触发快登。
    用于 -q 快登偶发失效时补一针，全程本地 127.0.0.1。"""
    import hashlib
    try:
        webui = json.loads((NAPCAT_CONFIG_DIR / "webui.json").read_text(encoding="utf-8"))
        port = int(webui.get("port") or 6099)
        token = str(webui.get("token") or "")
        if not token or not account.isdigit():
            return False
        h = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
        req = urllib.request.Request(
            "http://127.0.0.1:{0}/api/auth/login".format(port),
            data=json.dumps({"hash": h}).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=8) as resp:
            cred = (json.loads(resp.read().decode("utf-8")).get("data") or {}).get("Credential")
        if not cred:
            return False
        req = urllib.request.Request(
            "http://127.0.0.1:{0}/api/QQLogin/SetQuickLoginQQ".format(port),
            data=json.dumps({"uin": int(account)}).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + cred)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8")).get("code") == 0
    except Exception:
        return False


def _read_friend_spark_completed_at() -> int:
    """只读取好友火花整批完成标记，避免其他任务或首位好友触发收摊。"""
    try:
        st = (json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}).get("stats") or {}
        return int(st.get("friendSparkCompletedAt") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _read_friend_spark_result() -> dict:
    """读取插件最后一批好友续火花的完成时间和发送结果。"""
    try:
        stats = (json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8")) or {}).get("stats") or {}
        return {"completed_at": int(stats.get("friendSparkCompletedAt") or 0),
                "succeeded": int(stats.get("friendSparkSucceeded") or 0),
                "failed": int(stats.get("friendSparkFailed") or 0)}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"completed_at": 0, "succeeded": 0, "failed": 0}


def _has_other_enabled_tasks(config: dict) -> bool:
    return bool(config.get("groupSign_enable") or config.get("groupSpark_enable")
                or any(isinstance(task, dict) and task.get("enable")
                       for task in (config.get("tasks") or [])))


def _auto_stop_watcher(baseline: int) -> None:
    """等待插件明确写入好友火花整批完成标记后再收摊。"""
    while True:
        time.sleep(60)
        if not qq_running(max_age=0.0):
            return          # 引擎已被手动关闭，守护退场
        if _read_friend_spark_completed_at() > baseline:
            logger.info("[QQ] 好友续火花批次已运行结束，自动关闭 QQ 引擎；发送结果请查看 NapCat 日志", source="qq")
            stop()
            return


def scheduled_run(wait_seconds: int = 25 * 60) -> int:
    """计划任务入口：提前启动 QQ，并守候到好友批次结束或超时。"""
    cfg = get_plugin_config()
    if not cfg.get("friendSpark_enable") or not (cfg.get("friendSpark_targets") or "").strip():
        logger.info("[QQ定时] 好友续火花未启用，跳过", source="sched")
        return 0
    if not qq_account():
        logger.fail("[QQ定时] QQ 尚未扫码登录过，无法无人值守运行", source="sched")
        from backend import notify
        notify.notify_event("failure", "QQ 定时任务未运行：请先在软件里扫码登录一次")
        return 3
    baseline = _read_friend_spark_result()["completed_at"]
    result = start()
    if not result["started"] and "已在运行" not in result["msg"]:
        logger.fail("[QQ定时] 引擎启动失败: " + result["msg"], source="sched")
        from backend import notify
        notify.notify_event("failure", "QQ 定时任务引擎启动失败，请打开软件查看日志")
        return 2
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        batch = _read_friend_spark_result()
        if batch["completed_at"] > baseline:
            success = batch["succeeded"] > 0 and batch["failed"] == 0
            (logger.ok if success else logger.fail)(
                "[QQ定时] 好友批次完成：成功 {0}，失败 {1}".format(
                    batch["succeeded"], batch["failed"]), source="sched")
            if not _has_other_enabled_tasks(cfg) and qq_running(max_age=0.0):
                stop()
            if not success:
                from backend import notify
                notify.notify_event("failure", "QQ 定时续火花有发送失败，请查看 NapCat 日志")
            return 0 if success else 1
        time.sleep(5)
    logger.fail("[QQ定时] 等待好友批次完成超时，请检查 QQ 登录和插件日志", source="sched")
    from backend import notify
    notify.notify_event("failure", "QQ 定时任务等待超时，请检查登录和插件日志")
    if not _has_other_enabled_tasks(cfg):
        stop()
    return 1


def start() -> dict:
    if not plugin_source_dir().joinpath("index.mjs").exists():
        return {"started": False, "msg": "插件产物缺失，安装不完整"}
    if not _qq_installed():
        logger.fail("[QQ] 本机未检测到 QQ 聊天软件", source="qq")
        return {"started": False,
                "msg": "你的电脑没有安装 QQ。请先到 im.qq.com 下载安装 QQ，再回到这里点启动"}
    if qq_running(max_age=0.0):
        # 重复点启动时先识别已登录的 NapCat，避免把正在执行任务的引擎杀掉。
        existing = _read_onebot()
        servers = (existing.get("network") or {}).get("httpServers") or []
        entry = next((s for s in servers if s.get("name") == ONEBOT_HTTP_NAME
                      and s.get("enable", True) and s.get("token")), None)
        if entry and entry.get("port"):
            data = _onebot_call(entry["port"], entry["token"], "get_login_info", timeout=3).get("data")
            if isinstance(data, dict) and data.get("user_id"):
                return {"started": False, "msg": "QQ 续火花引擎已在运行，无需重复启动"}
        # 2026-09-17 实测：前台 QQ 同账号会顶掉引擎登录（已登录无法重复登录），
        # 关掉前台后快速登录直接成功；用户确认接受"要用续火花时自动关前台 QQ"。
        if not _kill_frontend_qq():
            return {"started": False,
                    "msg": "前台 QQ 没能自动关闭：请手动退出 QQ（右下角图标右键→退出）后，再点「启动 QQ」"}
    if not ensure_plugin_deployed():
        return {"started": False, "msg": "插件部署失败，请检查安装包"}
    ensure_onebot_http()
    launcher = NAPCAT_LAUNCHER if shutil.which("wt") else NAPCAT_LAUNCHER_WIN10
    account = qq_account()
    args = ["/c", str(launcher)]
    if account:
        args.append(account)      # 官方快速登录形式：launcher.bat <QQ号>（登录过一次即可）
        logger.info("[QQ] 正在用快速登录拉起 QQ（账号 {0}，通常不用扫码）……接下来会弹 UAC 与黑色日志窗".format(account), source="qq")
    else:
        logger.info("[QQ] 首次启动：接下来会弹 UAC（点「是」）、黑色日志窗和 QQ 扫码窗（只需扫这一次，之后自动快登）", source="qq")
    subprocess.Popen(["cmd"] + args, cwd=str(NAPCAT_DIR),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _watch():
        for _ in range(15):          # 最多等 30 秒
            time.sleep(2)
            if qq_running(max_age=0.0):
                logger.ok("[QQ] QQ 进程已拉起" + ("" if account else "，请在 QQ 窗口完成扫码登录（二维码也可以直接在本软件页面看）"), source="qq")
                break
        else:
            logger.fail("[QQ] 30 秒内没有检测到 QQ 启动：可能 UAC 弹窗被点了「否」。请再点一次「启动 QQ」并在弹窗时点「是」", source="qq")
            return
        if not account:
            return
        # 登录态确认（2026-09-17 实测教训：进程在 ≠ 登录成功，可能停在扫码页或被前台顶号）
        http_cfg = ensure_onebot_http()
        if not (http_cfg.get("ready") and not http_cfg.get("changed")):
            return          # 接口配置缺失/待重启时无从确认，保持旧行为
        port, token = http_cfg["port"], http_cfg["token"]
        for i in range(30):          # 最多再等 60 秒确认登录
            time.sleep(2)
            # NapCat≥4.18 健康桩对任何调用都回 retcode=0+空data，必须以 user_id 为准（2026-09-17 实测）
            d = _onebot_call(port, token, "get_login_info", timeout=3).get("data")
            if isinstance(d, dict) and d.get("user_id"):
                logger.ok("[QQ] 引擎登录已确认（账号 {0}，续火花就绪）".format(account), source="qq")
                return
            if i == 7:               # 进程起来约 15 秒仍未上线：WebUI 快登补一针
                if _webui_quick_login(account):
                    logger.info("[QQ] 已通过 WebUI 通道补发快速登录指令，等待生效……", source="qq")
                else:
                    logger.info("[QQ] 登录尚未完成：若 QQ 窗口停在扫码页，请扫码（仅这一次）", source="qq")
        logger.warn("[QQ] 引擎已拉起但 60 秒内未确认登录：请看一眼 QQ 窗口（可能在等扫码）", source="qq")

    threading.Thread(target=_watch, daemon=True).start()
    # 只有好友火花任务时才自动收摊，避免中断其他仍在执行的群/自定义任务。
    config = get_plugin_config()
    if _has_other_enabled_tasks(config):
        logger.info("[QQ] 检测到其他已启用任务，本次不自动收摊；完成后请手动点「停止」", source="qq")
    else:
        threading.Thread(target=_auto_stop_watcher, args=(_read_friend_spark_completed_at(),),
                         daemon=True).start()
    return {"started": True,
            "msg": "启动中（" + ("快速登录 " + account if account else "首次需扫码") + "）"}


# ---------------- 登录二维码（本机登录，展示进界面 + 自动清理） ----------------

QR_FILE = NAPCAT_DIR / "cache" / "qrcode.png"


def qq_friends() -> dict:
    """拉取 QQ 好友列表（OneBot get_friend_list），供 UI 勾选多好友。"""
    if not qq_running(max_age=0.0):
        return {"ok": False, "msg": "QQ 还没启动：请先点「▶ 启动 QQ」"}
    http_cfg = ensure_onebot_http()
    if not http_cfg.get("ready"):
        return {"ok": False, "msg": http_cfg.get("msg", "本地接口不可用")}
    if http_cfg.get("changed") or not _wait_http_up(http_cfg["port"], http_cfg["token"], 5):
        return {"ok": False,
                "msg": "本地接口未就绪：请点「■ 停止」再「▶ 启动 QQ」一次（不用扫码），然后重试"}
    r = _onebot_call(http_cfg["port"], http_cfg["token"], "get_friend_list", timeout=15)
    if r.get("retcode") != 0 or not isinstance(r.get("data"), list):
        return {"ok": False, "msg": "拉取好友列表失败: " + str(r.get("message") or "未知")}
    friends = [{"id": str(f.get("user_id", "")),
                "name": f.get("remark") or f.get("nickname") or str(f.get("user_id", ""))}
               for f in r["data"] if f.get("user_id")]
    logger.ok("[QQ] 已拉取 {0} 位好友".format(len(friends)), source="qq")
    return {"ok": True, "friends": friends}


def get_qrcode() -> dict:
    """返回最新登录二维码（base64 data URL）。超过 3 分钟的旧码不再展示。"""
    try:
        if not QR_FILE.exists():
            return {"has_qr": False}
        age = time.time() - QR_FILE.stat().st_mtime
        if age > 180:
            return {"has_qr": False, "note": "二维码已过期：若 QQ 窗口里出现了新码，点一次「启动 QQ」旁边不动它即可刷新"}
        import base64
        b64 = base64.b64encode(QR_FILE.read_bytes()).decode()
        return {"has_qr": True, "data_url": "data:image/png;base64," + b64,
                "age_seconds": int(age)}
    except OSError:
        return {"has_qr": False}


def cleanup_qr_files() -> None:
    """清理散落各处的过期二维码图片（保留 cache/qrcode.png 本体）。"""
    import time as _t
    now = _t.time()
    for pattern in ("*qrcode*.png", "*QRCode*.png"):
        for p in NAPCAT_DIR.rglob(pattern):
            try:
                if p == QR_FILE:
                    continue
                if now - p.stat().st_mtime > 86400:
                    p.unlink()
                    logger.info("[QQ] 清理过期二维码图片: " + p.name, source="qq")
            except OSError:
                continue


def stop() -> dict:
    if not qq_running(max_age=0.0):
        return {"stopped": False, "msg": "QQ 当前没有在运行"}
    logger.warn("[QQ] 正在结束 QQ 进程（含续火花引擎）……", source="qq")
    run_cmd(["taskkill", "/IM", "QQ.exe", "/F"])
    logger.ok("[QQ] 已停止", source="qq")
    return {"stopped": True, "msg": "QQ / 续火花引擎已停止"}


# ---------------- OneBot HTTP 直连（立即续火花） ----------------

def _onebot_config_path() -> Path | None:
    """登录后 NapCat 会生成 onebot11_<QQ号>.json；未登录时没有。"""
    for p in sorted(NAPCAT_CONFIG_DIR.glob("onebot11_*.json")):
        return p
    return None


def _read_onebot() -> dict:
    p = _onebot_config_path()
    if not p:
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ensure_onebot_http() -> dict:
    """确保存在软件专用的本地 HTTP 接口。返回 {port, token, changed}。
    changed=True 表示本次写入了配置，需要重启 QQ 引擎后才生效。"""
    p = _onebot_config_path()
    if not p:
        return {"ready": False, "changed": False,
                "msg": "还没有 QQ 登录过（找不到 OneBot 配置），请先启动 QQ 扫码"}
    data = _read_onebot()
    if not data:
        return {"ready": False, "changed": False, "msg": "OneBot 配置读取失败"}
    servers = data.setdefault("network", {}).setdefault("httpServers", [])
    entry = next((s for s in servers if s.get("name") == ONEBOT_HTTP_NAME), None)
    if entry and entry.get("enable", True) and entry.get("token"):
        return {"ready": True, "changed": False,
                "port": entry["port"], "token": entry["token"]}
    token = (entry or {}).get("token") or secrets.token_hex(16)
    new_entry = {"name": ONEBOT_HTTP_NAME, "enable": True, "host": "127.0.0.1",
                 "port": ONEBOT_HTTP_PORT, "enableCors": False,
                 "enableWebsocket": False, "messagePostFormat": "array",
                 "token": token, "debug": False}
    if entry:
        entry.update(new_entry)
    else:
        servers.append(new_entry)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.ok("[QQ] 已开启本地发送接口（127.0.0.1:{0}），重启 QQ 引擎后生效".format(ONEBOT_HTTP_PORT), source="qq")
    return {"ready": True, "changed": True, "port": ONEBOT_HTTP_PORT, "token": token}


def _onebot_call(port: int, token: str, endpoint: str, payload: dict | None = None,
                 timeout: float = 10) -> dict:
    url = "http://127.0.0.1:{0}/{1}".format(port, endpoint)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Authorization", "Bearer " + token)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        return {"status": "failed", "retcode": -1, "message": str(exc)}


def _wait_http_up(port: int, token: str, seconds: int = 60) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        d = _onebot_call(port, token, "get_login_info", timeout=3).get("data")
        if isinstance(d, dict) and d.get("user_id"):   # 健康桩空data不算在线
            return True
        time.sleep(2)
    return False


def qq_send_now() -> dict:
    """立即给好友续火花配置里的所有 QQ 号发送一条话术（OneBot 直连）。"""
    if not qq_running(max_age=0.0):
        return {"ok": False, "msg": "QQ 还没启动。请先在上方点「▶ 启动 QQ」并扫码"}
    http_cfg = ensure_onebot_http()
    if not http_cfg.get("ready"):
        return {"ok": False, "msg": http_cfg.get("msg", "本地接口不可用")}
    if http_cfg.get("changed"):
        # 接口配置刚写入，当前引擎还没加载它：自动重启一次引擎（登录态保留，不用扫码）
        with _restart_in_progress:
            logger.warn("[QQ] 本地发送接口需要重启引擎加载，正在自动重启（不用重新扫码）……", source="qq")
            stop()
            for _ in range(10):          # 等 QQ 进程真正退出（最多 10 秒）
                if not qq_running(max_age=0.0):
                    break
                time.sleep(1)
            start()
        if not _wait_http_up(http_cfg["port"], http_cfg["token"], 90):
            return {"ok": False,
                    "msg": "接口重启后没有就绪：可能 QQ 停在了扫码页，请手动完成登录后再点一次"}
    else:
        if not _wait_http_up(http_cfg["port"], http_cfg["token"], 8):
            return {"ok": False,
                    "msg": "本地接口未就绪。若刚改过配置，请点「■ 停止」再「▶ 启动 QQ」一次后重试"}

    cfg = get_plugin_config()
    raw_targets = (cfg.get("friendSpark_targets") or "").strip()
    if not raw_targets:
        return {"ok": False, "msg": "还没填对方 QQ 号：请在上方「对方 QQ 号」里填好并保存"}
    # 话术从共享话术池随机抽（QQ 与抖音共用），统一带固定结尾签名
    from backend import pool as pool_mod
    item = pool_mod.pick_random()
    if item["type"] == "text":
        message = item["content"]            # pick_random 已内嵌签名
    else:
        message = "[CQ:image,file=file:///" + item["abs_path"].replace("\\", "/") + "] " + pool_mod.SIGNATURE
    logger.info("[QQ] 本次抽取话术: {0}".format("图片表情+签名" if item["type"] == "image" else "文字+签名"), source="qq")
    port, token = http_cfg["port"], http_cfg["token"]
    results = []
    for uid in [t.strip() for t in raw_targets.split(",") if t.strip()]:
        if not uid.isdigit():
            results.append({"target": uid, "ok": False, "msg": "QQ 号格式不对"})
            continue
        r = _onebot_call(port, token, "send_private_msg",
                         {"user_id": int(uid), "message": message}, timeout=15)
        ok = r.get("retcode") == 0
        results.append({"target": uid, "ok": ok,
                        "msg": "已发送" if ok else "失败: {0}".format(r.get("message") or r.get("wording") or "未知")})
        (logger.ok if ok else logger.fail)("[QQ] 立即续火花 → {0}: {1}".format(uid, results[-1]["msg"]), source="qq")
    sent = sum(1 for x in results if x["ok"])
    from backend import notify as _notify
    _notify.notify_event("success" if sent == len(results) else "failure",
                         "QQ 立即续火花：{0}/{1} 位成功".format(sent, len(results)))
    msg = "已发送 {0}/{1} 位好友".format(sent, len(results))
    if results and sent == len(results):
        # 全部成功：任务完成，自动收摊（2026-09-17 用户需求：引擎退场，前台 QQ 才能登录）
        logger.ok("[QQ] 立即续火花全部成功，自动关闭 QQ 引擎（前台 QQ 现在可以正常登录了）", source="qq")
        stop()
        msg += "，引擎已自动关闭"
    elif results:
        logger.warn("[QQ] 有好友发送失败：引擎保持运行，可在界面重试；不用时请点「■ 停止」释放前台 QQ", source="qq")
    return {"ok": sent > 0, "results": results, "msg": msg}


def send_from_tray() -> dict:
    """托盘一键发送：必要时先启动引擎并等待登录，不在扫码前盲发。"""
    if not qq_running(max_age=0.0):
        started = start()
        if not started.get("started") and "已在运行" not in started.get("msg", ""):
            return {"ok": False, "msg": started.get("msg", "QQ 引擎启动失败")}
    http = ensure_onebot_http()
    if not http.get("ready"):
        return {"ok": False, "msg": http.get("msg", "QQ 本地接口未就绪")}
    if http.get("changed"):
        return qq_send_now()  # 已运行的引擎需重载新接口，qq_send_now 会处理重启
    if not _wait_http_up(http["port"], http["token"], 120):
        return {"ok": False, "msg": "QQ 登录未完成；请在窗口完成扫码后重试"}
    return qq_send_now()
