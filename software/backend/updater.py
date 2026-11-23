# -*- coding: utf-8 -*-
"""版本与更新（依据 软件组件/自适应更新检测.md）：
检查 = git fetch 比对本地/远端；更新 = ff-only pull + 依赖同步；失败兜底提示重试。
"""
import json
import re
from urllib.request import Request, urlopen

from backend import logger
from backend.paths import CHANGELOG_FILE, DOUYIN_VENV_PY, UPSTREAM_REPOS, VERSION_FILE
from backend.winproc import run_cmd

RELEASE_API = "https://api.github.com/repos/lyzbcy/xuhuohua/releases/latest"
RELEASE_PAGE = "https://github.com/lyzbcy/xuhuohua/releases"


def get_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def get_changelog() -> str:
    try:
        return CHANGELOG_FILE.read_text(encoding="utf-8")[:4000]
    except OSError:
        return ""


def _git(repo, *args):
    return run_cmd(["git", "-C", str(repo)] + list(args), timeout=60)


def check_public_release():
    current = get_version()
    try:
        request = Request(RELEASE_API, headers={"User-Agent": "xuhuohua"})
        with urlopen(request, timeout=10) as response:
            release = json.loads(response.read(196608))
        tag = release.get("tag_name", "")
        if (not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or release.get("draft") or release.get("prerelease")
                or not any(a.get("name") == "xuhuohua-windows-x64.zip" for a in release.get("assets", []))):
            raise ValueError("Windows release unavailable")
        latest = tag[1:]
        return {"current": current, "latest": latest, "url": f"{RELEASE_PAGE}/tag/{tag}"}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"current": current, "latest": "", "url": f"{RELEASE_PAGE}/latest"}


def check_updates() -> dict:
    """只检查不应用。remote 拿不到时不误报"有新版本"。"""
    result = {}
    for name, path in UPSTREAM_REPOS.items():
        if not path.joinpath(".git").exists():
            continue
        _git(path, "fetch", "--quiet")
        local = _git(path, "rev-parse", "HEAD").stdout.strip()
        remote = _git(path, "rev-parse", "@{u}").stdout.strip()
        if not remote:
            remote = _git(path, "rev-parse", "origin/HEAD").stdout.strip()
        if not remote or not local:
            result[name] = {"update_available": False, "note": "无法确定远端状态"}
            continue
        result[name] = {"update_available": (local != remote)}
        if result[name]["update_available"]:
            logger.warn("[更新] {0} 有新版本".format(name), source="update")
    return {"ok": True, "repos": result,
            "hint": "国内网络建议先开代理再更新（GitHub 直连较慢）"}


def apply_updates() -> dict:
    """执行更新：ff-only pull + 抖音依赖同步。个人配置在 .gitignore 内不受影响。"""
    failed = []
    for name, path in UPSTREAM_REPOS.items():
        if not path.joinpath(".git").exists():
            continue
        r = _git(path, "pull", "--ff-only", "--quiet")
        if r.returncode != 0:
            failed.append(name)
            logger.fail("[更新] {0} 更新失败（可稍后重试）: {1}".format(
                name, (r.stderr or r.stdout).strip()[:150]), source="update")
        else:
            logger.ok("[更新] {0} 已更新".format(name), source="update")
    if DOUYIN_VENV_PY.exists():
        req = UPSTREAM_REPOS["douyin-auto-fire"] / "requirements.txt"
        r = run_cmd([str(DOUYIN_VENV_PY), "-m", "pip", "install", "-q", "-r", str(req)],
                    timeout=300)
        if r.returncode == 0:
            logger.ok("[更新] 抖音侧依赖已同步", source="update")
        else:
            logger.fail("[更新] 抖音依赖同步失败（不影响当前使用）: {0}".format((r.stderr or "")[:120]), source="update")
    return {"ok": len(failed) == 0, "failed": failed,
            "msg": "全部更新完成" if not failed else "部分仓库更新失败：{0}，不影响现有使用，可重试".format("、".join(failed))}
