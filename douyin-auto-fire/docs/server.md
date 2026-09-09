# Linux 云服务器部署教程

本教程介绍如何在 Ubuntu / Debian 云服务器上部署 `douyin-auto-fire`，支持单账号、多账号、钉钉通知、Dry Run 和 systemd 定时运行。

推荐系统：Ubuntu 22.04 / 24.04、Debian 12 / 13。建议至少准备约 2 GB 内存，低内存机器可以增加 Swap。

> 第一次使用建议先跑通 1 个账号、1 个好友、1 条文字消息。确认正常后，再增加多账号、原生表情、随机消息或钉钉通知。

---

## 1. 准备 Cookie

在自己的电脑浏览器登录抖音网页版，然后用 Cookie-Editor 导出完整 JSON。

详细步骤参考：[GitHub Actions 教程 - 获取 Cookie](github-actions.md#3-获取抖音-cookie)

> Cookie 相当于登录凭证，不要提交到公开仓库、Issue、日志或截图中。

---

## 2. 安装基础环境

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
python3 --version
```

建议 Python 3.11 或更高版本。

---

## 3. 创建运行用户

```bash
sudo useradd --system \
  --home /opt/douyin-auto-sender \
  --shell /usr/sbin/nologin \
  douyin-sender
```

如果提示用户已存在，可以忽略。

---

## 4. 下载项目

```bash
sudo git clone https://github.com/unmev/douyin-auto-fire.git /opt/douyin-auto-sender
sudo chown -R douyin-sender:douyin-sender /opt/douyin-auto-sender
cd /opt/douyin-auto-sender
```

国内服务器如果访问 GitHub 较慢，也可以使用 CNB 国内同步仓库：

```bash
sudo git clone https://cnb.cool/1mev/douyin-auto-fire.git /opt/douyin-auto-sender
```

GitHub 仍然是主仓库，CNB 用于国内加速。

---

## 5. 创建虚拟环境并安装依赖

```bash
sudo -u douyin-sender -H python3 -m venv /opt/douyin-auto-sender/.venv
sudo -u douyin-sender -H /opt/douyin-auto-sender/.venv/bin/python -m pip install --upgrade pip
sudo -u douyin-sender -H /opt/douyin-auto-sender/.venv/bin/pip install -r /opt/douyin-auto-sender/requirements.txt
```

安装 Chromium 系统依赖和浏览器：

```bash
sudo /opt/douyin-auto-sender/.venv/bin/python -m playwright install-deps chromium
sudo -u douyin-sender -H /opt/douyin-auto-sender/.venv/bin/python -m playwright install chromium
```

---

## 6. 单账号：配置发送内容

```bash
cd /opt/douyin-auto-sender
sudo -u douyin-sender cp config.example.json config.json
sudo -u douyin-sender nano config.json
```

也可以用在线配置生成器：

**https://douyin-config.pages.dev/**

一个最简单的配置：

```json
{
  "friends": ["好友昵称"],
  "messages": [
    {"type": "text", "value": "续火花 ✨"}
  ],
  "send_interval_seconds": {
    "min": 3,
    "max": 8
  },
  "prevent_duplicates": false
}
```

---

## 7. 单账号：保存 Cookie

为了避免把 Cookie 放到 Git 仓库，推荐单独放在 `/etc`：

```bash
sudo mkdir -p /etc/douyin-auto-fire
sudo nano /etc/douyin-auto-fire/cookie.json
```

粘贴 Cookie JSON 后设置权限：

```bash
sudo chown root:douyin-sender /etc/douyin-auto-fire/cookie.json
sudo chmod 640 /etc/douyin-auto-fire/cookie.json
```

---

## 8. 创建 `.env`

```bash
sudo -u douyin-sender nano /opt/douyin-auto-sender/.env
```

单账号推荐：

```env
DOUYIN_COOKIE=/etc/douyin-auto-fire/cookie.json
TASK_CONFIG=/opt/douyin-auto-sender/config.json
ARTIFACTS_DIR=/opt/douyin-auto-sender/artifacts
HEADLESS=true

DINGTALK_WEBHOOK=
DINGTALK_SECRET=
```

然后：

```bash
sudo chmod 600 /opt/douyin-auto-sender/.env
```

---

## 9. 消息通知（可选）

### 钉钉机器人

如果希望每次运行结束后收到钉钉结果，在 `.env` 中填写：

```env
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxx
DINGTALK_SECRET=SECxxxx
```

两个参数必须同时配置。通知会包含任务模式、成功/失败人数和失败原因。

如果不需要通知，两个变量保持为空即可。

### 通用 Webhook（企业微信、飞书、Telegram 等）

项目支持向任意 Webhook 端点发送通知，适用于企业微信、飞书、Slack、Discord、Telegram 等平台。

在 `.env` 中添加：

```env
# 必需：Webhook 地址
WEBHOOK_URL=https://example.com/webhook

# 可选：自定义消息模板（JSON 格式）
WEBHOOK_TEMPLATE={"text":"任务 {task_id} {status}"}

# 可选：自定义 HTTP 请求头
WEBHOOK_HEADERS={"Authorization":"Bearer token"}
```

#### 配置示例

**企业微信群机器人**
```env
WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
WEBHOOK_TEMPLATE={"msgtype":"text","text":{"content":"🔥 抖音任务 {task_id}\n\n{status}\n✅ 成功: {success_count}\n❌ 失败: {failed_count}\n\n⏰ {timestamp}"}}
```

**飞书群机器人**
```env
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_KEY
WEBHOOK_TEMPLATE={"msg_type":"text","content":{"text":"🔥 抖音任务 {task_id}\n\n{status}\n✅ 成功: {success_count}\n❌ 失败: {failed_count}\n\n⏰ {timestamp}"}}
```

**Telegram Bot**
```env
WEBHOOK_URL=https://api.telegram.org/botYOUR_BOT_TOKEN/sendMessage
WEBHOOK_TEMPLATE={"chat_id":"YOUR_CHAT_ID","text":"🔥 抖音任务 {task_id}\n\n{status}\n✅ 成功: {success_count}\n❌ 失败: {failed_count}\n\n⏰ {timestamp}"}
```

#### 模板变量

- `{task_id}` - 任务 ID
- `{status}` - 执行状态
- `{success_count}` - 成功数量
- `{failed_count}` - 失败数量
- `{timestamp}` - 时间戳

#### 测试配置

```bash
cd /opt/douyin-auto-sender
sudo -u douyin-sender -H .venv/bin/python scripts/check_webhook.py
```

多账号模式下，全局 `.env` 中的通知配置会被各账号继承；如果某个账号需要独立通知，可以在该账号自己的 env 文件中覆盖这些变量。

---

## 10. 第一次运行 Dry Run

```bash
cd /opt/douyin-auto-sender
sudo -u douyin-sender -H .venv/bin/python run.py --dry-run
```

Dry Run 会验证登录状态、好友定位和任务配置，但不会真实发送消息。

确认成功后再真实运行：

```bash
sudo -u douyin-sender -H .venv/bin/python run.py
```

---

## 11. 多账号（可选）

Linux 本地运行原生支持多账号。只要创建：

```text
config/accounts.json
```

程序就会自动进入多账号模式，并串行执行所有启用账号。一个账号失败不会阻止后面的账号继续运行。

### 11.1 创建目录

```bash
cd /opt/douyin-auto-sender
sudo -u douyin-sender mkdir -p config/tasks storage_state
```

### 11.2 创建 `config/accounts.json`

```bash
sudo -u douyin-sender nano config/accounts.json
```

示例：

```json
{
  "accounts": [
    {
      "id": "account1",
      "enabled": true,
      "env_file": ".env.account1"
    },
    {
      "id": "account2",
      "enabled": true,
      "env_file": ".env.account2"
    }
  ]
}
```

`enabled: false` 可以临时停用某个账号。

### 11.3 每个账号创建独立 env

账号 1：

```bash
sudo -u douyin-sender nano .env.account1
```

```env
DOUYIN_COOKIE=/etc/douyin-auto-fire/account1.json
TASK_CONFIG=config/tasks/account1.json
```

账号 2：

```bash
sudo -u douyin-sender nano .env.account2
```

```env
DOUYIN_COOKIE=/etc/douyin-auto-fire/account2.json
TASK_CONFIG=config/tasks/account2.json
```

如果希望账号 2 使用独立钉钉机器人，可以追加：

```env
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxx
DINGTALK_SECRET=SECxxxx
```

### 11.4 保存每个账号 Cookie

```bash
sudo nano /etc/douyin-auto-fire/account1.json
sudo nano /etc/douyin-auto-fire/account2.json
sudo chown root:douyin-sender /etc/douyin-auto-fire/account*.json
sudo chmod 640 /etc/douyin-auto-fire/account*.json
```

### 11.5 保存每个账号任务配置

```bash
sudo -u douyin-sender nano config/tasks/account1.json
sudo -u douyin-sender nano config/tasks/account2.json
```

每个账号可以有完全不同的好友和消息配置。

### 11.6 测试多账号

```bash
sudo -u douyin-sender -H .venv/bin/python run.py --dry-run
```

日志会出现类似：

```text
多账号模式：共 2 个启用账号
[account1] ...
[account2] ...
```

运行产物默认分开保存：

```text
artifacts/account1/
artifacts/account2/
```

确认无误后再运行：

```bash
sudo -u douyin-sender -H .venv/bin/python run.py
```

> 删除或重命名 `config/accounts.json` 后，会恢复单账号模式。

---

## 12. 配置 systemd 自动运行

项目自带：

```text
deploy/systemd/douyin-sender.service
deploy/systemd/douyin-sender.timer
```

安装：

```bash
sudo cp deploy/systemd/douyin-sender.service /etc/systemd/system/
sudo cp deploy/systemd/douyin-sender.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now douyin-sender.timer
```

查看：

```bash
systemctl list-timers --all | grep douyin-sender
```

同一个 `run.py` 会自动识别单账号或多账号，所以 **systemd 不需要为每个账号创建一套 service**。

---

## 13. 修改每天运行时间

默认 Timer 为每天服务器本地时间 08:00。

先确认时区：

```bash
timedatectl
```

需要北京时间：

```bash
sudo timedatectl set-timezone Asia/Shanghai
```

修改定时器：

```bash
sudo nano /etc/systemd/system/douyin-sender.timer
```

例如每天 00:30：

```ini
[Timer]
OnCalendar=*-*-* 00:30:00
Persistent=true
RandomizedDelaySec=0
```

然后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart douyin-sender.timer
```

---

## 14. 手动触发和查看日志

```bash
sudo systemctl start douyin-sender.service
sudo systemctl status douyin-sender.service
journalctl -u douyin-sender.service -n 100 --no-pager
```

实时日志：

```bash
journalctl -u douyin-sender.service -f
```

程序诊断文件：

```text
/opt/douyin-auto-sender/artifacts/
```

多账号时：

```text
/opt/douyin-auto-sender/artifacts/account1/
/opt/douyin-auto-sender/artifacts/account2/
```

---

## 15. Cookie 失效

重新在电脑登录抖音并导出对应账号 Cookie，替换服务器上的 JSON 文件，然后先执行：

```bash
sudo -u douyin-sender -H /opt/douyin-auto-sender/.venv/bin/python /opt/douyin-auto-sender/run.py --dry-run
```

---

## 16. 更新项目

GitHub 源：

```bash
cd /opt/douyin-auto-sender
sudo -u douyin-sender -H git pull
sudo -u douyin-sender -H .venv/bin/pip install -r requirements.txt
```

如果使用 CNB clone，`git pull` 同样即可。

Playwright 版本变化后建议：

```bash
sudo /opt/douyin-auto-sender/.venv/bin/python -m playwright install-deps chromium
sudo -u douyin-sender -H /opt/douyin-auto-sender/.venv/bin/python -m playwright install chromium
```

---

## 注意事项

- Cookie、`.env`、`.env.account*` 和钉钉机器人密钥不要提交到公开仓库。
- 多账号是串行执行，不会并发启动多个账号。
- 同一个抖音账号不要同时在多个机器/任务中运行，避免重复发送。
- 服务器网络环境可能触发抖音安全验证。
- 日志、截图和 Trace 可能包含聊天信息，请勿随意公开。

---

## 其他部署方式

- [GitHub Actions 部署](github-actions.md)
- [Docker 部署](docker.md)
- [Windows 电脑部署](windows.md)
- [返回项目主页](../README.md)
