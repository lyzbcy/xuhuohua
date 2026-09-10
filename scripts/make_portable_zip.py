# -*- coding: utf-8 -*-
"""组装 Windows 便携分发包（小白版）：
xuhuohua.exe + ①一键安装引擎.bat + NapCat(QQ引擎) + 抖音引擎源码 + 使用说明。
产出：xuhuohua-windows-x64.zip（顶层目录：续火花控制台/）
"""
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "pkg"
OUT = ROOT / "xuhuohua-windows-x64.zip"

EXCLUDE_DIR_NAMES = {".venv", ".venv-ci", "__pycache__", ".pytest_cache",
                     "artifacts", ".git", "build", "dist",
                     ".idea", ".vscode", "config", "cache", "logs"}
# 注：node_modules 不排除——NapCat shell 自带的 Node 运行时依赖必须随包
EXCLUDE_FILE_SUFFIX = (".pyc", ".log", ".tmp")   # 注意：不能排除 .zip——PyInstaller 的 base_library.zip 必须随包


def copy_filtered(src: Path, dst: Path, extra_exclude_files: set = frozenset()):
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
        for f in files:
            if f.endswith(EXCLUDE_FILE_SUFFIX) or f in extra_exclude_files:
                continue
            s = Path(root) / f
            d = dst / s.relative_to(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            n += 1
    return n


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)

    # 1) 应用本体（PyInstaller 产物，原样全量）
    n1 = copy_filtered(ROOT / "software" / "dist" / "xuhuohua", PKG)
    # NapCat 与插件不再随包：exe「一键初始化」自动下载/释放（zip 瘦身 26MB）
    n2 = 0
    # 4) 抖音引擎源码（不含凭证/venv/产物）
    n3 = copy_filtered(ROOT / "douyin-auto-fire", PKG / "douyin-auto-fire",
                       extra_exclude_files={"storage-state.json", "config.json", ".env"})
    # 5) 说明 / 版本（安装脚本已退役：初始化内置于 exe）
    n2b = 0
    shutil.copy2(ROOT / "使用说明.txt", PKG / "使用说明.txt")
    shutil.copy2(ROOT / "README.md", PKG / "README.md")
    shutil.copy2(ROOT / "VERSION", PKG / "VERSION")

    # 打包（arcname 以 续火花控制台/ 开头）
    if OUT.exists():
        OUT.unlink()
    total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(PKG):
            for f in sorted(files):
                fp = Path(root) / f
                z.write(fp, Path("续火花控制台") / fp.relative_to(PKG))
                total += 1
    print(f"ZIP_OK {OUT.name} {OUT.stat().st_size/1048576:.1f} MB "
          f"app={n1} napcat={n2} douyin={n3} total={total}")


if __name__ == "__main__":
    main()
