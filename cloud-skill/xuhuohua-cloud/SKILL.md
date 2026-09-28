---
name: xuhuohua-cloud
description: 从续火花最新 GitHub Release 安装 Linux 云端 Skill，并逐步引导用户选择 QQ/抖音、设置时间、扫码登录及验证每日续火花。
---

# 续火花云端部署

适用于用户自己的 Linux x86_64 云服务器。包内 `qq-plugin/` 和 `douyin-auto-fire/` 是执行程序；本 Skill 是 Agent 的部署指南。只用本地话术，不调用 LLM API 生成消息。服务器需要持续开机联网。

## 1. 获取并安装最新 Release Skill

如果本 Skill 来自桌面版或旧包，先从 [项目最新 Release](https://github.com/lyzbcy/xuhuohua/releases/latest) 下载 `xuhuohua-cloud.zip` 和 `xuhuohua-cloud.zip.sha256`。稳定资产地址：

```text
https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip
https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip.sha256
```

在服务器的私有目录分别下载，执行 `sha256sum -c xuhuohua-cloud.zip.sha256` 后解压。校验失败或资产不存在时停止并告知用户；不要改用旧包或源码分支。确认当前 Agent 的 Skill 目录，再运行 `bash xuhuohua-cloud/scripts/install-skill.sh <Agent 的 skills 目录>`。安装器只复制说明并记录解压目录。**后续命令始终在保留的解压目录执行**；重新加载 Skill 时先读取 Skill 目录里的 `release-path.txt` 并切换到该目录。如果本轮无法重新加载，直接读取解压后的此文件继续。不要把 `qq-data/`、`storage-state.json` 或任何用户配置复制进 Skill 目录。

## 2. 先问用户

一次问清：是否启用 **QQ**、是否启用 **抖音**，各自希望的**北京时间 HH:MM**。同时主动建议配置**企业微信长连接机器人**接收每日结果，询问是否启用；明确这是可选项，用户跳过也能正常续火花。只安装用户选择的平台；都不开启就停止。配置好友时再分别询问目标和本地文字话术，建议先从少量好友开始。不要先运行正式发送。

## 3. QQ 登录与定时

1. 检查 Docker Engine、Compose v2、Python 3 和 crontab。运行 `bash xuhuohua-cloud/scripts/install-qq.sh`。它部署固定版本 `mlikiowa/napcat-docker:v4.18.19` 和本项目插件。首次好友任务处于关闭状态；已有配置不会被覆盖。容器路径以 [NapCat Docker 官方文档](https://github.com/NapNeko/NapCat-Docker) 为准。
2. 运行 `bash xuhuohua-cloud/scripts/qq-qr.sh`。脚本只返回最近 3 分钟生成的 PNG 绝对路径。用 Agent 的图片发送能力在**与用户的私聊**中把该图片发给用户扫码，不要发送 base64 或日志里的 Token；二维码过期就通过 WebUI 刷新再取。若 Agent 无法发送图片，引导用户在自己电脑上建立 `ssh -L 6099:127.0.0.1:6099 用户@服务器`，打开 `http://127.0.0.1:6099/webui` 扫码。WebUI 只绑定服务器本机，不开放公网。
3. 在 WebUI 确认 QQ 已登录。询问目标 QQ 号和一条本地话术后，运行 `python3 xuhuohua-cloud/scripts/configure-qq.py --time HH:MM --targets QQ号1,QQ号2 --message '话术'`；脚本不会立即发送。然后运行 `docker compose -f xuhuohua-cloud/scripts/compose.qq.yaml --project-directory xuhuohua-cloud restart` 加载配置，再运行 `bash xuhuohua-cloud/scripts/verify-qq.sh`。
4. QQ 由插件内置定时器按北京时间每日执行；cron 每 5 分钟只负责拉起停止的容器，另有每分钟一次的只读结果检查。不要再注册直接发 QQ 消息的 cron，避免重复。QQ 掉线时需要用户重新扫码；若错过时间，不自动补发。结果检查在整批完成后通知；超过计划时间 60 分钟仍无完成标记，则报告失败，每个北京时间日期最多报告一次。

## 4. 抖音虚拟桌面登录与定时

1. 运行 `bash xuhuohua-cloud/scripts/prepare-douyin.sh` 安装 Python 依赖和 Chromium。若浏览器缺少系统库，按 Playwright 诊断安装依赖。虚拟桌面需 `Xvfb`、`x11vnc`，建议有 `fluxbox`；在 Debian/Ubuntu 可安装 `xvfb x11vnc fluxbox`。
2. 运行 `bash xuhuohua-cloud/scripts/start-douyin-desktop.sh`。VNC 仅监听服务器 `127.0.0.1:5901`；让用户在自己电脑建立 `ssh -L 5901:127.0.0.1:5901 用户@服务器`，用 VNC 客户端连接 `127.0.0.1:5901`。VNC 不设单独密码，必须先建立 SSH 隧道；不要把 VNC 端口暴露到公网。
3. 在持续运行的终端执行 `bash xuhuohua-cloud/scripts/login-douyin.sh`。用户亲自操作可见浏览器完成扫码、可能出现的人脸验证；确认浏览器显示已登录后，Agent 才给登录脚本输入 Enter。脚本将登录态保存为服务器私有的 `douyin-auto-fire/storage-state.json`。结束后运行 `bash xuhuohua-cloud/scripts/stop-douyin-desktop.sh`。
4. 询问好友昵称和本地文字话术，基于 `douyin-auto-fire/config.example.json` 创建私有 `config.json`，先用 1 位好友和 1 条文字消息，开启防重复，并保持文件权限为 600。执行 `cd douyin-auto-fire && .venv/bin/python run.py --dry-run` 验证登录态和目标。通过后运行 `bash xuhuohua-cloud/scripts/install.sh HH:MM` 注册北京时间每日 cron；正式运行默认无头。

## 5. 可选的企业微信长连接结果通知

用户愿意配置时，使用**当前云端 Agent 官方支持的企业微信长连接机器人接入方式**，在私有会话中完成连接、选定接收人并测试发送。这里需要的是 Agent 已连接的长连接通道，不要把企业微信群 Webhook 当成同一功能，也不要索取或输出机器人密钥。若 Agent 暂不支持长连接或无法做无交互发送，清楚说明通知功能暂不可用，QQ/抖音部署仍继续。

让 Agent 在服务器私有目录创建一个可执行的发送适配命令：它从标准输入读取**一条 UTF-8 文本**，调用已连接的企业微信长连接通道发给用户；成功退出 0，失败返回非 0。只把该命令的**绝对路径**写入解压目录 `xuhuohua-cloud/notify-command`，执行 `chmod 600 xuhuohua-cloud/notify-command`，适配命令本身也仅供当前用户执行。适配命令可调用当前 Agent 的正式发送接口，具体命令以该 Agent 实际安装版本为准，不要猜测 CLI 参数。运行 `python3 xuhuohua-cloud/scripts/notify-result.py test`，确认用户在企业微信私聊中收到测试消息，才向用户报告通知已启用。不要在公开仓库、聊天或日志中写入密钥、会话标识或私有适配脚本。

启用后，抖音每日 cron 在实际运行结束时按退出码发**一条**成功或失败通知；QQ 只读检查读取插件的整批成功/失败记录，整批结束后发**一条**，到点后 60 分钟无完成记录则发失败通知。消息只含平台、结果、北京时间和简要数量/错误提示，不带好友名单与凭证。发送失败记录在 `logs/cron.log` 或 `logs/qq-result.log`，不改变续火花任务本身的结果。没有 `notify-command` 时两个平台照常运行，不发通知；不应把测试发送当成续火花任务。

## 6. 完成检查

报告已启用的平台、北京时间、扫码/登录验证结果、QQ 容器和 cron、抖音 cron、企业微信通知是否启用及日志路径。QQ 可看 `docker logs xuhuohua-napcat`、`logs/qq-watchdog.log` 与 `logs/qq-result.log`；抖音可看 `logs/cron.log` 与 `douyin-auto-fire/artifacts/run.log`。**不要在聊天或公开仓库展示 Cookie、Token、登录态、配置全文或二维码以外的私有数据。**只在用户已经配置并明确启用后等待每日定时；首次设置与验证阶段不真实发送。
