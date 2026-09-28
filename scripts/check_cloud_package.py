"""Offline gate for the public cloud release asset; never print credentials."""

import hashlib
import sys
import zipfile
from pathlib import Path


REQUIRED = {
    "xuhuohua-cloud/SKILL.md",
    "xuhuohua-cloud/scripts/install-skill.sh",
    "xuhuohua-cloud/scripts/install-qq.sh",
    "xuhuohua-cloud/scripts/qq-qr.sh",
    "xuhuohua-cloud/scripts/configure-qq.py",
    "xuhuohua-cloud/scripts/notify-result.py",
    "xuhuohua-cloud/scripts/prepare-douyin.sh",
    "xuhuohua-cloud/scripts/start-douyin-desktop.sh",
    "xuhuohua-cloud/scripts/login-douyin.sh",
    "xuhuohua-cloud/scripts/stop-douyin-desktop.sh",
    "douyin-auto-fire/scripts/login.py",
    "douyin-auto-fire/run.py",
    "qq-plugin/index.mjs",
    "qq-plugin/package.json",
    "qq-plugin/LICENSE",
    "qq-plugin/webui/index.html",
}


def check(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("云端 ZIP CRC 校验失败")
        names = set(archive.namelist())
        missing = REQUIRED - names
        if missing:
            raise SystemExit("云端包缺文件: " + ", ".join(sorted(missing)))
        for name in names:
            parts = name.lower().split("/")
            basename = parts[-1]
            if ("qq-data" in parts or "artifacts" in parts or "storage_state" in parts
                    or basename.startswith("storage-state") or basename.startswith(".env")
                    or basename in {"config.json", "accounts.json", "settings.json",
                                    "notify-command", "notify-state.json"}):
                raise SystemExit("云端包含私有文件")
            if name.endswith(".sh") and b"\r\n" in archive.read(name):
                raise SystemExit("Linux shell 脚本含 CRLF: " + name)
    checksum_path = path.with_name(path.name + ".sha256")
    expected = checksum_path.read_text(encoding="ascii").split()[0]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected != actual:
        raise SystemExit("云端 ZIP SHA-256 不匹配")
    prompt_file = path.with_name("xuhuohua-cloud-prompt.txt")
    deployment_prompt = prompt_file.read_text(encoding="utf-8")
    if ("https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip"
            not in deployment_prompt or "xuhuohua-cloud.zip.sha256" not in deployment_prompt
            or "是否开启 QQ" not in deployment_prompt or "是否开启抖音" not in deployment_prompt
            or "企业微信长连接机器人" not in deployment_prompt):
        raise SystemExit("Release Prompt 缺少下载或引导步骤")
    print(f"CLOUD_PACKAGE_OK files={len(names)} sha256={actual}")


if __name__ == "__main__":
    check(Path(sys.argv[1] if len(sys.argv) > 1 else "xuhuohua-cloud.zip"))
