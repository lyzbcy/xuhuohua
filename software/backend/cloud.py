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
    return f"""请在我的 Linux 云服务器上部署续火花。发布源是项目最新 GitHub Release：
{LATEST_RELEASE_ASSET}
校验文件：{LATEST_RELEASE_ASSET}.sha256
同时下载校验文件，验证 SHA-256 后解压到私有目录。只使用这两个 Release 资产；若最新 Release 尚未提供，请告知我，不要改用源码或旧包。若服务器已安装旧版，在任务空闲时把校验后的公共文件更新到原解压目录，保留 QQ/抖音登录态、好友配置及 webhook 私有文件，不另建第二套 cron。读取包内 xuhuohua-cloud/SKILL.md，并按你这个 Agent 的 Skill 安装约定安装该目录；如果本轮无法热加载，先读取 Skill 继续执行。安装后每次使用 Skill 时先运行已安装目录的 check-update.sh：每天北京时间首次使用会在后台静默检查并更新 Skill，失败继续使用旧版，不打断本次工作。

先问我是否开启 QQ 自动续火花、是否开启抖音自动续火花，以及每个启用平台的北京时间 HH:MM。只安装我选的平台，再逐步引导我配置好友和本地话术。部署时请主动建议我配置企业微信群机器人 webhook 推送链接，询问是否启用每日结果通知；这是可选项，跳过也要继续部署。如果我已给过链接，直接从私有上下文使用，不要再索取或复述。

QQ：启动 NapCat 后运行 qq-login-page.sh start，默认给我可在浏览器打开的 QQ 实时二维码页面链接及 SSH 隧道命令；页面自动读取新二维码，不要反复发静态截图，也不要公开暴露端口。安装器会固定容器 MAC 与主机名。扫码授权后，检查 qq-data/QQ 持久化目录和 Docker 挂载，运行 configure-onebot.py 配置仅供容器网络访问的带令牌 OneBot HTTP 接口，重启容器，再运行 verify-qq.sh 确认同一账号仍已登录；若重启后要求重新扫码，先排查设备标识、数据卷、同账号桌面 QQ 顶号或账号风控，不能声称部署成功。确认后关闭临时 QQ 页面、配置好友任务并核对目标和发送时间。当前 NapCat 镜像不加载第三方定时插件，QQ 由 crontab 每分钟核对设定时间并在到点时通过 OneBot 发送；登录确认前不可声称自动续火花就绪。

抖音：准备 Playwright 与 Xvfb/x11vnc/noVNC 虚拟桌面。默认给我浏览器可打开的 noVNC 链接和 SSH 隧道命令，使用仅监听服务器本机的 6089 端口；先检查现有 nginx /vnc/ 是否把旧 6080 端口公开反代，不能沿用无密码的公网链接。让我直接操作可见浏览器扫码，并在可能出现的人脸验证中自行完成；不要默认要求安装 VNC 客户端。等我明确确认登录结束后，保存服务器私有登录态，运行 stop-douyin-desktop.sh 关闭 noVNC、VNC 和本次虚拟桌面，再做 --dry-run，确认通过后注册每日无头运行。

企业微信通知：如果我选择启用，把企业微信群机器人 webhook 链接私密保存到解压目录的 xuhuohua-cloud/notify-webhook，权限设为 600，运行 python3 xuhuohua-cloud/scripts/notify-result.py test 确认目标群收到测试消息。QQ 整批结束后和抖音每日运行退出后，无论成功还是失败，都各发送一条结果；通知失败写入日志，不改变续火花本身结果。不要要求长连接机器人，不要在公开文件、命令行参数或日志中暴露 webhook 的 key。如果我暂不配置，保持 notify-webhook 不存在，QQ/抖音定时任务照常运行。

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
