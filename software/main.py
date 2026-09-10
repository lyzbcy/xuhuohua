# -*- coding: utf-8 -*-
"""续火花控制台 —— 主程序
pywebview 窗口 + Python 后端桥接（前端通过 pywebview.api.* 调用）。
启动：software 下的 .venv/Scripts/python.exe main.py
"""
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import webview  # noqa: E402

from backend import douyin, logger, pool, qq, scheduler, updater  # noqa: E402
from backend.paths import (DOUYIN_RUNLOG, DOUYIN_STICKERS,  # noqa: E402
                           LOG_DIR, NAPCAT_DIR, PROJECT_ROOT, UI_DIR,
                           UI_STICKER_DIR)

WINDOW_TITLE = "续火花控制台"
INSTANCE_PORT = 28099


class Api:
    # ---------- 全局状态 ----------
    def get_state(self):
        plugin_cfg = qq.get_plugin_config()
        sched = scheduler.status()
        return {
            "version": updater.get_version(),
            "douyin": {
                "logged_in": douyin.logged_in(),
                "env_ready": douyin.env_ready(),
                "friends": douyin.friends(),
                "has_placeholder": douyin.has_placeholder(),
                "running": douyin.proc_status(),
            },
            "qq": {
                "running": qq.qq_running(),
                "quick_account": qq.qq_account(),
                "send_time": plugin_cfg.get("friendSpark_time", "10:00:00"),
                "targets": plugin_cfg.get("friendSpark_targets", ""),
            },
            "schedule": sched,
            "rotate": scheduler.rotation_status(),
            "pool": pool.get_pool(),
        }

    def get_events(self, since: int = 0):
        return {"events": logger.get_events(int(since))}

    # ---------- 共享话术库 ----------
    def pool_get(self):
        return {"ok": True, "pool": pool.get_pool()}

    def pool_save(self, texts, stickers):
        r = pool.save_pool(list(texts or []), list(stickers or []))
        if r.get("ok"):
            # 抖音 config.json 的 choices 同步重建（好友名单不动）
            rr = douyin.rebuild_from_pool()
            if not rr.get("ok"):
                return {"ok": False, "msg": rr.get("msg", "抖音配置重建失败")}
        return r

    def douyin_stickers(self):
        """表情镜像到 ui/assets/stickers，前端用稳定的相对路径展示。"""
        import shutil
        items = []
        if DOUYIN_STICKERS.exists():
            for p in sorted(DOUYIN_STICKERS.glob("*.png")):
                dst = UI_STICKER_DIR / p.name
                if not dst.exists() or dst.stat().st_mtime != p.stat().st_mtime:
                    shutil.copy2(p, dst)
                items.append({
                    "name": p.stem,
                    "file": "stickers-lb/" + p.name,
                    "rel": "assets/stickers/" + p.name,
                })
        return {"stickers": items}

    # ---------- 抖音 ----------
    def douyin_login(self):
        return douyin.start_login()

    def douyin_setup_env(self):
        return douyin.setup_env()

    def douyin_run(self, dry_run=False):
        return douyin.run(bool(dry_run))

    def douyin_fix_uncertain(self):
        return douyin.fix_uncertain()

    def douyin_get_config(self):
        return {"ok": True, "config": douyin.get_config()}

    def douyin_save_friends(self, names):
        return douyin.save_friends([str(n) for n in (names or [])])

    def douyin_fetch_friends(self):
        """打开无头浏览器抓取抖音最近会话名（约 20-40 秒）。"""
        if not douyin.logged_in():
            return {"ok": False, "msg": "请先扫码登录抖音"}
        from backend.winproc import run_cmd
        logger.info("[抖音] 正在拉取最近会话列表（约半分钟，请稍等）……", source="douyin")
        r = run_cmd([str(douyin.DOUYIN_VENV_PY),
                     str(Path(douyin.__file__).parent / "fetch_friends.py")],
                    timeout=240, cwd=douyin.DOUYIN_DIR)
        out = (r.stdout or "")
        if "FRIENDS_OK" in out:
            from backend.paths import PROJECT_ROOT
            f = PROJECT_ROOT / "douyin-auto-fire" / "artifacts" / "douyin_friends.json"
            try:
                names = json.loads(f.read_text(encoding="utf-8"))
                logger.ok("[抖音] 已拉取 {0} 个最近会话名".format(len(names)), source="douyin")
                return {"ok": True, "names": names}
            except (OSError, json.JSONDecodeError):
                pass
        logger.fail("[抖音] 拉取会话列表失败: {0}".format((r.stderr or out)[-150:]), source="douyin")
        return {"ok": False, "msg": "拉取失败（抖音页面可能改版了）。可以手动输入好友昵称，效果一样"}

    def douyin_runlog_tail(self, lines: int = 60):
        try:
            text = DOUYIN_RUNLOG.read_text(encoding="utf-8", errors="replace")
            return {"text": "\n".join(text.splitlines()[-int(lines):])}
        except OSError:
            return {"text": "暂无发送日志（还没运行过）"}

    # ---------- QQ ----------
    def qq_start(self):
        return qq.start()

    def qq_stop(self):
        return qq.stop()

    def qq_get_config(self):
        return {"ok": True, "config": qq.get_plugin_config(),
                "running": qq.qq_running()}

    def qq_save_config(self, config):
        return qq.save_plugin_config(dict(config))

    def qq_send_now(self):
        return qq.qq_send_now()

    def qq_friends(self):
        return qq.qq_friends()

    def qq_qrcode(self):
        return qq.get_qrcode()

    # ---------- 定时 ----------
    def schedule_register(self, time_str="08:30"):
        return scheduler.register(str(time_str))

    def schedule_remove(self):
        return scheduler.remove()

    def schedule_status(self):
        return scheduler.status()

    # ---------- 日志 ----------
    def logs_today(self):
        return {"text": logger.today_log_text()}

    def open_folder(self, which: str = "logs"):
        target = {"logs": LOG_DIR, "douyin": PROJECT_ROOT / "douyin-auto-fire",
                  "napcat": NAPCAT_DIR, "project": PROJECT_ROOT}.get(which, LOG_DIR)
        if not target.exists():
            logger.warn("文件夹不存在: " + str(target))
            return {"ok": False, "msg": "文件夹不存在"}
        import subprocess
        subprocess.Popen(["explorer", str(target)])
        logger.info("已打开文件夹：" + str(target))
        return {"ok": True}

    # ---------- 更新 ----------
    def get_version(self):
        return {"version": updater.get_version(),
                "changelog": updater.get_changelog()}

    def check_updates(self):
        return updater.check_updates()

    def apply_updates(self):
        return updater.apply_updates()


def _startup_housekeeping():
    """每次打开软件做的例行维护：注册话术轮换任务、清理过期二维码。"""
    try:
        scheduler.ensure_rotation()
    except Exception as exc:
        logger.warn("[定时] 轮换任务注册异常: {0}".format(exc), source="sched")
    try:
        qq.cleanup_qr_files()
    except Exception:
        pass


def main():
    # ---- 单实例锁：绑定本地端口；重复启动快速弹窗退出（避免狂点出多窗口）----
    # 放在 main() 而非模块层：API 直调/测试不会触发弹窗阻塞
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _sock.bind(("127.0.0.1", INSTANCE_PORT))
    except OSError:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "续火花控制台已经在运行啦，请看任务栏。", "续火花控制台", 0x40)
        except Exception:
            pass
        return
    logger.info("软件启动：v{0}".format(updater.get_version()), source="app")
    _startup_housekeeping()
    api = Api()
    webview.create_window(WINDOW_TITLE, str(UI_DIR / "index.html"), js_api=api,
                          width=1120, height=760, min_size=(900, 620))
    webview.start()
    logger.info("软件退出", source="app")


if __name__ == "__main__":
    main()
