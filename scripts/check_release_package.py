"""对最终 Windows 便携包做离线发布门禁，不读取或输出任何凭证。"""

import sys
import zipfile
from pathlib import Path


def check(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        names = [item.filename.replace("\\", "/") for item in archive.infolist()]
        if archive.testzip() is not None:
            raise SystemExit("ZIP CRC 校验失败")

        required = (
            "/xuhuohua.exe",
            "/VERSION",
            "/README.md",
            "/使用说明.txt",
            "/_internal/ui/index.html",
            "/_internal/backend/login_gui.py",
            "/_internal/backend/fetch_friends.py",
            "/_internal/backend/daily_douyin.ps1",
            "/_internal/backend/assets/auto-tasks/index.mjs",
            "/_internal/backend/assets/auto-tasks/package.json",
            "/_internal/backend/assets/auto-tasks/LICENSE",
            "/_internal/backend/assets/auto-tasks/webui/index.html",
            "/douyin-auto-fire/run.py",
            "/cloud-skill/xuhuohua-cloud/SKILL.md",
            "/cloud-skill/xuhuohua-cloud/scripts/check-update.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/update-skill.py",
            "/cloud-skill/xuhuohua-cloud/scripts/install.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/install-qq.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/install-skill.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/compose.qq.yaml",
            "/cloud-skill/xuhuohua-cloud/scripts/qq-watchdog.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/verify-qq.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/qq-qr.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/prepare-douyin.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/start-douyin-desktop.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/login-douyin.sh",
            "/cloud-skill/xuhuohua-cloud/scripts/notify-result.py",
        )
        missing = [suffix for suffix in required if not any(n.endswith(suffix) for n in names)]
        if missing:
            raise SystemExit("安装包缺少组件: " + ", ".join(missing))

        forbidden = []
        for name in names:
            parts = [part.lower() for part in name.split("/")]
            basename = parts[-1]
            if (basename.startswith(".env") or basename.startswith("storage-state")
                    or basename in {"settings.json", "accounts.json",
                                    "notify-command", "notify-webhook", "notify-state.json",
                                    ".last-update-check", ".update.log", ".update.lock"}
                    or "storage_state" in parts or "artifacts" in parts
                    or "qq-data" in parts):
                forbidden.append(name)
        if forbidden:
            raise SystemExit("安装包包含敏感数据文件: " + str(len(forbidden)))

        version_name = next(n for n in names if n.endswith("/VERSION"))
        guide_name = next(n for n in names if n.endswith("/使用说明.txt"))
        if len(archive.read(guide_name).strip()) < 100:
            raise SystemExit("安装包使用说明为空或内容不完整")
        plugin_name = next(n for n in names if n.endswith("/assets/auto-tasks/index.mjs"))
        plugin = archive.read(plugin_name)
        if b"friendSparkCompletedAt" not in plugin or b"friendSparkFailed" not in plugin:
            raise SystemExit("QQ 插件不是当前批次结果标记版本")
        packaged_version = archive.read(version_name).decode("utf-8").strip()
        expected = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
        if packaged_version != expected:
            raise SystemExit(f"版本不一致: 安装包 {packaged_version} / 仓库 {expected}")
        print(f"RELEASE_PACKAGE_OK version={packaged_version} files={len(names)}")


if __name__ == "__main__":
    check(Path(sys.argv[1] if len(sys.argv) > 1 else "xuhuohua-windows-x64.zip"))
