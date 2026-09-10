# -*- coding: utf-8 -*-
"""引擎自动安装器：exe 内一键初始化，缺什么自动下载什么（用户要求：不要 bat，exe 自修复）。
步骤：嵌入式 Python → pip → 抖音依赖 → 浏览器组件 → NapCat(QQ引擎) → 插件
全部国内镜像优先、官方源兜底；进度走事件总线（UI 实时可见），也支持 exe --setup 命令行模式。
"""
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

from backend import logger
from backend.paths import (DOUYIN_DIR, DOUYIN_RUNTIME_PY, NAPCAT_DIR,
                           PROJECT_ROOT)
from backend.winproc import run_cmd

PY_ZIP_MIRRORS = [
    "https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip",
    "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
]
PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
NAPCAT_ZIPS = [
    "https://gh-proxy.com/https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.19/NapCat.Shell.zip",
    "https://ghproxy.net/https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.19/NapCat.Shell.zip",
    "https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.19/NapCat.Shell.zip",
]
NAPCAT_VER = "4.18.19"

STATE = {"running": False, "step": "", "error": "", "done": True}


def _download(url: str, dest: Path, timeout: int = 120, min_bytes: int = 0) -> bool:
    """下载并校验：zip 必须真是 zip（防代理返回 HTML 门槛页冒充文件）。"""
    import zipfile as _zf
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=timeout) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        if dest.stat().st_size < max(min_bytes, 1024):
            return False
        if dest.suffix == ".zip" and not _zf.is_zipfile(dest):
            return False
        return True
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _download_any(urls: list, dest: Path, timeout: int = 180, min_bytes: int = 0) -> bool:
    for u in urls:
        if _download(u, dest, timeout, min_bytes):
            return True
    return False


def _step(msg: str):
    STATE["step"] = msg
    logger.info("[初始化] " + msg, source="setup")


def ensure_runtime() -> bool:
    if DOUYIN_RUNTIME_PY.exists():
        return True
    _step("1/5 下载嵌入式 Python（约 11MB）…")
    tmp = PROJECT_ROOT / "runtime_tmp"
    z = tmp / "py.zip"
    if not _download_any(PY_ZIP_MIRRORS, z, min_bytes=5 * 1024 * 1024):
        STATE["error"] = "Python 下载失败：请检查网络（或开代理）后重试"
        return False
    runtime = PROJECT_ROOT / "runtime"
    with zipfile.ZipFile(z) as zf:
        zf.extractall(runtime)
    pth = runtime / "python312._pth"
    lines = pth.read_text(encoding="utf-8").splitlines() + ["import site"]
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def ensure_deps() -> bool:
    deps = DOUYIN_DIR / "deps"
    req = DOUYIN_DIR / "requirements.txt"
    if (deps / "playwright").exists():
        _ensure_pth_deps()
        return True
    _step("2/5 准备 pip…")
    tmp = PROJECT_ROOT / "runtime_tmp"
    r = run_cmd([str(DOUYIN_RUNTIME_PY), "-m", "pip", "--version"], timeout=30)
    if r.returncode != 0:
        gp = tmp / "get-pip.py"
        if not _download_any([GET_PIP], gp):
            STATE["error"] = "get-pip 下载失败，请检查网络后重试"
            return False
        run_cmd([str(DOUYIN_RUNTIME_PY), str(gp), "-q", "--no-warn-script-location",
                 "-i", PIP_INDEX], timeout=300)
    _step("3/5 安装抖音引擎依赖（约 40MB）…")
    if not req.exists():
        STATE["error"] = "douyin-auto-fire 源码缺失（安装包不完整）"
        return False
    ok = run_cmd([str(DOUYIN_RUNTIME_PY), "-m", "pip", "install", "-q",
                  "--no-warn-script-location", "--target", str(deps),
                  "-r", str(req), "-i", PIP_INDEX], timeout=900).returncode == 0
    if not ok:  # 官方源兜底
        ok = run_cmd([str(DOUYIN_RUNTIME_PY), "-m", "pip", "install", "-q",
                      "--no-warn-script-location", "--target", str(deps),
                      "-r", str(req)], timeout=900).returncode == 0
    if not ok:
        STATE["error"] = "依赖安装失败：请检查网络后重试"
        return False
    _ensure_pth_deps()
    return True


def _ensure_pth_deps():
    pth = DOUYIN_RUNTIME_PY.parent / "python312._pth"
    if not pth.exists():
        return
    deps = DOUYIN_DIR / "deps"
    if not deps.exists():
        return
    lines = pth.read_text(encoding="utf-8", errors="replace").splitlines()
    rel = os.path.relpath(deps, DOUYIN_RUNTIME_PY.parent)
    if not any("deps" in ln for ln in lines):
        pth.write_text("\n".join(lines + [rel]) + "\n", encoding="utf-8")


def ensure_chromium() -> bool:
    marker = DOUYIN_DIR / "deps" / ".chromium_done"
    if marker.exists():
        return True
    _step("4/5 下载浏览器组件（约 300MB，最耗时，可先去忙别的）…")
    env = dict(os.environ)
    env["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright/"
    r = run_cmd([str(DOUYIN_RUNTIME_PY), "-m", "playwright", "install", "chromium"],
                timeout=1800, env=env)
    if r.returncode != 0:
        env.pop("PLAYWRIGHT_DOWNLOAD_HOST", None)
        r = run_cmd([str(DOUYIN_RUNTIME_PY), "-m", "playwright", "install", "chromium"],
                    timeout=1800, env=env)
    if r.returncode != 0:
        STATE["error"] = "浏览器组件下载失败：请检查网络后重试"
        return False
    marker.write_text("ok", encoding="utf-8")
    return True


def ensure_napcat() -> bool:
    if (NAPCAT_DIR / "launcher.bat").exists():
        return True
    _step("5/5 下载 QQ 引擎 NapCat（约 26MB）…")
    tmp = PROJECT_ROOT / "runtime_tmp"
    z = tmp / "napcat.zip"
    if not _download_any(NAPCAT_ZIPS, z, timeout=600, min_bytes=10 * 1024 * 1024):
        STATE["error"] = "NapCat 下载失败：请检查网络（或开代理）后重试"
        return False
    NAPCAT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(NAPCAT_DIR)
    logger.ok("[初始化] NapCat v{0} 就位".format(NAPCAT_VER), source="setup")
    return True


def run_install() -> dict:
    """串行执行全部步骤；单步失败即停并回报。"""
    if STATE["running"]:
        return {"started": False, "msg": "初始化正在进行中"}
    STATE.update(running=True, error="", done=False)
    try:
        for fn in (ensure_runtime, ensure_deps, ensure_chromium, ensure_napcat):
            if not fn():
                logger.fail("[初始化] 失败：" + STATE["error"], source="setup")
                return {"ok": False, "error": STATE["error"]}
        STATE["done"] = True
        logger.ok("[初始化] 全部完成！可以扫码登录开始使用了", source="setup")
        return {"ok": True}
    finally:
        STATE["running"] = False
        shutil.rmtree(PROJECT_ROOT / "runtime_tmp", ignore_errors=True)


def start_async() -> dict:
    """UI 触发：后台线程跑安装，进度走事件总线。"""
    if STATE["running"]:
        return {"started": False, "msg": "初始化正在进行中，看下方进度"}
    threading.Thread(target=run_install, daemon=True).start()
    return {"started": True, "msg": "初始化已开始（全自动，可最小化窗口等它完成）"}


def status() -> dict:
    missing = []
    if not DOUYIN_RUNTIME_PY.exists():
        missing.append("runtime")
    if not (DOUYIN_DIR / "deps" / "playwright").exists():
        missing.append("deps")
    if not (DOUYIN_DIR / "deps" / ".chromium_done").exists():
        missing.append("chromium")
    if not (NAPCAT_DIR / "launcher.bat").exists():
        missing.append("napcat")
    return dict(STATE, missing=missing)
