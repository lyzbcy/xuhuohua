# 续火花 · 全自动 QQ/抖音火花保持器

一个软件搞定 QQ 和抖音的每日续火花：**双击打开「续火花控制台」，扫码登录，选好友，剩下全自动。**

**核心原则：0 token 消耗** —— 消息全部来自本地话术库随机抽取（文字 + 星星布丁原创表情包 + 平台原生表情），不调用任何 LLM API。

## 🚀 怎么用（就这三步）

1. 双击项目根目录的 **`启动续火花控制台.bat`**（或桌面快捷方式「续火花控制台」）
2. 「抖音」页点扫码登录（自动保存）；「QQ」页点启动 QQ 并扫码
3. 「抖音」页管理好友（支持从最近会话勾选）；「QQ」页填对方 QQ 号并**勾选「启用」**。话术库 QQ/抖音共用，每天自动随机换一条。完事，每天自动续

图文教程见 `docs/部署指南.md`（与软件界面一一对应）。

## 软件界面（software/）

| 页面 | 功能 |
|------|------|
| 仪表盘 | 抖音/QQ/定时整体状态 + 立即发送（两边） + 每日计划 + 实时动态 |
| 抖音 | 扫码登录 / 好友管理（拉取会话勾选）/ 演练 / 正式发送 |
| QQ | NapCat 启停 + 好友/群续火花的时间、目标、话术配置 |
| 话术库 | QQ 和抖音共用的文字话术与原创表情池 |
| 定时 | 每日定时任务注册/删除（默认 08:30） |
| 日志 | 软件日志 + 抖音引擎日志聚合查看 |
| 关于 | 版本/更新日志、检查更新、一键更新、捞鱼工作室 |

## 从源码运行（新机器）

1. 克隆本仓库，双击 `启动续火花控制台.bat`（首次会提示缺环境，先做第 2 步）
2. 环境准备：
   - Python 3.11+ 后执行：`cd software && python -m venv .venv && .venv\Scripts\python -m pip install pywebview`
   - 抖音引擎：`cd douyin-auto-fire && python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt && .venv\Scripts\python -m playwright install chromium`
   - NapCat：从 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 下载 `NapCat.Shell.zip` 解压到 `tools/napcat/shell/`（本仓库不含该二进制）
3. 软件里扫码登录抖音和 QQ，即可使用

## 项目组成

| 模块 | 目录 | 说明 |
|------|------|------|
| **软件本体** | `software/` | pywebview + HTML 前端控制台（Python 跨平台 Win/Mac） |
| 抖音引擎 | `douyin-auto-fire/` | 上游 [unmev/douyin-auto-fire](https://github.com/unmev/douyin-auto-fire)，Playwright 驱动 |
| QQ 引擎 | `tools/napcat/` + `napcat-plugin-auto-tasks/` | NapCat v4.18.19 Shell + 续火花插件（已构建部署） |
| 备选 | `DouYinSparkFlow/` | 抖音备胎方案 |
| 开发者工具 | `scripts/` | 早期脚本版工具（已被软件界面取代，保留给开发者） |

## 开发文档入口

- AI 开发索引（渐进式披露）：`docs/agent.md`
- 专属开发 Skill：`skills/续火花开发/SKILL.md`（已安装到 `~/.agents/skills/`）
- 待办 / 技术方案 / 开发日志：`docs/`

## 安全须知

- 登录凭证（`storage-state.json`、`.env*`、QQ 登录态）= 账号密码，**绝不入公开仓库、不外传**
- 自动化保持低频（每天 1 次）、少量好友，防平台风控
- 本项目个人自用 + 学习研究，禁止商用（上游 douyin-auto-fire 为 PolyForm Noncommercial 协议）
