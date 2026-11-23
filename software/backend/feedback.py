"""User-initiated feedback to the developer's WeCom robot."""
import json
import os
import re
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from backend import logger
from backend.paths import PROJECT_ROOT


CHANNEL_FILE = PROJECT_ROOT / "config" / "feedback-channel.json"
CATEGORIES = {"登录与连接", "定时任务", "发送与签名", "界面与操作", "功能建议", "其他"}
MAX_MESSAGE_BYTES = 1100
EVENT_LINE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
    r"\[(OK|INFO|WARN|FAIL|OUT|SCHED)\](?: \[(app|qq|douyin|sched|setup|pool|notify|rotate|cloud|feedback)\])?"
)


def _endpoint():
    value = os.environ.get("XUHUOHUA_FEEDBACK_WEBHOOK", "").strip()
    if not value:
        try:
            value = json.loads(CHANNEL_FILE.read_text(encoding="utf-8")).get("webhook", "")
        except (OSError, ValueError, AttributeError):
            return ""
    if not isinstance(value, str):
        return ""
    try:
        url = urlsplit(value)
    except ValueError:
        return ""
    if (url.scheme == "https" and url.netloc == "qyapi.weixin.qq.com"
            and url.path == "/cgi-bin/webhook/send" and not url.fragment
            and re.fullmatch(r"key=[a-zA-Z0-9_-]{12,100}", url.query)):
        return value
    return ""


def available():
    return bool(_endpoint())


def _diagnostics():
    try:
        entries = logger.today_log_text(tail=80).splitlines()
    except OSError:
        entries = []
    lines = []
    for line in entries:
        event = EVENT_LINE.match(line)
        if event:
            stamp, level, source = event.groups()
            lines.append(f"{stamp} {level} {source or 'schedule'}")
    return ["诊断日志摘要（时间、级别、模块）", *(lines[-12:] or ["今天暂无可附带的日志条目"])]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(app, version, category, message, include_logs):
    message = str(message or "").strip()
    if not message:
        return {"ok": False, "msg": "请填写反馈内容。"}
    if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
        return {"ok": False, "msg": "留言过长，请缩短至 1100 字节以内。"}
    if category and category not in CATEGORIES:
        return {"ok": False, "msg": "请选择有效的问题分类。"}

    url = _endpoint()
    if not url:
        return {"ok": False, "msg": "开发者反馈通道尚未配置。"}
    lines = [f"【用户反馈】{app} v{version}"]
    if category:
        lines.append(f"分类：{category}")
    lines.append(message)
    if include_logs is True:
        lines.extend(["", *_diagnostics()])
    payload = {"msgtype": "text", "text": {"content": "\n".join(lines)}}
    req = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                  headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with build_opener(_NoRedirect()).open(req, timeout=8) as response:
            result = json.loads(response.read(16384).decode("utf-8"))
        if isinstance(result, dict) and result.get("errcode") == 0:
            logger.ok("用户反馈已由企微接收", source="feedback")
            return {"ok": True, "msg": "已发送到开发者的企业微信。"}
        logger.warn("企微拒绝接收用户反馈", source="feedback")
    except (OSError, URLError, ValueError):
        logger.warn("用户反馈请求失败或响应不可读", source="feedback")
    return {"ok": False, "msg": "企微未确认接收，内容已保留。"}
