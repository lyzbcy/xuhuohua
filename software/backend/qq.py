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
from backend.paths import (NAPCAT_CONFIG_DIR, NAPCAT_DIR, NAPCAT_LAUNCHER,
                           NAPCAT_LAUNCHER_WIN10, PLUGIN_CONFIG_PATH,
                           PLUGIN_DIR, PLUGIN_DIST, PLUGIN_ENABLE_FILE,
                           PLUGIN_ID, LEGACY_PLUGIN_CONFIG, PLUGIN_REGISTRY)
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
    """部署插件产物 + 启用项 + 旧配置迁移。"""
    if not PLUGIN_DIST.joinpath("index.mjs").exists():
        logger.fail("[QQ] 插件产物缺失（napcat-plugin-auto-tasks/dist）", source="qq")
        return False
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("index.mjs", "package.json"):
        src, dst = PLUGIN_DIST / name, PLUGIN_DIR / name
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
    return {"saved": True, "path": str(PLUGIN_CONFIG_PATH), "need_restart": need_restart}


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


def start() -> dict:
    if not PLUGIN_DIST.joinpath("index.mjs").exists():
        return {"started": False, "msg": "插件产物缺失，安装不完整"}
    if not _qq_installed():
        logger.fail("[QQ] 本机未检测到 QQ 聊天软件", source="qq")
        return {"started": False,
                "msg": "你的电脑没有安装 QQ。请先到 im.qq.com 下载安装 QQ，再回到这里点启动"}
    if qq_running(max_age=0.0):
        logger.warn("[QQ] 检测到 QQ 已在运行（可能不是本软件拉起的）", source="qq")
        return {"started": False,
                "msg": "检测到 QQ 已经开着，但可能不是由本软件启动的（没有续火能力）。请先完全退出 QQ（右下角图标右键→退出），再回来点「启动 QQ」"}
    ensure_plugin_deployed()
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
                return
        logger.fail("[QQ] 30 秒内没有检测到 QQ 启动：可能 UAC 弹窗被点了「否」。请再点一次「启动 QQ」并在弹窗时点「是」", source="qq")

    threading.Thread(target=_watch, daemon=True).start()
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
        r = _onebot_call(port, token, "get_login_info", timeout=3)
        if r.get("retcode") == 0:
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
    return {"ok": sent > 0, "results": results,
            "msg": "已发送 {0}/{1} 位好友".format(sent, len(results))}
