"""Send the configured QQ friend message once per Beijing day through local OneBot HTTP."""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import message_policy

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
SIGNATURE = "来自捞鱼自动续火花"
OLD_SIGNATURES = ("——来自楼宇自动续火花", "——来自捞鱼自动续火花")


class QQLoginExpired(RuntimeError):
    """The saved QQ ticket was rejected; another quick-login loop cannot renew it."""


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
    if onebot("get_status", {}, address, token).get("online") is not True:
        raise RuntimeError("QQ 当前不在线")


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


def image_reference(item, message_id, own_account, tail):
    if not isinstance(item, dict) or str(item.get("message_id", item.get("msgId", ""))) != str(message_id):
        return None
    sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
    segments = item.get("message")
    if str(sender.get("user_id", item.get("user_id", ""))) != str(own_account) or not isinstance(segments, list):
        return None
    images, parts = [], []
    for segment in segments:
        data = segment.get("data") if isinstance(segment, dict) else None
        if not isinstance(data, dict):
            return None
        if segment.get("type") == "image" and isinstance(data.get("file"), str) and data["file"]:
            images.append(data["file"])
        elif segment.get("type") == "text" and isinstance(data.get("text"), str):
            parts.append(data["text"])
        else:
            return None
    return images[0] if len(images) == 1 and "".join(parts) == tail else None


def confirm_sent(target, message_id, own_account, expected_message, address, token,
                 attempts=5, poll_seconds=1, image_tail=None):
    for attempt in range(attempts):
        data = onebot("get_friend_msg_history", {"user_id": int(target), "count": 20}, address, token)
        if image_tail is None and history_confirms(data, message_id, own_account, expected_message):
            return True
        if image_tail is not None:
            for item in _history_messages(data):
                reference = image_reference(item, message_id, own_account, image_tail)
                if reference:
                    detail = onebot("get_msg", {"message_id": message_id}, address, token)
                    if image_reference(detail, message_id, own_account, image_tail) == reference:
                        return True
        if attempt + 1 < attempts:
            time.sleep(poll_seconds)
    return False


def recent_history(target, address, token):
    return _history_messages(onebot("get_friend_msg_history", {"user_id": int(target), "count": 20}, address, token))


def image_matches(reference, digest, address, token):
    image = onebot("get_image", {"file": reference}, address, token)
    path = PurePosixPath(image.get("file") or "")
    root = PurePosixPath("/app/.config/QQ")
    if not path.is_relative_to(root) or path == root or ".." in path.parts:
        return False
    checked = subprocess.run(["docker", "exec", "xuhuohua-napcat", "sha256sum", "--", str(path)],
                             capture_output=True, text=True, timeout=8)
    return checked.returncode == 0 and checked.stdout.startswith(digest + " ")


def recover_image_id(target, account, image_tail, digest, before, started, address, token, attempts=5):
    for attempt in range(attempts):
        candidates = {}
        for item in recent_history(target, address, token):
            if not isinstance(item, dict):
                continue
            message_id = item.get("message_id", item.get("msgId"))
            stamp = item.get("time")
            if not message_id or str(message_id) in before or type(stamp) not in (float, int):
                continue
            if not started - 1 <= stamp <= started + 35:
                continue
            reference = image_reference(item, message_id, account, image_tail)
            if reference:
                candidates[message_id] = reference
        if len(candidates) > 1:
            return None
        if candidates:
            message_id, reference = next(iter(candidates.items()))
            detail = onebot("get_msg", {"message_id": message_id}, address, token)
            if (image_reference(detail, message_id, account, image_tail) == reference
                    and image_matches(reference, digest, address, token)):
                return message_id
        if attempt + 1 < attempts:
            time.sleep(2)
    return None


def send_checked(target, payload, summary, image_tail, account, address, token):
    before = set()
    if image_tail is not None:
        sent_image = payload[0]["data"]["file"].removeprefix("base64://")
        digest = hashlib.sha256(base64.b64decode(sent_image)).hexdigest()
        before = {str(item.get("message_id", item.get("msgId"))) for item in
                  recent_history(target, address, token) if isinstance(item, dict)}
    started = time.time()
    try:
        result = onebot("send_private_msg", {"user_id": int(target), "message": payload}, address, token)
    except (OSError, RuntimeError):
        if image_tail is None:
            raise
        result = {}
    message_id = result.get("message_id")
    if message_id:
        if confirm_sent(target, message_id, account, summary, address, token, image_tail=image_tail):
            return
    elif image_tail is not None:
        if recover_image_id(target, account, image_tail, digest, before, started, address, token):
            return
    else:
        raise RuntimeError("QQ 发送未返回消息编号")
    raise RuntimeError("聊天记录未确认该消息，为避免重复不会自动重发")


def save_result(value):
    temp = RESULT.with_name(RESULT.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(RESULT)


def _compose(*args):
    files = ["-f", str(COMPOSE)]
    local = SKILL / "compose.qq.local.yaml"
    if local.is_file():
        files += ["-f", str(local)]
    return subprocess.run(
        ["docker", "compose", *files, "--project-directory", str(SKILL), *args],
        capture_output=True, text=True, check=True, timeout=90)


def start_container():
    """Start the QQ engine only for the current scheduled session."""
    _compose("up", "-d", "napcat")


def stop_container():
    """Terminate the QQ application first; the image's PID 1 does not forward TERM."""
    inspected = subprocess.run(
        ["docker", "inspect", "xuhuohua-napcat"], capture_output=True,
        text=True, check=True, timeout=15)
    if not json.loads(inspected.stdout)[0]["State"]["Running"]:
        return
    processes = subprocess.run(
        ["docker", "exec", "xuhuohua-napcat", "ps", "-eo", "pid,args"],
        capture_output=True, text=True, check=True, timeout=15)
    pids = []
    for line in processes.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and re.fullmatch(
                r"/opt/QQ/qq --no-sandbox(?: -q [1-9]\d{4,14})?", fields[1]):
            pids.append(fields[0])
    if len(pids) != 1:
        raise RuntimeError("QQ 主进程不唯一，未执行强制终止")
    subprocess.run(["docker", "exec", "xuhuohua-napcat", "kill", "-TERM", pids[0]],
                   capture_output=True, text=True, check=True, timeout=15)
    # TERM reaches Electron directly, allowing its login database/WAL to flush.
    _compose("stop", "-t", "20", "napcat")
    inspected = subprocess.run(
        ["docker", "inspect", "xuhuohua-napcat"], capture_output=True,
        text=True, check=True, timeout=15)
    state = json.loads(inspected.stdout)[0]["State"]
    if state["Running"] or state.get("ExitCode") != 0:
        raise RuntimeError("QQ 未正常退出，快登凭证持久化未验证")


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
            data=json.dumps({"uin": account}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + credential}, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
        if result.get("code") != 0 and any(
                phrase in str(result.get("message", ""))
                for phrase in ("登录态已失效", "用户身份已失效")):
            raise QQLoginExpired("QQ 快速登录授权已失效，需要扫码确认")
        return result.get("code") == 0
    except QQLoginExpired:
        raise
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
    try:
        start_container()
        wait_for_login(account)
    finally:
        stop_container()
    print("QQ 会话自检通过：已自动登录并退出；未发送消息")
    return "session-ready"


def run_due(now=None, dry_run=False, check_session=False):
    now = now or datetime.now(BEIJING)
    loaded = settings()
    if loaded is None:
        return "disabled"
    config, when, targets, message = loaded
    if not dry_run and not check_session and now.strftime("%H:%M") != when[:5]:
        return "not-due"
    if not dry_run and not check_session and (SKILL / "qq-maintenance").exists():
        return "maintenance"
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
    policy = message_policy.load(SKILL)
    payload, image_tail = message, None
    if policy is not None:
        payload, message, image_tail = message_policy.qq_payload(message, policy, SKILL)
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
                    send_checked(target, payload, message, image_tail, account, address, token)
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
            reason = ("QQ 快速登录授权已失效，需要扫码确认" if isinstance(exc, QQLoginExpired)
                      else "QQ 自动登录或本机接口不可用")
            recipients = [{"target": target, "name": target, "message": message,
                           "confirmed": False, "error": reason}
                          for target in targets]
            print(f"{reason}：{type(exc).__name__}", file=sys.stderr)
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
        if policy is None:
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
    if result == "maintenance":
        print("QQ 正在维护验证，未发送且未修改每日去重记录")
    return 1 if result == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
