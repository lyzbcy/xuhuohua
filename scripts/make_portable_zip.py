# -*- coding: utf-8 -*-
"""组装 Windows 便携分发包：
xuhuohua.exe + 抖音引擎源码 + 引导安装脚本 + 使用说明。
产出：xuhuohua-windows-x64.zip
"""
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "pkg"
EXE_DIR = ROOT / "software" / "dist" / "xuhuohua"

EXCLUDE_DIRS = {".venv", ".venv-ci", "__pycache__", ".pytest_cache", "artifacts",
                ".git", "node_modules", "build", "dist", ".idea", ".vscode"}
EXCLUDE_FILES = {"storage-state.json", "storage-state.json.tmp", "config.json", ".env"}


def copy_tree(src: Path, dst: Path):
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES or f.endswith((".pyc", ".log")):
                continue
            s = Path(root) / f
            rel = s.relative_to(src)
            d = dst / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(s.read_bytes())


def main():
    if PKG.exists():
        import shutil
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)

    # 1) 应用本体（exe + _internal）
    copy_tree(EXE_DIR, PKG)
    # 2) VERSION
    (PKG / "VERSION").write_text((ROOT / "VERSION").read_text(encoding="utf-8"))
    # 3) 抖音引擎源码（含 requirements + 表情包，不含凭证/venv）
    copy_tree(ROOT / "douyin-auto-fire", PKG / "douyin-auto-fire")
    # 4) 引导安装脚本 + 使用说明 + README
    (PKG / "scripts").mkdir()
    for name in ("引导安装-抖音引擎.bat",):
        src = ROOT / "scripts" / name
        if src.exists():
            (PKG / "scripts" / name).write_bytes(src.read_bytes())
    for name in ("README.md", "使用说明.txt"):
        src = ROOT / name
        if src.exists():
            (PKG / name).write_bytes(src.read_bytes())

    # 5) 打 zip
    out = ROOT / "xuhuohua-windows-x64.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(PKG):
            for f in files:
                fp = Path(root) / f
                z.write(fp, Path('续火花控制台') / fp.relative_to(PKG))
    size = out.stat().st_size / 1024 / 1024
    print(f"ZIP_OK {out} {size:.1f} MB")


if __name__ == "__main__":
    main()
