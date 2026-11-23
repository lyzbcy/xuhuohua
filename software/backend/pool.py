# -*- coding: utf-8 -*-
"""共享话术池：QQ 和抖音共用同一份话术（用户规范：话术库统一）。
存储：续火花/config/message_pool.json
抖音 config.json 的 random.choices 和 QQ 的发送内容都从这里生成。
"""
import json
import hashlib
import random
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from backend import logger
from backend.paths import DOUYIN_CONFIG, DOUYIN_DIR, DOUYIN_STICKERS, FROZEN, PROJECT_ROOT, UI_STICKER_DIR

if not FROZEN:
    sys.path.insert(0, str(DOUYIN_DIR))
from app.sticker_transfer import MAX_STICKER_BYTES, compress_png

POOL_FILE = PROJECT_ROOT / "config" / "message_pool.json"
DEFAULT_TEXTS = (
    "续火花 续火花 续火花",
    "来续个火花 🔥",
    "今天的火花续一下！",
)
DEFAULT_STICKER = "周三涵做表情154-超开心.png"
_lock = threading.Lock()

# 老配置没有签名偏好时沿用原有默认值。
SIGNATURE = "来自捞鱼自动续火花"


def _default_pool() -> dict:
    return {"texts": [], "stickers": []}   # stickers 存文件名（stickers-lb/xx.png）


def _seed_from_douyin_config() -> dict:
    """首次迁移：从抖音 config.json 现有 choices 提取池子。"""
    pool = _default_pool()
    try:
        cfg = json.loads(DOUYIN_CONFIG.read_text(encoding="utf-8"))
        msgs = (cfg.get("targets") or [{}])[0].get("messages") or []
        rand = next((m for m in msgs if m.get("type") == "random"), None)
        for c in (rand or {}).get("choices", []):
            if c.get("type") == "text":
                pool["texts"].append(c.get("content", ""))
            elif c.get("type") == "image":
                pool["stickers"].append(Path(c.get("path", "")).name)
        pool["texts"] = [t for t in pool["texts"] if t]
        pool["stickers"] = [s for s in pool["stickers"] if s]
    except (OSError, json.JSONDecodeError, IndexError):
        pass
    if not pool["texts"]:
        pool["texts"] = list(DEFAULT_TEXTS)
    if not pool["stickers"]:
        default_sticker = DOUYIN_STICKERS / DEFAULT_STICKER
        if not default_sticker.is_file():
            bundled = UI_STICKER_DIR / DEFAULT_STICKER
            if bundled.is_file():
                DOUYIN_STICKERS.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bundled, default_sticker)
        if default_sticker.is_file():
            pool["stickers"].append(DEFAULT_STICKER)
    return pool


def get_pool() -> dict:
    with _lock:
        if not POOL_FILE.exists():
            pool = _seed_from_douyin_config()
            save_pool(pool["texts"], pool["stickers"], log=False)
            return pool
        try:
            data = json.loads(POOL_FILE.read_text(encoding="utf-8"))
            return {"texts": data.get("texts", []),
                    "stickers": data.get("stickers", [])}
        except (OSError, json.JSONDecodeError):
            return _default_pool()


def save_pool(texts: list, stickers: list, log: bool = True) -> dict:
    texts = [t.strip() for t in texts if t and t.strip()]
    stickers = [s.strip() for s in stickers if s and s.strip()]
    # 过滤掉磁盘上已不存在的表情文件
    if DOUYIN_STICKERS.exists():
        existing = {p.name for p in DOUYIN_STICKERS.glob("*.png")}
        stickers = [s for s in stickers if s in existing]
    POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
    POOL_FILE.write_text(json.dumps({"texts": texts, "stickers": stickers},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    if log:
        logger.ok("[话术库] 共享话术池已保存（{0} 条文字 / {1} 个表情，QQ 与抖音共用）".format(
            len(texts), len(stickers)), source="pool")
    return {"ok": True, "texts": len(texts), "stickers": len(stickers)}


def pick_random() -> dict:
    """抽取原始话术，发送端按平台决定如何渲染签名。"""
    pool = get_pool()
    bag = ([{"type": "text", "content": t} for t in pool["texts"]]
           + [{"type": "image", "file": s} for s in pool["stickers"]])
    if not bag:
        return {"type": "text", "content": "续火花啦 🔥"}
    item = random.choice(bag)
    if item["type"] == "image":
        item["abs_path"] = str(DOUYIN_STICKERS / item["file"])
    return item


def signature_text(settings: dict) -> str:
    if settings.get("signature_enabled") is False:
        return ""
    return str(settings.get("signature_text") or "").strip() or SIGNATURE


def qq_message(item: dict, signature: str) -> str:
    if item["type"] == "image":
        path = Path(item["abs_path"])
        if path.stat().st_size >= MAX_STICKER_BYTES:
            original = path.read_bytes()
            cache = PROJECT_ROOT / "config" / "sticker-transfer"
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / (hashlib.sha256(original).hexdigest() + ".png")
            if not path.is_file() or path.stat().st_size >= MAX_STICKER_BYTES:
                payload = compress_png(original)
                with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
                    pending = Path(stream.name)
                    try:
                        stream.write(payload)
                        stream.close()
                        pending.replace(path)
                    finally:
                        pending.unlink(missing_ok=True)
        message = "[CQ:image,file=file:///" + path.as_posix() + "]"
        separator = " "
    else:
        message = item["content"]
        separator = "\n"
        base, _, tail = message.rpartition(separator)
        if base and tail in {SIGNATURE, "——" + SIGNATURE, "——来自楼宇自动续火花", signature}:
            message = base
    return message + separator + signature if signature else message


def douyin_choices() -> list:
    """生成抖音 config.json 用的 choices 数组（相对路径，保持原文）。
    签名不内嵌：由 save_friends 统一追加为独立的第二条消息（图文一致）。"""
    pool = get_pool()
    choices = [{"type": "text", "content": t} for t in pool["texts"]]
    choices += [{"type": "image", "path": "stickers-lb/" + s} for s in pool["stickers"]]
    return choices


def douyin_signature_message() -> dict:
    """抖音侧的签名消息（作为图片消息后的独立一条）。"""
    return {"type": "text", "content": SIGNATURE}
