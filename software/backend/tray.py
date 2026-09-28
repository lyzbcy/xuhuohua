# -*- coding: utf-8 -*-
"""Windows 托盘菜单。菜单动作在工作线程执行，不阻塞托盘消息循环。"""
import sys
import threading

from backend import logger
from backend.paths import UI_DIR


def start(window, on_douyin, on_qq, on_quit):
    if sys.platform != "win32":
        return None
    try:
        import pystray
        from PIL import Image
        artwork = Image.open(UI_DIR / "assets" / "icon.ico").convert("RGBA")
        send_lock = threading.Lock()

        def dispatch(callback, sending=False):
            def invoke(_icon, _item):
                if sending and not send_lock.acquire(blocking=False):
                    logger.warn("[托盘] 已有一键续火任务在运行，请等本轮结束", source="app")
                    return
                def worker():
                    try:
                        callback()
                    except Exception as exc:
                        logger.fail("[托盘] 操作失败: " + str(exc), source="app")
                    finally:
                        if sending:
                            send_lock.release()
                threading.Thread(target=worker, daemon=True).start()
            return invoke

        menu = pystray.Menu(
            pystray.MenuItem("打开控制台", dispatch(window.show), default=True),
            pystray.MenuItem("一键续抖音火花", dispatch(on_douyin, sending=True)),
            pystray.MenuItem("一键续 QQ 火花", dispatch(on_qq, sending=True)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出续火花控制台", dispatch(on_quit)),
        )
        icon = pystray.Icon("xuhuohua", artwork, "续火花控制台", menu)
        icon.run_detached()
        logger.info("[托盘] 已在右下角托盘运行", source="app")
        return icon
    except Exception as exc:
        logger.warn("[托盘] 启动失败: " + str(exc), source="app")
        return None
