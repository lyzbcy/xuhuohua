---
name: xuhuohua-cloud
description: 从续火花最新 GitHub Release 安装 Linux 云端 Skill，并逐步引导用户选择 QQ/抖音、设置时间、扫码登录及验证每日续火花。
---

# 续火花云端部署

适用于用户自己的 Linux x86_64 云服务器。包内 `douyin-auto-fire/` 与 QQ OneBot 定时脚本是执行程序；本 Skill 是 Agent 的部署指南。只用本地话术，不调用 LLM API 生成消息。服务器需要持续开机联网。QQ 采用“到点借号”：任务时间才启动并登录，结束后退出，平时不占用账号。

## 1. 获取并安装最新 Release Skill

如果本 Skill 来自桌面版或旧包，先从 [项目最新 Release](https://github.com/lyzbcy/xuhuohua/releases/latest) 下载 `xuhuohua-cloud.zip` 和 `xuhuohua-cloud.zip.sha256`。稳定资产地址：

```text
https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip
https://github.com/lyzbcy/xuhuohua/releases/latest/download/xuhuohua-cloud.zip.sha256
```

在服务器的私有目录分别下载，执行 `sha256sum -c xuhuohua-cloud.zip.sha256` 后解压。校验失败或资产不存在时停止并告知用户；不要改用旧包或源码分支。确认当前 Agent 的 Skill 目录，再运行 `bash xuhuohua-cloud/scripts/install-skill.sh <Agent 的 skills 目录>`。安装器复制 Skill 说明、版本与静默更新组件，并记录解压目录。**后续命令始终在保留的解压目录执行**；重新加载 Skill 时先读取 Skill 目录里的 `release-path.txt` 并切换到该目录。如果本轮无法重新加载，直接读取解压后的此文件继续。不要把 `qq-data/`、`storage-state.json` 或任何用户配置复制进 Skill 目录。

**每次使用本 Skill 的第一步**：在已安装的 Agent Skill 目录执行 `bash xuhuohua-cloud/check-update.sh`，然后立即继续当前工作，不等待更新。脚本每天北京时间首次使用时在后台静默检查最新 Release；失败继续用旧版，下次使用再重试。初次安装尚未有该文件时跳过此步，按本节先安装。

**从旧版首次升级**：旧版没有更新入口，需在任务空闲时手动校验最新云端 ZIP，把包内公共文件覆盖到**原解压目录**，保留 `qq-data/`、`douyin-auto-fire/config.json`、`storage-state.json`、`notify-webhook` 等私有文件，再重跑 `install-skill.sh`。QQ 升级后必须重跑 `install-qq.sh`，让 Compose 改为按需启动并删除旧 watchdog cron；已有登录态用 `qq-run.py --session-check` 验收，不做真实补发。

## 2. 先问用户

一次问清：是否启用 **QQ**、是否启用 **抖音**，各自希望的**北京时间 HH:MM**。同时主动建议配置**企业微信群机器人 webhook 推送链接**接收每日结果，询问是否启用；用户已经给出链接时直接沿用私有上下文，不要再索取或复述。明确通知是可选项，跳过也能正常续火花。只安装用户选择的平台；都不开启就停止。配置好友时再分别询问目标和本地文字话术，建议先从少量好友开始。不要先运行正式发送。

## 3. QQ 登录与定时

1. 检查 Docker Engine、Compose v2、Python 3 和 crontab。运行 `bash xuhuohua-cloud/scripts/install-qq.sh`。它部署固定版本 `mlikiowa/napcat-docker:v4.18.19`，将旧版被白名单拒载的插件移入私有备份目录，固定容器 MAC 与主机名，删除旧版常驻 watchdog，并注册 QQ 本机 cron；已有好友配置不会被覆盖。容器路径以 [NapCat Docker 官方文档](https://github.com/NapNeko/NapCat-Docker) 为准。
2. 默认运行 `bash xuhuohua-cloud/scripts/qq-login-page.sh start`，给用户 `ssh -L 6100:127.0.0.1:6100 用户@服务器` 和浏览器链接 `http://127.0.0.1:6100/`。这是只监听服务器本机、每 2 秒读取最新二维码的页面；过期会提示在 WebUI 刷新，**不要反复发送静态二维码截图**。需要管理 NapCat 时另建 `ssh -L 6099:127.0.0.1:6099 用户@服务器`，打开 `http://127.0.0.1:6099/webui`。两个端口都不能公开到公网；不要把 WebUI Token 发给他人。
3. 用户扫码并在手机上授权后，先在 WebUI 确认账号已登录，检查 `/app/.config/QQ` 是否挂载到原有 `qq-data/QQ` 且已落盘。询问目标 QQ 号和一条本地话术，运行 `python3 xuhuohua-cloud/scripts/configure-qq.py --time HH:MM --targets QQ号1,QQ号2 --message '话术'`；运行时会自动追加固定结尾 `来自捞鱼自动续火花`，不要让用户重复填写签名。再运行 `python3 xuhuohua-cloud/scripts/configure-onebot.py` 写入私有 OneBot 令牌；两者均不会发消息。**重启容器后再次运行 `verify-qq.sh` 确认同一账号仍已登录**。若重新要求扫码，先检查固定设备标识、挂载目录、权限和 QQ 设备信任；解决并重做重启验证，不要宣称成功。
4. 关闭临时页面：`bash xuhuohua-cloud/scripts/qq-login-page.sh stop`。随后运行 `python3 xuhuohua-cloud/scripts/qq-run.py --session-check`，它必须完成“启动容器 → 自动登录 → OneBot 真登录验证 → 停止容器”，全程不发消息。确认 `docker inspect -f '{{.State.Running}}' xuhuohua-napcat` 输出 `false` 后，才算 QQ 部署通过。
5. QQ cron 每分钟核对北京时间，仅在配置分钟且当天尚未执行时工作。执行顺序固定为：启动 NapCat → 等待自动登录 → 未上线时通过本机 WebUI `/SetQuickLogin` 主动快登 → 验证 OneBot 账号 → 发送单条消息 → 用返回的 `message_id`、本人账号和完整正文回查聊天记录 → 整批结束后停止容器。只有聊天记录三项完全匹配才算成功；接口只返回成功但历史中找不到时按失败记录，为避免重复不自动重发。无论成功、部分失败或异常都在 `finally` 中停止容器。停止容器会释放 QQ 在线会话并保留下次快登凭证；不要调用会清除设备信任的账号注销。平时不得启动 watchdog 或保持容器常驻。
6. 如果同账号在本机登录并把云端顶下线，无需立即处理；到点脚本会重新快登，可能把本机会话顶下线，发送后再释放。若 QQ 风控使快登凭证失效，任务应失败并通知用户重新扫码，不能绕过安全验证。若错过时间，不自动补发。不要叠加其他 QQ 发送 cron。

## 4. 抖音虚拟桌面登录与定时

1. 运行 `bash xuhuohua-cloud/scripts/prepare-douyin.sh` 安装 Python 依赖和 Chromium。若浏览器缺少系统库，按 Playwright 诊断安装依赖。虚拟桌面需 `Xvfb`、`x11vnc`、`novnc`、`websockify`，建议有 `fluxbox`；在 Debian/Ubuntu 可安装 `xvfb x11vnc novnc websockify fluxbox`。
2. 运行 `bash xuhuohua-cloud/scripts/start-douyin-desktop.sh`，随即在持续运行的终端执行 `bash xuhuohua-cloud/scripts/login-douyin.sh`，等待浏览器进入登录页。**默认提供 noVNC 网页链接**：让用户在自己电脑建立 `ssh -L 6089:127.0.0.1:6089 用户@服务器`，在浏览器打开 `http://127.0.0.1:6089/vnc_lite.html?autoconnect=true`。6089 刻意避开可能已由 nginx `/vnc/` 公开反代的 6080；上线前仍应核对本机反代配置。noVNC 与 VNC 仅监听服务器本机，必须经 SSH 隧道；不要公开无密码桌面，也不要默认要求用户安装 VNC 客户端。
3. 用户亲自操作 noVNC 中的浏览器完成扫码、可能出现的人脸验证。**等用户明确确认登录结束**且浏览器显示已登录后，Agent 才给登录脚本输入 Enter；脚本将登录态保存为服务器私有的 `douyin-auto-fire/storage-state.json`。确认文件存在且权限为 600 后，立即运行 `bash xuhuohua-cloud/scripts/stop-douyin-desktop.sh`，关闭 noVNC、VNC 和本次启动的虚拟桌面。若登录失败，也关闭临时桌面并报告原因。
4. 询问好友昵称和本地文字话术，基于 `douyin-auto-fire/config.example.json` 创建私有 `config.json`，先用 1 位好友和 1 条文字消息，开启防重复，并保持文件权限为 600。执行 `cd douyin-auto-fire && .venv/bin/python run.py --dry-run` 验证登录态和目标。通过后运行 `bash xuhuohua-cloud/scripts/install.sh HH:MM` 注册北京时间每日 cron；正式运行默认无头，并为每位好友自动追加独立签名消息 `来自捞鱼自动续火花`，配置已有相同签名时不会重复追加。

## 5. 可选的企业微信群机器人结果通知

用户愿意配置时，使用用户提供的**企业微信群机器人 webhook 推送链接**；这是本 Skill 支持的结果推送方式，**不要求企业微信长连接机器人**。把完整链接只写入解压目录 `xuhuohua-cloud/notify-webhook`，执行 `chmod 600 xuhuohua-cloud/notify-webhook`。不要在命令行参数、聊天回复、公开仓库或日志里再次打印该链接及其中的 `key`；已给出的链接无需重复索取。若用户不配置，保持该文件不存在即可。

运行 `python3 xuhuohua-cloud/scripts/notify-result.py test`，确认目标企业微信群收到了测试消息，才向用户报告通知已启用。脚本仅向 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send` 发送文本消息并检查接口错误码。旧版的私有 `notify-command` 适配命令仍兼容，但新安装优先使用 webhook；如果两者都有，以 `notify-webhook` 为准。

启用后，每个北京时间日期最多推送**一条合并通知**。若同时启用抖音和 QQ，要等两边都有终态后再发送；任一平台在计划时间后 60 分钟仍无完成记录，则把该平台作为失败并纳入当天汇总。汇总逐项列出平台、真实好友名称（QQ 仅展示尾号）、实际发送内容和聊天记录确认结果；抖音读取私有 `notification-result.json`，QQ 读取私有 `qq-result.json`。QQ 消息发送后自动退出失败也按失败。所有明细文件权限为 600，发布包必须排除。通知发送失败只写 `logs/cron.log` 或 `logs/qq-result.log`，不改变续火花任务本身的结果。没有通知配置时两个平台照常运行，不发通知；测试消息不得伪装成续火花任务。

## 6. Skill 静默更新

`check-update.sh` 在每天北京时间首次使用时立即后台运行，当前任务继续使用已加载版本。后台 updater 对照本地 `VERSION` 与 GitHub 最新正式 Release，下载云端包和 SHA-256 校验文件，只原子替换 Skill 说明与包内脚本，最后更新版本号；失败保留旧版本并在下次使用重试。日志在已安装 Skill 目录的 `.update.log`。`notify-webhook`、`notify-command`、QQ 登录态、抖音 Cookie、好友配置、定时任务及正在运行的任务均不覆盖。涉及 QQ Compose 或 cron 规范变化时，必须在任务空闲时重跑 `install-qq.sh`；静默更新不会擅自重建运行中的容器。

## 7. 完成检查

报告已启用的平台、北京时间、扫码/登录验证结果、QQ `--session-check` 自动登录与退出结果、cron、抖音 cron、企业微信通知是否启用及日志路径。QQ 可看 `docker logs xuhuohua-napcat`、`logs/qq-run.log` 与 `logs/qq-result.log`；完成时 QQ 容器应为停止状态。抖音可看 `logs/cron.log` 与 `douyin-auto-fire/artifacts/run.log`。**不要在聊天或公开仓库展示 Cookie、Token、登录态、配置全文或二维码以外的私有数据。**只在用户已经配置并明确启用后等待每日定时；首次设置与验证阶段不真实发送。
