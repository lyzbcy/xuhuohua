"""Optional post-run notifications through the cloud Agent's WeCom channel.

The private notify-command file contains one absolute executable path. The
executable reads one UTF-8 message on stdin and sends it through the Agent's
already configured WeCom long-connection bot. No bot credentials live here.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Lets Windows CI test the pure result parser; runtime is Linux.
    fcntl = None

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
COMMAND_FILE = SKILL / "notify-command"
STATE_FILE = SKILL / "notify-state.json"
QQ_CONFIG = SKILL / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")


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


def send(command: Path, message: str) -> bool:
    try:
        result = subprocess.run([str(command)], input=message + "\n", text=True,
                                encoding="utf-8",
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"企业微信通知发送失败：{type(exc).__name__}", file=sys.stderr)
        return False
    if result.returncode:
        print(f"企业微信通知发送失败，适配命令退出码 {result.returncode}", file=sys.stderr)
        return False
    return True


def qq_result(config: dict, now: datetime) -> tuple[str, str] | None:
    """Return a terminal result for today's configured QQ batch, if known."""
    if not config.get("enabled") or not config.get("friendSpark_enable"):
        return None
    when = str(config.get("friendSpark_time", ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", when):
        return None
    hour, minute, second = map(int, when.split(":"))
    due = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if now < due:
        return None
    stats = config.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    try:
        completed_ms = int(stats.get("friendSparkCompletedAt") or 0)
        succeeded = int(stats.get("friendSparkSucceeded") or 0)
        failed = int(stats.get("friendSparkFailed") or 0)
    except (TypeError, ValueError):
        completed_ms = succeeded = failed = 0
    if completed_ms > 0:
        completed = datetime.fromtimestamp(completed_ms / 1000, BEIJING)
        if due <= completed <= now and succeeded + failed > 0:
            status = "成功" if failed == 0 else "失败"
            return status, f"成功 {succeeded}，失败 {failed}；详见 NapCat 日志"
    if now >= due + timedelta(minutes=60):
        return "失败", "计划时间后 60 分钟仍无整批完成记录，请检查登录态、容器和插件日志"
    return None


def notify_qq(command: Path, now: datetime) -> int:
    if fcntl is None:
        raise RuntimeError("QQ 结果通知仅支持 Linux")
    if not QQ_CONFIG.is_file():
        return 0
    try:
        config = json.loads(QQ_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"QQ 通知状态读取失败：{type(exc).__name__}", file=sys.stderr)
        return 1
    if not isinstance(config, dict):
        print("QQ 通知状态读取失败：配置不是 JSON 对象", file=sys.stderr)
        return 1
    outcome = qq_result(config, now)
    if outcome is None:
        return 0
    status, detail = outcome
    # Cron can overlap when a notification transport stalls. Hold one lock
    # until the result is sent and the day's deduplication marker is saved.
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("a+", encoding="utf-8") as state_file:
        os.chmod(STATE_FILE, 0o600)
        fcntl.flock(state_file, fcntl.LOCK_EX)
        state_file.seek(0)
        try:
            state = json.load(state_file)
        except ValueError:
            state = {}
        day = now.strftime("%Y-%m-%d")
        if state.get("qq_notified_day") == day:
            return 0
        message = f"续火花 QQ 每日任务{status}｜{day} 北京时间｜{detail}"
        if not send(command, message):
            return 1
        state["qq_notified_day"] = day
        state_file.seek(0)
        state_file.truncate()
        json.dump(state, state_file, ensure_ascii=False)
        state_file.flush()
        os.fsync(state_file.fileno())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("douyin", "qq", "test"))
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()
    try:
        command = command_path()
    except (OSError, ValueError) as exc:
        print(f"企业微信通知未启用：{exc}", file=sys.stderr)
        return 1
    if command is None:
        if args.platform == "test":
            print("尚未配置企业微信长连接通知适配命令", file=sys.stderr)
            return 2
        return 0  # User declined optional WeCom setup.
    now = datetime.now(BEIJING)
    if args.platform == "test":
        return 0 if send(command, "续火花企业微信通知测试｜连接正常，不会触发续火花发送") else 1
    if args.platform == "qq":
        return notify_qq(command, now)
    if args.exit_code is None:
        parser.error("抖音通知需要 --exit-code")
    status = "成功" if args.exit_code == 0 else "失败"
    detail = "已执行完毕" if args.exit_code == 0 else f"退出码 {args.exit_code}，请检查 logs/cron.log"
    message = f"续火花 抖音每日任务{status}｜{now:%Y-%m-%d %H:%M} 北京时间｜{detail}"
    return 0 if send(command, message) else 1


if __name__ == "__main__":
    raise SystemExit(main())
