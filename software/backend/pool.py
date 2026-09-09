# -*- coding: utf-8 -*-
"""共享话术池：QQ 和抖音共用同一份话术（用户规范：话术库统一）。
存储：续火花/config/message_pool.json
抖音 config.json 的 random.choices 和 QQ 的发送内容都从这里生成。
"""
import json
import random
import threading
from pathlib import Path

from backend import logger
from backend.paths import DOUYIN_CONFIG, DOUYIN_STICKERS, PROJECT_ROOT

POOL_FILE = PROJECT_ROOT / "config" / "message_pool.json"
_lock = threading.Lock()


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
    """随机抽一条：{"type":"text","content":...} 或 {"type":"image","abs_path":...}。"""
    pool = get_pool()
    bag = ([{"type": "text", "content": t} for t in pool["texts"]]
           + [{"type": "image", "file": s} for s in pool["stickers"]])
    if not bag:
        return {"type": "text", "content": "续火花啦 🔥"}
    item = random.choice(bag)
    if item["type"] == "image":
        item["abs_path"] = str(DOUYIN_STICKERS / item["file"])
    return item


def douyin_choices() -> list:
    """生成抖音 config.json 用的 choices 数组（相对路径）。"""
    pool = get_pool()
    choices = [{"type": "text", "content": t} for t in pool["texts"]]
    choices += [{"type": "image", "path": "stickers-lb/" + s} for s in pool["stickers"]]
    return choices
