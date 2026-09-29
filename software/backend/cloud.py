# -*- coding: utf-8 -*-
"""导出不含登录态的 Linux QQ/抖音云端部署包与可复制部署提示词。"""
import zipfile
import urllib.error
import urllib.request
from pathlib import Path

from backend.paths import PROJECT_ROOT

EXPORT_NAME = "xuhuohua-cloud.zip"
LATEST_RELEASE_ASSET = "https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip"
LATEST_PROMPT_ASSET = "https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud-prompt.txt"
PROMPT_MAX_BYTES = 12_000


def export_bundle() -> dict:
    skill = PROJECT_ROOT / "cloud-skill" / "xuhuohua-cloud"
    engine = PROJECT_ROOT / "douyin-auto-fire"
    if not all(p.is_file() for p in (skill / "SKILL.md", PROJECT_ROOT / "VERSION", engine / "run.py")):
        return {"ok": False, "msg": "云端 Skill 或抖音引擎缺失，请重新下载完整安装包"}
    destination = PROJECT_ROOT / EXPORT_NAME
    selected = [engine / name for name in
                ("run.py", "requirements.txt", "config.example.json", "README.md", "LICENSE")]
    selected.append(engine / "scripts" / "login.py")
    selected.extend((engine / "app").rglob("*.py"))
    selected.append(skill / "SKILL.md")
    selected.extend(skill / "scripts" / name for name in
                    ("install.sh", "install-qq.sh", "install-skill.sh", "compose.qq.yaml",
                     "qq-watchdog.sh", "verify-qq.sh", "qq-qr.sh",
                     "qq-login-page.sh", "qq-login-page.py",
                     "prepare-douyin.sh", "start-douyin-desktop.sh",
                     "stop-douyin-desktop.sh", "login-douyin.sh",
                     "configure-qq.py", "notify-result.py",
                     "check-update.sh", "update-skill.py",
                     "configure-onebot.py", "qq-run.py"))
    if not all(source.is_file() for source in selected):
        return {"ok": False, "msg": "云端包所需文件不完整，请重新安装"}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(PROJECT_ROOT / "VERSION", "xuhuohua-cloud/VERSION")
        for source in selected:
            if not source.is_file() or source.name.startswith(".env"):
                continue
            if source.is_relative_to(skill):
                name = Path("xuhuohua-cloud") / source.relative_to(skill)
            else:
                name = Path("douyin-auto-fire") / source.relative_to(engine)
            if source.suffix == ".sh":
                archive.writestr(str(name).replace("\\", "/"),
                                 source.read_bytes().replace(b"\r\n", b"\n"))
            else:
                archive.write(source, name)
    return {"ok": True, "path": str(destination), "files": len(selected) + 1}


def prompt() -> str:
    return f"""请在我的 Linux x86_64 云服务器部署续火花。

只从最新 Release 下载并校验：
- {LATEST_RELEASE_ASSET}
- {LATEST_RELEASE_ASSET}.sha256

校验 SHA-256 后解压到私有目录，读取并安装包内 `xuhuohua-cloud/SKILL.md`，随后严格按该 Skill 执行。已有安装应在任务空闲时原地升级，保留登录态、好友配置和 `notify-webhook`，不要创建重复 cron。每次使用先运行已安装目录的 `check-update.sh`；更新失败继续使用当前版本。

开始时一次问清：是否开启 QQ、是否开启抖音、各自北京时间 HH:MM，以及是否配置企业微信群机器人 webhook。通知是可选项；只安装已选择的平台，配置和验收阶段不要真实发送。

必须遵守：
1. QQ 首次登录默认提供 `qq-login-page.sh` 的实时二维码网页和 SSH 隧道，不反复发静态截图。持久化与重启验证后，再执行 `qq-run.py --session-check`；正式任务到点才启动 NapCat，若被顶下线则主动快速登录，发送结束或失败都自动退出并停止容器，平时不得用 watchdog 常驻 QQ。
2. 抖音首次登录默认提供 noVNC 虚拟桌面浏览器链接和 SSH 隧道，用户确认完成后立即运行 `stop-douyin-desktop.sh` 关闭临时桌面；定时任务使用无头浏览器。
3. 企业微信只使用群机器人 webhook 推送链接，可跳过；启用时私密保存并运行 `notify-result.py test`。同一天的 QQ、抖音结果合并为一条通知，列清给谁发送了什么；通知故障不改变任务结果。
4. QQ 与抖音正文都自动追加 `来自捞鱼自动续火花`。QQ 只有在发送后按 message_id、本人账号和完整正文回查聊天记录一致时才能报告成功；回查失败不自动重发。
5. 不在聊天、公开仓库、命令行参数或日志中展示 Cookie、Token、webhook key、登录态或好友配置。

完成后报告平台、时间、登录与自动退出验收、cron、通知状态和日志位置。"""


def latest_prompt() -> dict:
    """Copy the prompt published with the latest Release, not a stale desktop copy."""
    request = urllib.request.Request(LATEST_PROMPT_ASSET,
                                     headers={"User-Agent": "xuhuohua-desktop"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read(PROMPT_MAX_BYTES + 1)
        if len(payload) > PROMPT_MAX_BYTES:
            raise ValueError("Release Prompt 超过大小限制")
        value = payload.decode("utf-8-sig").strip()
        if LATEST_RELEASE_ASSET not in value or "xuhuohua-cloud.zip.sha256" not in value:
            raise ValueError("Release Prompt 缺少云端包或校验文件地址")
        return {"ok": True, "prompt": value, "source": LATEST_PROMPT_ASSET}
    except (urllib.error.URLError, OSError, UnicodeError, ValueError) as exc:
        return {"ok": False, "msg": "最新 Release 的云端 Prompt 暂不可用，请先发布含云端资产的新版本：" + str(exc)}
