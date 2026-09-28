# -*- coding: utf-8 -*-
"""导出不含登录态的 Linux QQ/抖音云端部署包与可复制部署提示词。"""
import zipfile
import urllib.error
import urllib.request
from pathlib import Path

from backend.paths import BUNDLE_DIR, PROJECT_ROOT

EXPORT_NAME = "xuhuohua-cloud.zip"
LATEST_RELEASE_ASSET = "https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip"
LATEST_PROMPT_ASSET = "https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud-prompt.txt"


def export_bundle() -> dict:
    skill = PROJECT_ROOT / "cloud-skill" / "xuhuohua-cloud"
    engine = PROJECT_ROOT / "douyin-auto-fire"
    plugin = PROJECT_ROOT / "napcat-plugin-auto-tasks" / "dist"
    if not (plugin / "index.mjs").is_file():
        plugin = BUNDLE_DIR / "backend" / "assets" / "auto-tasks"
    if not all(p.is_file() for p in (skill / "SKILL.md", engine / "run.py",
                                      plugin / "index.mjs", plugin / "package.json",
                                      plugin / "LICENSE")):
        return {"ok": False, "msg": "云端 Skill、抖音引擎或 QQ 插件缺失，请重新下载完整安装包"}
    destination = PROJECT_ROOT / EXPORT_NAME
    selected = [engine / name for name in
                ("run.py", "requirements.txt", "config.example.json", "README.md", "LICENSE")]
    selected.append(engine / "scripts" / "login.py")
    selected.extend((engine / "app").rglob("*.py"))
    selected.append(skill / "SKILL.md")
    selected.extend(skill / "scripts" / name for name in
                    ("install.sh", "install-qq.sh", "install-skill.sh", "compose.qq.yaml",
                     "qq-watchdog.sh", "verify-qq.sh", "qq-qr.sh",
                     "prepare-douyin.sh", "start-douyin-desktop.sh",
                     "stop-douyin-desktop.sh", "login-douyin.sh",
                     "configure-qq.py", "notify-result.py"))
    selected.extend(plugin / name for name in ("index.mjs", "package.json", "LICENSE"))
    selected.extend((plugin / "webui").rglob("*"))
    if not all(source.is_file() for source in selected):
        return {"ok": False, "msg": "云端包所需文件不完整，请重新安装"}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in selected:
            if not source.is_file() or source.name.startswith(".env"):
                continue
            if source.is_relative_to(skill):
                name = Path("xuhuohua-cloud") / source.relative_to(skill)
            elif source.is_relative_to(plugin):
                name = Path("qq-plugin") / source.relative_to(plugin)
            else:
                name = Path("douyin-auto-fire") / source.relative_to(engine)
            if source.suffix == ".sh":
                archive.writestr(str(name).replace("\\", "/"),
                                 source.read_bytes().replace(b"\r\n", b"\n"))
            else:
                archive.write(source, name)
    return {"ok": True, "path": str(destination), "files": len(selected)}


def prompt() -> str:
    return f"""请在我的 Linux 云服务器上部署续火花。发布源是项目最新 GitHub Release：
{LATEST_RELEASE_ASSET}
校验文件：{LATEST_RELEASE_ASSET}.sha256
同时下载校验文件，验证 SHA-256 后解压到私有目录。只使用这两个 Release 资产；若最新 Release 尚未提供，请告知我，不要改用源码或旧包。读取包内 xuhuohua-cloud/SKILL.md，并按你这个 Agent 的 Skill 安装约定安装该目录；如果本轮无法热加载，先读取 Skill 继续执行。

先问我是否开启 QQ 自动续火花、是否开启抖音自动续火花，以及每个启用平台的北京时间 HH:MM。只安装我选的平台，再逐步引导我配置好友和本地话术。部署时请主动建议我配置企业微信长连接机器人，询问是否启用每日结果通知；这是可选项，跳过也要继续部署。

QQ：启动 NapCat 后运行包内 qq-qr.sh 获取最新二维码 PNG，在当前私聊中直接把图片发给我扫码；不要发送过期码。如果你不能发送图片，引导我通过 SSH 隧道进入仅监听 127.0.0.1 的 WebUI 扫码。确认账号登录后才启用好友任务，核对目标和发送时间。QQ 由插件定时发送，cron 只检查容器，不另建发送任务。

抖音：准备 Playwright 与 Xvfb/x11vnc 虚拟桌面。给我 SSH 隧道和 VNC 连接步骤，让我直接操作可见浏览器扫码，并在可能出现的人脸验证中自行完成。登录态只留在服务器。先做 --dry-run，确认通过后再注册每日无头运行。

企业微信通知：如果我选择启用，先按你这个云端 Agent 官方支持的方式连接企业微信长连接机器人，私下设置接收会话并发一条测试消息。再创建私有可执行适配命令：从标准输入读取一条 UTF-8 文本，通过该长连接通道发送给我，成功退出 0，失败返回非 0。把适配命令的绝对路径单独写入解压目录的 xuhuohua-cloud/notify-command 并 chmod 600，运行 python3 xuhuohua-cloud/scripts/notify-result.py test 验证。QQ 整批结束后和抖音每日运行退出后，无论成功还是失败，都各发送一条结果；通知失败写入日志，不改变续火花本身结果。不要把长连接机器人误写成群 Webhook，也不要在公开文件里存放凭证。如果我暂不配置，保持 notify-command 不存在，QQ/抖音定时任务照常运行。

不要在聊天、公开仓库或日志中贴出 Cookie、Token、登录态或好友配置文件。不要在配置与演练阶段真实发送；完成后报告两个平台的启用状态、时间、登录验证、定时任务、企业微信通知是否启用和日志位置。"""


def latest_prompt() -> dict:
    """Copy the prompt published with the latest Release, not a stale desktop copy."""
    request = urllib.request.Request(LATEST_PROMPT_ASSET,
                                     headers={"User-Agent": "xuhuohua-desktop"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read(50_001)
        if len(payload) > 50_000:
            raise ValueError("Release Prompt 超过大小限制")
        value = payload.decode("utf-8-sig").strip()
        if LATEST_RELEASE_ASSET not in value or "xuhuohua-cloud.zip.sha256" not in value:
            raise ValueError("Release Prompt 缺少云端包或校验文件地址")
        return {"ok": True, "prompt": value, "source": LATEST_PROMPT_ASSET}
    except (urllib.error.URLError, OSError, UnicodeError, ValueError) as exc:
        return {"ok": False, "msg": "最新 Release 的云端 Prompt 暂不可用，请先发布含云端资产的新版本：" + str(exc)}
