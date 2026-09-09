---
name: 续火花开发
description: 全自动 QQ/抖音续火花项目的专属开发 Skill。当用户要开发、修改、排障、更新"续火花"项目（续火花控制台、火花保持、douyin-auto-fire、NapCat 插件、话术库、定时任务相关）时使用。项目根目录：E:\共享\创业\续火花
---

# 续火花项目开发 Skill

一个桌面软件「续火花控制台」统一管理 QQ/抖音每日续火花。**0 token**：话术全部来自本地话术库随机抽取，禁止引入任何 LLM API。

## 接管开发时的动作顺序

1. **先读** `E:\共享\创业\续火花\docs\agent.md`（索引，按需去读 reference 文档，别一次全读）
2. 看 `docs/TODO.md` 了解进度，`docs/开发日志.md` 了解最近改动
3. 动手前确认改动属于哪层：
   - 界面/交互 → `software/ui/`（HTML/CSS/JS）
   - 后端逻辑 → `software/backend/`（Python，pywebview js_api 桥接）
   - 话术/好友/时间 → 纯配置（软件界面改，或直接改 `douyin-auto-fire/config.json`、`tools/napcat/shell/config/napcat-plugin-auto-tasks.json`）
   - 上游源码 → 谨慎！先读 `docs/reference/上游项目.md` 的更新策略

## 硬性规则

1. **版本号**：开发完成必须更新根目录 `VERSION` + `CHANGELOG.md`
2. **凭证红线**：`storage-state.json`、`.env*`、`config.json`、`storage_state/`、`artifacts/` 绝不外传/入公开仓库
3. **0 token**：禁止调用 LLM API；话术只能来自本地话术库与表情包
4. **低频原则**：每日 1 次、少量好友，防平台风控
5. **日志规范**：后端一律走 `backend/logger.py`（info/ok/warn/fail），输出自动进底部状态栏+仪表盘+落盘
6. **Windows 编码**：所有子进程输出必须走 `backend/winproc.py` 的 `run_cmd`/`decode_bytes`（GBK/UTF-8 双保险）；PowerShell 脚本必须带 UTF-8 BOM
7. **跨平台**：新增功能保持 Python/HTML 技术栈（Win/Mac 兼容），Windows 专属调用集中隔离

## 软件架构速览（software/）

```
software/
├── main.py              # pywebview 入口 + Api 桥接类（前端调 pywebview.api.*）
├── backend/
│   ├── paths.py         # 所有路径常量（从 __file__ 推导，项目可整体搬迁）
│   ├── logger.py        # 事件总线日志（UI状态栏/仪表盘/落盘三路）
│   ├── winproc.py       # 子进程编码安全工具
│   ├── douyin.py        # 抖音引擎：登录子进程/运行/配置IO
│   ├── login_gui.py     # 界面内扫码登录器（轮询 sessionid 自动保存，无 input()）
│   ├── qq.py            # NapCat 启停/插件配置IO（真实路径 config/plugins/<id>/config.json + plugins.json 启用项）
│   ├── scheduler.py     # schtasks 定时任务管理
│   ├── updater.py       # 版本/更新检查/一键更新
│   └── daily_douyin.ps1 # 每日定时任务入口（计划任务指向这里）
└── ui/                  # index.html + style.css + app.js（七页面单页应用）
```

## 常用命令

```powershell
# 启动软件（或双击根目录 启动续火花控制台.bat / 桌面快捷方式）
cd E:\共享\创业\续火花\software; .\.venv\Scripts\python.exe main.py
# 无界面直调后端 API（开发自测）
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from main import Api; print(Api().get_state())"
# 重建 QQ 插件（改了 napcat-plugin-auto-tasks 源码后）
cd ..\napcat-plugin-auto-tasks; npm run build   # 产物 dist/ 会被软件在启动QQ时自动同步部署
```

## 排障入口

软件打不开 → `logs/日期-software.log`；WebView2 缺失时装 Edge/WebView2 Runtime
抖音找不到好友/发送失败 → `docs/reference/抖音侧.md#常见排障`
QQ 到点没发/插件问题 → `docs/reference/QQ侧.md#常见排障`
计划任务没跑 → 任务计划程序看「续火花-抖音」上次结果（3=未登录，0=成功）
