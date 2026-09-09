# -*- coding: utf-8 -*-
"""路径常量：一切路径从本文件位置推导，软件整体可任意搬迁。
PyInstaller 打包（frozen）时：
  - exe 放在项目根目录（和 douyin-auto-fire/ 等文件夹平级）
  - UI 等只读资源从解包目录 sys._MEIPASS 取
"""
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    SOFTWARE_DIR = Path(sys.executable).resolve().parent      # exe 所在目录（项目根）
    UI_DIR = Path(getattr(sys, "_MEIPASS", SOFTWARE_DIR)) / "ui"
else:
    SOFTWARE_DIR = Path(__file__).resolve().parents[1]        # software/
    UI_DIR = SOFTWARE_DIR / "ui"

PROJECT_ROOT = SOFTWARE_DIR                                   # 续火花/
DOUYIN_DIR = PROJECT_ROOT / "douyin-auto-fire"
DOUYIN_VENV_PY = DOUYIN_DIR / ".venv" / "Scripts" / "python.exe"
DOUYIN_CONFIG = DOUYIN_DIR / "config.json"
DOUYIN_STATE = DOUYIN_DIR / "storage-state.json"
DOUYIN_ENV = DOUYIN_DIR / ".env"
DOUYIN_STICKERS = DOUYIN_DIR / "stickers-lb"
DOUYIN_RUNLOG = DOUYIN_DIR / "artifacts" / "run.log"
DOUYIN_LOCK = DOUYIN_DIR / "artifacts" / "run.lock"
NAPCAT_DIR = PROJECT_ROOT / "tools" / "napcat" / "shell"
NAPCAT_CONFIG_DIR = NAPCAT_DIR / "config"
NAPCAT_LAUNCHER = NAPCAT_DIR / "launcher.bat"
NAPCAT_LAUNCHER_WIN10 = NAPCAT_DIR / "launcher-win10.bat"
# NapCat 插件真实约定（napcat.mjs getPluginConfigPath）：
#   config/plugins/<插件id>/config.json，id 取插件 package.json 的 name
PLUGIN_ID = "napcat-plugin-auto-tasks"
PLUGIN_DIR = NAPCAT_DIR / "plugins" / PLUGIN_ID
PLUGIN_DIST = PROJECT_ROOT / "napcat-plugin-auto-tasks" / "dist"
PLUGIN_CONFIG_PATH = NAPCAT_CONFIG_DIR / "plugins" / PLUGIN_ID / "config.json"
PLUGIN_ENABLE_FILE = NAPCAT_CONFIG_DIR / "plugins.json"   # {"<id>": true} 才会被加载
LEGACY_PLUGIN_CONFIG = NAPCAT_CONFIG_DIR / "napcat-plugin-auto-tasks.json"
PLUGIN_REGISTRY = PROJECT_ROOT / "napcat-plugin-auto-tasks" / "package.json"
LOG_DIR = PROJECT_ROOT / "logs"
VERSION_FILE = PROJECT_ROOT / "VERSION"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
UI_STICKER_DIR = UI_DIR / "assets" / "stickers"

# 出厂配置里的占位好友名前缀：出现即为"还没配置真实好友"
PLACEHOLDER_PREFIX = "在这里填好友昵称"

UPSTREAM_REPOS = {
    "douyin-auto-fire": DOUYIN_DIR,
    "napcat-plugin-auto-tasks": PROJECT_ROOT / "napcat-plugin-auto-tasks",
    "DouYinSparkFlow": PROJECT_ROOT / "DouYinSparkFlow",
}

for _d in (LOG_DIR, UI_STICKER_DIR):
    _d.mkdir(parents=True, exist_ok=True)
