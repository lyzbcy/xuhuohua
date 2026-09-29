"""Aggregate QQ and Douyin outcomes into one detailed daily WeCom message."""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows unit tests; cloud runtime is Linux.
    fcntl = None

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
COMMAND_FILE = SKILL / "notify-command"
WEBHOOK_FILE = SKILL / "notify-webhook"
STATE_FILE = SKILL / "notify-state.json"
QQ_CONFIG = SKILL / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
QQ_RESULT = SKILL / "qq-result.json"
DOUYIN_RESULT = ROOT / "douyin-auto-fire/artifacts/notification-result.json"
DOUYIN_SCHEDULE = SKILL / "douyin-schedule.json"
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
MAX_MESSAGE_BYTES = 2000


def command_path() -> Path | None:
    if not COMMAND_FILE.exists():
        return None
    if COMMAND_FILE.stat().st_mode & 0o077:
        raise ValueError("notify-command 权限过宽，请 chmod 600")
    value = COMMAND_FILE.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or not Path(value).is_absolute():
        raise ValueError("notify-command 必须只包含一个可执行文件的绝对路径")
    command = Path(value)
    if not command.is_file() or not os.access(command, os.X_OK):
        raise ValueError("企业微信通知适配命令不存在或不可执行")
    return command


def webhook_url() -> str | None:
    if not WEBHOOK_FILE.exists():
        return None
    if WEBHOOK_FILE.stat().st_mode & 0o077:
        raise ValueError("notify-webhook 权限过宽，请 chmod 600")
    url = WEBHOOK_FILE.read_text(encoding="utf-8").strip()
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.hostname != "qyapi.weixin.qq.com"
            or parsed.path != "/cgi-bin/webhook/send" or not query.get("key")
            or "\n" in url):
        raise ValueError("notify-webhook 不是有效的企业微信群机器人地址")
    return url


def transport() -> tuple[str, str | Path] | None:
    url = webhook_url()
    if url:
        return "webhook", url
    command = command_path()
    return ("command", command) if command else None


def send(destination: tuple[str, str | Path], message: str) -> bool:
    kind, value = destination
    if kind == "webhook":
        payload = json.dumps({"msgtype": "text", "text": {"content": message}},
                             ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(str(value), data=payload,
                                         headers={"Content-Type": "application/json; charset=utf-8"},
                                         method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError("企业微信响应格式无效")
            if result.get("errcode") == 0:
                return True
            print(f"企业微信通知发送失败，接口错误码 {result.get('errcode', 'unknown')}", file=sys.stderr)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print(f"企业微信通知发送失败：{type(exc).__name__}", file=sys.stderr)
        return False
    try:
        result = subprocess.run([str(value)], input=message + "\n", text=True,
                                encoding="utf-8", stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"企业微信通知发送失败：{type(exc).__name__}", file=sys.stderr)
        return False
    return result.returncode == 0


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _day(value) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(BEIJING).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def qq_result(config: dict, now: datetime) -> tuple[str, str] | None:
    """Compatibility summary used when a pre-0.13.10 install has no detail file."""
    if not config.get("enabled") or not config.get("friendSpark_enable"):
        return None
    when = str(config.get("friendSpark_time", ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", when):
        return None
    hour, minute, second = map(int, when.split(":"))
    due = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if now < due:
        return None
    stats = config.get("stats") if isinstance(config.get("stats"), dict) else {}
    try:
        completed_ms = int(stats.get("friendSparkCompletedAt") or 0)
        succeeded = int(stats.get("friendSparkSucceeded") or 0)
        failed = int(stats.get("friendSparkFailed") or 0)
    except (TypeError, ValueError):
        completed_ms = succeeded = failed = 0
    if completed_ms:
        completed = datetime.fromtimestamp(completed_ms / 1000, BEIJING)
        if due <= completed <= now and succeeded + failed > 0:
            stopped = stats.get("friendSparkSessionStopped") is not False
            status = "成功" if failed == 0 and stopped else "失败"
            cleanup = "已自动退出" if stopped else "自动退出失败"
            return status, f"成功 {succeeded}，失败 {failed}；{cleanup}"
    if now >= due + timedelta(minutes=60):
        return "失败", "计划时间后 60 分钟仍无整批完成记录"
    return None


def _due(config: dict | None, now: datetime) -> datetime | None:
    if not isinstance(config, dict):
        return None
    value = str(config.get("time") or config.get("friendSpark_time") or "")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", value):
        return None
    parts = list(map(int, value.split(":")))
    return now.replace(hour=parts[0], minute=parts[1], second=parts[2] if len(parts) > 2 else 0,
                       microsecond=0)


def _enabled(invoked: str) -> tuple[list[str], dict, dict]:
    qq = _read_json(QQ_CONFIG)
    douyin = _read_json(DOUYIN_SCHEDULE)
    platforms = []
    if isinstance(douyin, dict) and douyin.get("enabled"):
        platforms.append("douyin")
    if isinstance(qq, dict) and qq.get("enabled") and qq.get("friendSpark_enable"):
        platforms.append("qq")
    if invoked in {"douyin", "qq"} and invoked not in platforms:
        platforms.append(invoked)
    return platforms, douyin or {}, qq or {}


def _douyin_terminal(now: datetime, exit_code: int | None):
    data = _read_json(DOUYIN_RESULT)
    today = now.strftime("%Y-%m-%d")
    if isinstance(data, dict) and _day(data.get("finished_at")) == today:
        items = []
        for item in data.get("results", []):
            if isinstance(item, dict):
                items.append({"target": str(item.get("target") or "未知好友"),
                              "messages": [str(x) for x in item.get("messages", [])],
                              "ok": item.get("status") == "success",
                              "error": str(item.get("error") or "")})
        if items:
            return {"status": "success" if all(x["ok"] for x in items) else "failed", "items": items}
    if exit_code is not None:
        detail = "未生成可核验的发送明细" if exit_code == 0 else f"任务退出码 {exit_code}"
        return {"status": "failed", "items": [{"target": "抖音任务", "messages": [],
                                                  "ok": False, "error": detail}]}
    return None


def _qq_terminal(now: datetime, config: dict):
    today = now.strftime("%Y-%m-%d")
    data = _read_json(QQ_RESULT)
    if isinstance(data, dict) and str(data.get("day") or _day(data.get("finished_at"))) == today:
        items = []
        for item in data.get("recipients", []):
            if isinstance(item, dict):
                target = str(item.get("target") or "")
                name = str(item.get("name") or target or "未知好友")
                label = f"{name}（QQ尾号 {target[-4:]}）" if target and name != target else f"QQ尾号 {target[-4:]}"
                items.append({"target": label, "messages": [str(item.get("message") or "")],
                              "ok": bool(item.get("confirmed")),
                              "error": str(item.get("error") or "")})
        if items:
            stopped = data.get("session_stopped") is True
            if not stopped:
                items.append({"target": "QQ 会话收尾", "messages": [], "ok": False,
                              "error": "发送后自动退出失败"})
            return {"status": "success" if all(x["ok"] for x in items) else "failed", "items": items}
    fallback = qq_result(config, now)
    if fallback is None:
        return None
    status, detail = fallback
    targets = [x.strip() for x in str(config.get("friendSpark_targets", "")).split(",") if x.strip()]
    message = str(config.get("friendSpark_message") or "")
    return {"status": "success" if status == "成功" else "failed",
            "items": [{"target": f"QQ尾号 {target[-4:]}", "messages": [message],
                       "ok": status == "成功", "error": "" if status == "成功" else detail}
                      for target in targets] or
                     [{"target": "QQ 任务", "messages": [], "ok": False, "error": detail}]}


def _timeout(platform: str, now: datetime, config: dict):
    due = _due(config, now)
    if due and now >= due + timedelta(minutes=60):
        return {"status": "failed", "items": [{"target": f"{platform} 任务", "messages": [],
                                                  "ok": False, "error": "计划时间后 60 分钟仍无完成记录"}]}
    return None


def _truncate_utf8(value: str, limit: int = MAX_MESSAGE_BYTES) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    suffix = "\n…明细过长，已截断；完整结果请查看服务器私有日志"
    budget = limit - len(suffix.encode("utf-8"))
    return encoded[:budget].decode("utf-8", errors="ignore") + suffix


def build_message(day: str, results: dict) -> str:
    overall = "成功" if results and all(x.get("status") == "success" for x in results.values()) else "部分失败"
    lines = [f"续火花每日任务汇总｜{day} 北京时间", f"总结果：{overall}"]
    labels = {"douyin": "抖音", "qq": "QQ"}
    for platform in ("douyin", "qq"):
        if platform not in results:
            continue
        items = results[platform].get("items", [])
        succeeded = sum(bool(item.get("ok")) for item in items)
        lines.extend(["", f"{labels[platform]}：成功 {succeeded}/{len(items)}"])
        for item in items:
            lines.append(f"• {item.get('target', '未知目标')}")
            messages = [x for x in item.get("messages", []) if x]
            if messages:
                lines.append("  发送内容：" + "\n  ".join(messages))
            lines.append("  结果：" + ("已在聊天记录确认" if item.get("ok") else
                                      (item.get("error") or "失败")))
    return _truncate_utf8("\n".join(lines))


def aggregate(destination, platform: str, now: datetime, exit_code: int | None = None) -> int:
    platforms, douyin_config, qq_config = _enabled(platform)
    day = now.strftime("%Y-%m-%d")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("a+", encoding="utf-8") as stream:
        os.chmod(STATE_FILE, 0o600)
        if fcntl is not None:
            fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        try:
            state = json.load(stream)
        except ValueError:
            state = {}
        days = state.setdefault("days", {})
        current = days.setdefault(day, {"results": {}, "notified": False})
        if state.get("qq_notified_day") == day:
            current["notified"] = True  # pre-0.13.10 already notified today
        if current.get("notified"):
            return 0
        results = current.setdefault("results", {})
        douyin = _douyin_terminal(now, exit_code if platform == "douyin" else None)
        qq = _qq_terminal(now, qq_config)
        if douyin:
            results["douyin"] = douyin
        elif "douyin" in platforms:
            timeout = _timeout("抖音", now, douyin_config)
            if timeout:
                results["douyin"] = timeout
        if qq:
            results["qq"] = qq
        elif "qq" in platforms:
            timeout = _timeout("QQ", now, qq_config)
            if timeout:
                results["qq"] = timeout
        if not platforms or any(name not in results for name in platforms):
            _save_state(stream, state)
            return 0
        if not send(destination, build_message(day, {name: results[name] for name in platforms})):
            _save_state(stream, state)
            return 1
        current["notified"] = True
        current["notified_at"] = now.isoformat()
        _save_state(stream, state)
    return 0


def _save_state(stream, value):
    stream.seek(0)
    stream.truncate()
    json.dump(value, stream, ensure_ascii=False)
    stream.flush()
    os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("douyin", "qq", "test"))
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()
    try:
        destination = transport()
    except (OSError, ValueError) as exc:
        print(f"企业微信通知未启用：{exc}", file=sys.stderr)
        return 1
    if destination is None:
        if args.platform == "test":
            print("尚未配置企业微信通知链接", file=sys.stderr)
            return 2
        return 0
    if args.platform == "test":
        return 0 if send(destination, "续火花企业微信通知测试｜连接正常，不会触发续火花发送") else 1
    if args.platform == "douyin" and args.exit_code is None:
        parser.error("抖音通知需要 --exit-code")
    return aggregate(destination, args.platform, datetime.now(BEIJING), args.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
