"""Send the configured QQ friend message once per Beijing day through local OneBot HTTP."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows tests; cloud runtime is Linux.
    fcntl = None

SKILL = Path(__file__).resolve().parents[1]
QQ_CONFIG = SKILL / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
STATE = SKILL / "qq-run-state.json"
RESULT = SKILL / "qq-result.json"
BEIJING = timezone(timedelta(hours=8))
COMPOSE = SKILL / "scripts/compose.qq.yaml"
WEBUI_CONFIG = SKILL / "qq-data/config/webui.json"
SIGNATURE = "——来自楼宇自动续火花"
OLD_SIGNATURES = ("——来自捞鱼自动续火花",)


def with_signature(message):
    value = str(message).rstrip()
    for old in OLD_SIGNATURES:
        if value.endswith(old):
            value = value[:-len(old)].rstrip()
    if value.endswith(SIGNATURE):
        return value
    return value + "\n" + SIGNATURE


def settings():
    config = json.loads(QQ_CONFIG.read_text(encoding="utf-8"))
    if not config.get("enabled") or not config.get("friendSpark_enable"):
        return None
    when = str(config.get("friendSpark_time", ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", when):
        raise ValueError("QQ 发送时间无效")
    targets = list(dict.fromkeys(x.strip() for x in str(config.get("friendSpark_targets", "")).split(",") if x.strip()))
    if not targets or not all(re.fullmatch(r"[1-9]\d{4,14}", x) for x in targets):
        raise ValueError("QQ 好友目标无效")
    message = str(config.get("friendSpark_message", ""))
    if not message.strip():
        raise ValueError("QQ 话术为空")
    message = with_signature(message)
    return config, when, targets, message


def endpoint():
    files = list((SKILL / "qq-data/config").glob("onebot11_*.json"))
    if len(files) != 1:
        raise ValueError("QQ OneBot 账号配置不唯一")
    data = json.loads(files[0].read_text(encoding="utf-8"))
    matches = [x for x in data.get("network", {}).get("httpServers", [])
               if x.get("name") == "xuhuohua-local" and x.get("enable")]
    if len(matches) != 1 or not matches[0].get("token"):
        raise ValueError("QQ 本机 OneBot 接口未配置")
    inspect = subprocess.run(["docker", "inspect", "xuhuohua-napcat"],
                             capture_output=True, text=True, check=True, timeout=15)
    container = json.loads(inspect.stdout)[0]
    if not container["State"]["Running"]:
        raise ValueError("QQ 容器未运行")
    networks = container["NetworkSettings"]["Networks"].values()
    ips = [item.get("IPAddress") for item in networks if item.get("IPAddress")]
    if len(ips) != 1:
        raise ValueError("QQ 容器网络地址不唯一")
    return f"http://{ips[0]}:{matches[0]['port']}", matches[0]["token"]


def onebot(action, payload, address, token):
    request = urllib.request.Request(address + "/" + action,
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json; charset=utf-8",
                                              "Authorization": "Bearer " + token}, method="POST")
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if result.get("retcode") != 0:
        raise RuntimeError("OneBot API 返回失败")
    return result.get("data") or {}


def check_login(address, token, own_account):
    data = onebot("get_login_info", {}, address, token)
    if str(data.get("user_id", "")) != own_account:
        raise RuntimeError("QQ 登录态未就绪")


def friend_names(address, token):
    try:
        data = onebot("get_friend_list", {}, address, token)
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}
    return {
        str(item.get("user_id")): str(item.get("remark") or item.get("nickname") or item.get("user_id"))
        for item in data if isinstance(item, dict) and item.get("user_id")
    }


def _history_messages(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("messages", "message_list", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _message_text(item):
    raw = item.get("raw_message")
    if isinstance(raw, str):
        return raw
    message = item.get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for segment in message:
            if not isinstance(segment, dict):
                continue
            data = segment.get("data") or {}
            if segment.get("type") == "text" and isinstance(data.get("text"), str):
                parts.append(data["text"])
        return "".join(parts)
    return ""


def history_confirms(data, message_id, own_account, expected_message):
    for item in _history_messages(data):
        if not isinstance(item, dict) or str(item.get("message_id", item.get("msgId", ""))) != str(message_id):
            continue
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        sender_id = str(sender.get("user_id", item.get("user_id", "")))
        if sender_id and sender_id != str(own_account):
            continue
        if _message_text(item).strip() == expected_message.strip():
            return True
    return False


def confirm_sent(target, message_id, own_account, expected_message, address, token,
                 attempts=5, poll_seconds=1):
    for attempt in range(attempts):
        data = onebot("get_friend_msg_history", {"user_id": int(target), "count": 20}, address, token)
        if history_confirms(data, message_id, own_account, expected_message):
            return True
        if attempt + 1 < attempts:
            time.sleep(poll_seconds)
    return False


def save_result(value):
    temp = RESULT.with_name(RESULT.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(RESULT)


def _compose(*args):
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "--project-directory", str(SKILL), *args],
        capture_output=True, text=True, check=True, timeout=90)


def start_container():
    """Start the QQ engine only for the current scheduled session."""
    _compose("up", "-d", "napcat")


def stop_container():
    """Release the QQ session while preserving its quick-login data."""
    _compose("stop", "-t", "20", "napcat")


def webui_quick_login(account):
    """Trigger NapCat's real quick-login action through the loopback WebUI."""
    try:
        webui = json.loads(WEBUI_CONFIG.read_text(encoding="utf-8"))
        port = int(webui.get("port") or 6099)
        token = str(webui.get("token") or "")
        if not token or not account.isdigit():
            return False
        digest = hashlib.sha256((token + ".napcat").encode("utf-8")).hexdigest()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/auth/login",
            data=json.dumps({"hash": digest}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=8) as response:
            credential = (json.load(response).get("data") or {}).get("Credential")
        if not credential:
            return False
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/QQLogin/SetQuickLogin",
            data=json.dumps({"uin": int(account)}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + credential}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response).get("code") == 0
    except Exception:
        return False


def wait_for_login(account, timeout=90, poll_seconds=2):
    """Wait for auto-login, then actively retry quick login when needed."""
    deadline = time.monotonic() + timeout
    next_quick_login = time.monotonic() + 10
    last_error = None
    while time.monotonic() < deadline:
        try:
            address, token = endpoint()
            check_login(address, token, account)
            return address, token
        except Exception as exc:
            last_error = exc
        if time.monotonic() >= next_quick_login:
            webui_quick_login(account)
            next_quick_login = time.monotonic() + 20
        time.sleep(poll_seconds)
    raise RuntimeError("QQ 自动快速登录超时") from last_error


def session_check(account):
    """Exercise start/login/stop without sending or touching daily state."""
    stopped = False
    try:
        start_container()
        wait_for_login(account)
        return "session-ready"
    finally:
        try:
            stop_container()
            stopped = True
        finally:
            if stopped:
                print("QQ 会话自检通过：已自动登录并退出；未发送消息")


def run_due(now=None, dry_run=False, check_session=False):
    now = now or datetime.now(BEIJING)
    loaded = settings()
    if loaded is None:
        return "disabled"
    config, when, targets, message = loaded
    if not dry_run and not check_session and now.strftime("%H:%M") != when[:5]:
        return "not-due"
    own = next((SKILL / "qq-data/config").glob("onebot11_*.json"), None)
    if own is None:
        raise ValueError("QQ 尚未扫码登录")
    account = own.stem.removeprefix("onebot11_")
    if dry_run:
        address, token = endpoint()
        check_login(address, token, account)
        return f"ready:{len(targets)}"
    if check_session:
        return session_check(account)
    if fcntl is None:
        raise RuntimeError("QQ 定时运行仅支持 Linux")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.open("a+", encoding="utf-8") as state_file:
        os.chmod(STATE, 0o600)
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state_file.seek(0)
        try:
            state = json.load(state_file)
        except ValueError:
            state = {}
        today = now.strftime("%Y-%m-%d")
        if state.get("day") == today:
            return "already-ran"
        state = {"day": today, "startedAt": now.isoformat(), "done": False}
        _save(state_file, state)
        succeeded = failed = 0
        recipients = []
        session_stopped = False
        try:
            start_container()
            address, token = wait_for_login(account)
            names = friend_names(address, token)
            for target in targets:
                try:
                    result = onebot("send_private_msg", {"user_id": int(target), "message": message}, address, token)
                    message_id = result.get("message_id")
                    if not message_id:
                        raise RuntimeError("QQ 发送未返回消息编号")
                    if not confirm_sent(target, message_id, account, message, address, token):
                        raise RuntimeError("聊天记录未确认该消息，为避免重复不会自动重发")
                    succeeded += 1
                    recipients.append({"target": target, "name": names.get(target, target),
                                       "message": message, "confirmed": True, "error": None})
                except Exception as exc:
                    failed += 1
                    recipients.append({"target": target, "name": names.get(target, target),
                                       "message": message, "confirmed": False, "error": str(exc)})
                    print(f"QQ 好友发送失败：{type(exc).__name__}", file=sys.stderr)
        except Exception as exc:
            failed = len(targets)
            recipients = [{"target": target, "name": target, "message": message,
                           "confirmed": False, "error": "QQ 自动登录或本机接口不可用"}
                          for target in targets]
            print(f"QQ 自动登录或本机接口不可用：{type(exc).__name__}", file=sys.stderr)
        finally:
            try:
                stop_container()
                session_stopped = True
            except Exception as exc:
                print(f"QQ 任务后自动退出失败：{type(exc).__name__}", file=sys.stderr)
        state.update(done=True, succeeded=succeeded, failed=failed,
                     sessionStopped=session_stopped,
                     endedAt=datetime.now(BEIJING).isoformat())
        _save(state_file, state)
        save_result({
            "platform": "qq", "day": today,
            "finished_at": datetime.now(BEIJING).isoformat(),
            "status": "success" if failed == 0 and session_stopped else "failed",
            "session_stopped": session_stopped,
            "recipients": recipients,
        })
        stats = config.setdefault("stats", {})
        stats.update(friendSparkCompletedAt=int(datetime.now(BEIJING).timestamp() * 1000),
                     friendSparkSucceeded=succeeded, friendSparkFailed=failed,
                     friendSparkSessionStopped=session_stopped)
        config["friendSpark_message"] = message
        temp = QQ_CONFIG.with_name(QQ_CONFIG.name + ".tmp")
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temp, 0o600)
        temp.replace(QQ_CONFIG)
        cleanup = "已退出" if session_stopped else "退出失败"
        print(f"QQ 每日任务完成：成功 {succeeded}，失败 {failed}；{cleanup}")
        return "ok" if failed == 0 and session_stopped else "failed"


def _save(stream, value):
    stream.seek(0)
    stream.truncate()
    json.dump(value, stream, ensure_ascii=False)
    stream.flush()
    os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--session-check", action="store_true",
                      help="启动、自动快登并退出，不发送消息")
    args = parser.parse_args()
    try:
        result = run_due(dry_run=args.dry_run, check_session=args.session_check)
    except Exception as exc:
        print(f"QQ 检查失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if result == "ready:1" or result.startswith("ready:"):
        print(f"QQ 只读验证通过，目标 {result.split(':')[1]} 位；未发送")
    return 1 if result == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
