# -*- coding: utf-8 -*-
"""企业微信机器人通知：每日发送结果 / 失败告警推到企微群。
配置存 config/settings.json（与话术池同目录，不入库）。
"""
import json
import urllib.request
from pathlib import Path

from backend import logger
from backend.paths import PROJECT_ROOT

SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.json"

DEFAULTS = {
    "wecom_webhook": "",
    "notify_on_success": True,   # 每日定时发送完成（含成败统计）
    "notify_on_failure": True,   # 失败告警
}


def get_settings() -> dict:
    data = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save_settings(patch: dict) -> dict:
    cur = get_settings()
    for k in DEFAULTS:
        if k in patch:
            cur[k] = patch[k]
    cur["wecom_webhook"] = str(cur.get("wecom_webhook", "")).strip()
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    logger.ok("[通知] 设置已保存", source="notify")
    return cur


def send_text(text: str, force: bool = False) -> dict:
    """向企业微信群机器人发文本。force=True 用于「测试」按钮（无视开关）。"""
    s = get_settings()
    hook = s.get("wecom_webhook", "")
    if not hook.startswith("https://qyapi.weixin.qq.com/"):
        return {"ok": False, "msg": "没有配置有效的企业微信机器人 Webhook"}
    payload = json.dumps({"msgtype": "text",
                          "text": {"content": "【续火花】\n" + text}}).encode("utf-8")
    req = urllib.request.Request(hook, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode("utf-8"))
        if resp.get("errcode") == 0:
            return {"ok": True, "msg": "已发送到企业微信"}
        return {"ok": False, "msg": "企微返回错误: " + str(resp.get("errmsg"))}
    except Exception as exc:
        return {"ok": False, "msg": "发送失败: " + str(exc)[:120]}


def notify_event(kind: str, text: str) -> None:
    """按设置开关推送（kind: success / failure）。发送失败只记日志不打扰。"""
    s = get_settings()
    if not s.get("wecom_webhook"):
        return
    if kind == "success" and not s.get("notify_on_success", True):
        return
    if kind == "failure" and not s.get("notify_on_failure", True):
        return
    r = send_text(text)
    (logger.ok if r["ok"] else logger.warn)(
        "[通知] 企微推送{0}".format("成功" if r["ok"] else "失败: " + r["msg"]), source="notify")
