"""Import and apply the desktop text, signature and sticker library."""
import argparse
import base64
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
POLICY_FILE = "message-policy.json"
ASSET_DIR = "message-policy-assets"
PNG_HEADER = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE = 2_000_000
MAX_IMAGES_TOTAL = 24_000_000
DEFAULT_SIGNATURE = "来自捞鱼自动续火花"
OLD_SIGNATURES = {DEFAULT_SIGNATURE, "——" + DEFAULT_SIGNATURE, "——来自楼宇自动续火花"}
DEFAULT_TEXTS = ("续火花 续火花 续火花", "来续个火花 🔥", "今天的火花续一下！")


def parse(raw):
    if len(raw) > 64_000:
        raise ValueError("话术配置超过大小限制")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict) or set(value) != {"texts", "signature_enabled", "signature_text"}:
        raise ValueError("需要桌面导出的文字和签名配置")
    enabled, signature, texts = value["signature_enabled"], value["signature_text"], value["texts"]
    if type(enabled) is not bool or not isinstance(signature, str) or not isinstance(texts, list):
        raise ValueError("话术或签名字段类型无效")
    signature = signature.strip()
    if len(signature) > 120 or any(tag in signature for tag in ("\r", "\n", "[CQ:")):
        raise ValueError("签名应为单行普通文字，最多 120 字")
    if len(texts) > 100 or any(not isinstance(text, str) or not text.strip() or
                               len(text) > 500 or "[CQ:" in text for text in texts):
        raise ValueError("话术池最多 100 条，每条需要 1–500 字普通文字")
    return {"texts": list(dict.fromkeys(text.strip() for text in texts)),
            "signature_enabled": enabled, "signature_text": signature}


def load(skill=SKILL):
    try:
        with (skill / POLICY_FILE).open("rb") as stream:
            raw = stream.read(64_001)
    except FileNotFoundError:
        return None
    if len(raw) > 64_000:
        raise ValueError("话术配置超过大小限制")
    value = json.loads(raw.decode("utf-8-sig"))
    return parse_library(value) if isinstance(value, dict) and "version" in value else parse(raw)


def parse_library(value):
    if (not isinstance(value, dict) or set(value) != {"version", "policy", "selected_stickers", "stickers"}
            or type(value["version"]) is not int or value["version"] != 1):
        raise ValueError("同步包版本不受支持")
    assets, selected = value["stickers"], value["selected_stickers"]
    if not isinstance(assets, dict) or len(assets) > 100 or not isinstance(selected, list):
        raise ValueError("表情清单无效")
    for name, digest in assets.items():
        if (not isinstance(name, str) or len(name) > 180 or not name.endswith(".png")
                or any(c in name for c in ("/", "\\", ":", "\x00", "\r", "\n"))
                or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise ValueError("表情名称或校验值无效")
    if len(selected) > len(assets) or any(not isinstance(name, str) or name not in assets for name in selected):
        raise ValueError("勾选的表情缺少原图")
    return {"version": 1, "policy": parse(json.dumps(value["policy"], ensure_ascii=False).encode("utf-8")),
            "stickers": assets, "selected_stickers": list(dict.fromkeys(selected))}


def atomic_write(dest, data):
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".message-policy-", delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)


def import_library(file, skill=SKILL):
    if file.stat().st_size > MAX_IMAGES_TOTAL + 1_000_000:
        raise ValueError("同步包超过大小限制")
    with zipfile.ZipFile(file) as archive:
        entries = archive.infolist()
        members = {entry.filename: entry for entry in entries}
        manifest = members.get("manifest.json")
        if len(entries) != len(members) or not manifest or manifest.file_size > 64_000:
            raise ValueError("同步包清单无效")
        library = parse_library(json.loads(archive.read(manifest)))
        expected = {"stickers/" + name for name in library["stickers"]}
        if set(members) != expected | {"manifest.json"}:
            raise ValueError("同步包文件与清单不一致")
        if (sum(members[name].file_size for name in expected) > MAX_IMAGES_TOTAL
                or any(members[name].file_size > MAX_IMAGE for name in expected)):
            raise ValueError("表情超过大小限制")
        blobs = {}
        for name, digest in library["stickers"].items():
            blob = archive.read(members["stickers/" + name])
            if not blob.startswith(PNG_HEADER) or hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError("表情文件与清单校验不一致")
            blobs[digest] = blob
    directory = skill / ASSET_DIR
    directory.mkdir(mode=0o700, exist_ok=True)
    for digest, blob in blobs.items():
        atomic_write(directory / (digest + ".png"), blob)
    save(library, skill)
    return library


def selected_assets(settings, skill):
    paths = []
    for name in settings.get("selected_stickers", []):
        digest = settings["stickers"][name]
        path = (skill / ASSET_DIR / (digest + ".png")).resolve()
        if not path.is_file():
            raise ValueError("云端缺少已勾选的表情，请重新导入同步包")
        paths.append((name, path))
    return paths


def signature(policy):
    return (policy["signature_text"] or DEFAULT_SIGNATURE) if policy["signature_enabled"] else ""


def qq_message(message, policy):
    value = random.choice(policy["texts"]) if policy["texts"] else message
    return signed_text(value, policy)


def signed_text(value, policy):
    value = value.rstrip()
    tail = signature(policy)
    for suffix in OLD_SIGNATURES | {tail}:
        if suffix and value.endswith("\n" + suffix):
            value = value[:-len(suffix)].rstrip()
            break
    return value + "\n" + tail if tail and value != tail else value


def qq_payload(legacy, settings, skill):
    policy = settings.get("policy", settings)
    images = selected_assets(settings, skill)
    if not images:
        text = qq_message(legacy, policy)
        return text, text, None
    kind, choice = random.choice([("text", text) for text in policy["texts"]]
                                + [("image", image) for image in images])
    if kind == "text":
        text = signed_text(choice, policy)
        return text, text, None
    name, path = choice
    with path.open("rb") as stream:
        blob = stream.read(MAX_IMAGE + 1)
    if len(blob) > MAX_IMAGE or hashlib.sha256(blob).hexdigest() != settings["stickers"][name]:
        raise ValueError("云端表情文件校验失败，请重新导入同步包")
    image = base64.b64encode(blob).decode("ascii")
    tail = signature(policy)
    payload = [{"type": "image", "data": {"file": "base64://" + image}}]
    if tail:
        payload.append({"type": "text", "data": {"text": tail}})
    return payload, "[表情] " + name + ("\n" + tail if tail else ""), tail


def douyin_config(original, settings, skill=SKILL):
    policy = settings.get("policy", settings)
    choices = ([{"type": "text", "content": text} for text in policy["texts"]]
               + [{"type": "image", "path": str(path)} for _, path in selected_assets(settings, skill)])
    source = original.get("targets")
    if source is None and "friends" in original:
        source = [{"name": name, "messages": original["messages"]} for name in original["friends"]]
    if not isinstance(source, list) or not source:
        raise ValueError("没有可应用共享话术的抖音目标")
    tail = signature(policy)
    targets = []
    for target in source:
        messages = list(target["messages"])
        if choices:
            messages = [{"type": "random", "choices": choices}]
        else:
            while len(messages) > 1 and messages[-1].get("type") == "text" and (
                messages[-1].get("content", messages[-1].get("value", "")).strip()
                in (OLD_SIGNATURES | {tail})
            ):
                messages.pop()
        if tail and not any(m.get("type") == "text" and m.get("content", m.get("value")) == tail
                            for m in messages):
            messages.append({"type": "text", "content": tail})
        targets.append({**target, "messages": messages})
    return {**original, "targets": targets}


def run_douyin(arguments):
    policy = load()
    command = [sys.executable, *arguments]
    if policy is None:
        os.execv(sys.executable, command)
    sys.path.insert(0, str(Path.cwd()))
    from app.config import load_settings
    source = load_settings().task_config_path.resolve()
    current = douyin_config(json.loads(source.read_text(encoding="utf-8")), policy)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".message-policy-",
                                     suffix=".json", dir=source.parent, delete=False) as stream:
        pending = Path(stream.name)
        json.dump(current, stream, ensure_ascii=False)
    try:
        env = dict(os.environ, TASK_CONFIG=str(pending), XUHUOHUA_SIGNATURE="",
                   XUHUOHUA_DESKTOP_SIGNATURE_MODE="")
        return subprocess.call(command, env=env)
    finally:
        pending.unlink(missing_ok=True)


def save(policy, skill=SKILL):
    data = json.dumps(policy, ensure_ascii=False, indent=2).encode("utf-8")
    if len(data) > 64_000:
        raise ValueError("话术配置超过大小限制")
    atomic_write(skill / POLICY_FILE, data)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "run-douyin":
        return run_douyin(sys.argv[2:])
    parser = argparse.ArgumentParser(description="配置云端话术、签名和精选表情")
    parser.add_argument("action", choices=("status", "defaults", "import"))
    parser.add_argument("file", nargs="?", type=Path)
    args = parser.parse_args()
    if (args.action == "import") != (args.file is not None):
        parser.error("import 需要指定桌面导出的 ZIP 或旧版 JSON 文件")
    if args.action == "import":
        if args.file.suffix.lower() == ".zip":
            import_library(args.file)
        else:
            with args.file.open("rb") as stream:
                save(parse(stream.read(64_001)))
    elif args.action == "defaults":
        save({"texts": list(DEFAULT_TEXTS), "signature_enabled": True, "signature_text": ""})
    policy = load()
    if policy is None:
        print("云端沿用各平台原配置，未启用共享话术设置。")
    else:
        text = policy.get("policy", policy)
        print(f"云端共享配置已启用：{len(text['texts'])} 条文字，"
              f"{len(policy.get('stickers', {}))} 张精选表情，"
              f"{len(selected_assets(policy, SKILL))} 张已勾选，签名{'开启' if signature(text) else '关闭'}。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile):
        raise SystemExit("共享话术配置无效或无法读取，请检查配置；任务未继续。")
