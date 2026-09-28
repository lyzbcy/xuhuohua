"""Safely configure one daily QQ friend spark task; does not send messages."""
import argparse
import json
import os
import re
from pathlib import Path


def configure(path: Path, when: str, targets: str, message: str) -> dict:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", when):
        raise ValueError("时间必须是 HH:MM")
    friends = [item.strip() for item in targets.split(",") if item.strip()]
    if not friends or not all(re.fullmatch(r"[1-9]\d{4,14}", item) for item in friends):
        raise ValueError("请提供逗号分隔的有效 QQ 号")
    if not message.strip():
        raise ValueError("话术不能为空")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("现有 QQ 配置不是 JSON 对象")
    data.update(enabled=True, friendSpark_enable=True,
                friendSpark_time=when + ":00",
                friendSpark_targets=",".join(dict.fromkeys(friends)),
                friendSpark_message=message)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    return {"count": len(dict.fromkeys(friends)), "time": data["friendSpark_time"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time", required=True, help="北京时间 HH:MM")
    parser.add_argument("--targets", required=True, help="逗号分隔 QQ 号")
    parser.add_argument("--message", default="✨", help="本地固定话术")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
    result = configure(path, args.time, args.targets, args.message)
    print(f"QQ 好友任务已配置：{result['count']} 位，{result['time']} 北京时间；没有发送消息")


if __name__ == "__main__":
    main()
