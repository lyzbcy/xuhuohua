# -*- coding: utf-8 -*-
"""每日话术轮换：从共享话术池随机抽一条写进 QQ 插件配置，
让插件到点发的内容每天不一样（由计划任务「续火花-QQ话术轮换」每日凌晨调用）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import logger, qq  # noqa: E402


def main() -> int:
    cfg = qq.get_plugin_config()
    if not cfg.get("friendSpark_enable") or not (cfg.get("friendSpark_targets") or "").strip():
        logger.info("[轮换] QQ 好友续火花未启用或未填目标，跳过", source="rotate")
        return 0
    from backend import pool as pool_mod
    item = pool_mod.pick_random()
    if item["type"] == "text":
        message = item["content"]            # 已内嵌签名结尾
    else:
        message = "[CQ:image,file=file:///" + item["abs_path"].replace("\\", "/") + "] " + pool_mod.SIGNATURE
    # 只动 friendSpark_message 一个字段，其余内容合并保留
    data = json.loads(qq.PLUGIN_CONFIG_PATH.read_text(encoding="utf-8")) \
        if qq.PLUGIN_CONFIG_PATH.exists() else {}
    data["friendSpark_message"] = message
    qq.PLUGIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    qq.PLUGIN_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    logger.ok("[轮换] 今日 QQ 话术已换成: {0}".format(
        "图片表情+签名" if item["type"] == "image" else message), source="rotate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
