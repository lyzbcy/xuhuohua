"""Send the configured QQ friend message once per Beijing day through local OneBot HTTP."""

import argparse
import json
import os
import re
import subprocess
import sys
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
BEIJING = timezone(timedelta(hours=8))


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


def run_due(now=None, dry_run=False):
    now = now or datetime.now(BEIJING)
    loaded = settings()
    if loaded is None:
        return "disabled"
    config, when, targets, message = loaded
    if not dry_run and now.strftime("%H:%M") != when[:5]:
        return "not-due"
    own = next((SKILL / "qq-data/config").glob("onebot11_*.json"), None)
    if own is None:
        raise ValueError("QQ 尚未扫码登录")
    account = own.stem.removeprefix("onebot11_")
    if dry_run:
        address, token = endpoint()
        check_login(address, token, account)
        return f"ready:{len(targets)}"
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
        try:
            address, token = endpoint()
            check_login(address, token, account)
            for target in targets:
                try:
                    result = onebot("send_private_msg", {"user_id": int(target), "message": message}, address, token)
                    if not result.get("message_id"):
                        raise RuntimeError("QQ 发送未返回消息编号")
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    print(f"QQ 好友发送失败：{type(exc).__name__}", file=sys.stderr)
        except Exception as exc:
            failed = len(targets)
            print(f"QQ 登录或本机接口不可用：{type(exc).__name__}", file=sys.stderr)
        state.update(done=True, succeeded=succeeded, failed=failed, endedAt=datetime.now(BEIJING).isoformat())
        _save(state_file, state)
        stats = config.setdefault("stats", {})
        stats.update(friendSparkCompletedAt=int(datetime.now(BEIJING).timestamp() * 1000),
                     friendSparkSucceeded=succeeded, friendSparkFailed=failed)
        temp = QQ_CONFIG.with_name(QQ_CONFIG.name + ".tmp")
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temp, 0o600)
        temp.replace(QQ_CONFIG)
        print(f"QQ 每日任务完成：成功 {succeeded}，失败 {failed}")
        return "ok" if failed == 0 else "failed"


def _save(stream, value):
    stream.seek(0)
    stream.truncate()
    json.dump(value, stream, ensure_ascii=False)
    stream.flush()
    os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = run_due(dry_run=args.dry_run)
    except Exception as exc:
        print(f"QQ 检查失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if result == "ready:1" or result.startswith("ready:"):
        print(f"QQ 只读验证通过，目标 {result.split(':')[1]} 位；未发送")
    return 1 if result == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
