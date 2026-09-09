# agent.md — AI 开发索引（渐进式披露入口）

> 任何 Agent 接管本项目开发时，**先读这个文件**，再按需深入 reference/，避免浪费上下文。

## 项目一句话

全自动 QQ/抖音续火花：每天定时从本地话术库随机抽一条消息发给指定好友，**0 token**（不调用任何 LLM）。

## 目录地图（按需读取，不要一次全读）

| 想做什么 | 去读哪里 |
|---------|---------|
| 了解技术选型与架构 | `docs/技术方案.md` |
| 部署 / 配置 / 排障 | `docs/部署指南.md` |
| 改软件界面/交互 | `software/ui/`（index.html + app.js，七页面单页应用） |
| 改软件后端逻辑 | `software/backend/` → 先读 `docs/reference/软件层.md` |
| 改抖音侧行为 | `docs/reference/抖音侧.md` → 上游源码 `douyin-auto-fire/app/` |
| 改 QQ 侧行为 | `docs/reference/QQ侧.md` → 上游源码 `napcat-plugin-auto-tasks/src/` |
| 了解三个上游项目的边界 | `docs/reference/上游项目.md` |
| 了解开发规范如何落实 | `docs/reference/开发规范落实.md` |
| 看待办 / 开发历史 | `docs/TODO.md`、`docs/开发日志.md` |

## 硬性规则（违反 = 事故）

1. **版本号**：每次开发完成，更新根目录 `VERSION`（语义化），并在 `CHANGELOG.md` 追加条目。
2. **凭证安全**：`storage-state.json`、`.env*`、`config.json`、`config/accounts.json`、`storage_state/`、`artifacts/` 一律不得提交到公开仓库或外传。
3. **0 token 原则**：话术只能来自本地话术库/表情包，禁止引入任何 LLM API 调用。
4. **上游更新**：改上游仓库的代码前先想清楚——我们的定制尽量放在软件层（software/）和配置层，少改上游源码，否则 `git pull` 会冲突。`scripts/` 是退役的开发者工具，不是主流程。
5. **日志**：所有编排层脚本用 `scripts/common.ps1` 的 `Write-Step/Write-Ok/Write-Fail` 输出（用户看得懂 + 落盘可查）。

## 当前状态速览

- 软件本体 v0.2.0 已可用：桌面控制台统一操作抖音/QQ/话术库/定时/日志/更新
- 抖音侧：已登录（用户已扫码）；待填真实好友昵称
- QQ 侧：NapCat 可从软件内启动；待用户在界面配置好友火花任务
- 定时：计划任务 `续火花-抖音`（每天 08:30，入口 software/backend/daily_douyin.ps1）
