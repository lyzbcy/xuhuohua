from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.models import TargetResult


MAX_RESULTS_PER_SECTION = 15
MAX_MARKDOWN_BYTES = 18_000
NOTIFY_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


async def send_dingtalk_notification(
    webhook: str,
    secret: str,
    task_id: str,
    dry_run: bool,
    results: list[TargetResult],
    screenshots: list[Path],
) -> None:
    title, markdown = build_dingtalk_markdown(task_id, dry_run, results, screenshots)
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": markdown},
        "at": {"isAtAll": False},
    }
    await asyncio.to_thread(_post_json, _signed_webhook_url(webhook, secret), payload)


async def send_webhook_notification(
    webhook_url: str,
    task_id: str,
    dry_run: bool,
    results: list[TargetResult],
    screenshots: list[Path],
    template: str | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """发送通用 Webhook 通知。

    Args:
        webhook_url: Webhook URL
        task_id: 任务 ID
        dry_run: 是否为 Dry Run 模式
        results: 执行结果列表
        screenshots: 截图文件列表
        template: 自定义模板（JSON 字符串），支持变量替换
        headers: 自定义请求头
    """
    payload = build_webhook_payload(task_id, dry_run, results, screenshots, template)
    custom_headers = dict(headers or {})
    custom_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    await asyncio.to_thread(_post_json_webhook, webhook_url, payload, custom_headers)


def build_dingtalk_markdown(
    task_id: str,
    dry_run: bool,
    results: list[TargetResult],
    screenshots: list[Path],
    finished_at: datetime | None = None,
) -> tuple[str, str]:
    successes = [result for result in results if result.status == "success"]
    failures = [result for result in results if result.status == "failed"]
    status = "全部成功" if not failures else "存在失败"
    mode = "检查模式（未发送消息）" if dry_run else "正式发送"
    finished = (finished_at or datetime.now(timezone.utc)).astimezone(NOTIFY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %z")
    title = f"抖音自动发送：{status}"
    lines = [
        f"### {title}",
        "",
        f"> **任务**：{_markdown_text(task_id, limit=100)}  ",
        f"> **模式**：{mode}  ",
        f"> **完成时间**：{finished}  ",
        f"> **结果**：成功 {len(successes)} 人，失败 {len(failures)} 人",
        "",
        f"#### 成功名单（{len(successes)}）",
    ]
    if successes:
        for index, result in enumerate(successes[:MAX_RESULTS_PER_SECTION], 1):
            detail = "验证通过" if dry_run else f"已发送 {result.sent} 条"
            lines.append(f"{index}. **{_markdown_text(result.target, limit=100)}** - {detail}")
        if len(successes) > MAX_RESULTS_PER_SECTION:
            lines.append(f"- 其余 {len(successes) - MAX_RESULTS_PER_SECTION} 人已省略")
    else:
        lines.append("无")

    lines.extend(["", f"#### 失败名单（{len(failures)}）"])
    if failures:
        for index, result in enumerate(failures[:MAX_RESULTS_PER_SECTION], 1):
            error = _markdown_text(result.error or "未知错误", limit=300)
            sent = f"，已发送 {result.sent} 条" if result.sent else ""
            lines.append(f"{index}. **{_markdown_text(result.target, limit=100)}**{sent}")
            lines.append(f"   - 原因：{error}")
        if len(failures) > MAX_RESULTS_PER_SECTION:
            lines.append(f"- 其余 {len(failures) - MAX_RESULTS_PER_SECTION} 人已省略")
    else:
        lines.append("无")

    if screenshots:
        lines.extend(["", "#### 失败截图"])
        lines.extend(f"- `{_markdown_text(path.name, limit=100)}`" for path in screenshots[:MAX_RESULTS_PER_SECTION])
        run_url = _github_run_url()
        if run_url:
            lines.extend(
                [
                    "",
                    f"[打开本次 GitHub Actions 运行并下载截图]({run_url})",
                    "",
                    "> 截图将在任务结束后出现在该次运行底部的 Artifacts 中。",
                ]
            )

    return title, _truncate_utf8("\n".join(lines), MAX_MARKDOWN_BYTES)


def _signed_webhook_url(webhook: str, secret: str, timestamp_ms: int | None = None) -> str:
    timestamp = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()).decode()
    parsed = urlsplit(webhook)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend((('timestamp', str(timestamp)), ('sign', signature)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _post_json(url: str, payload: dict) -> None:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    result = json.loads(body)
    if result.get("errcode") != 0:
        raise RuntimeError(f"钉钉机器人返回错误: {result.get('errmsg', body)}")


def _github_run_url() -> str | None:
    server = os.getenv("GITHUB_SERVER_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if not server or not repository or not run_id:
        return None
    return f"{server.rstrip('/')}/{repository}/actions/runs/{run_id}"


def _markdown_text(value: str, limit: int | None = None) -> str:
    text = " ".join(value.splitlines()).strip()
    if limit is not None and len(text) > limit:
        text = f"{text[:limit - 3]}..."
    for character in ("\\", "`", "*", "_", "[", "]", "#", ">", "|"):
        text = text.replace(character, f"\\{character}")
    return text


def _truncate_utf8(text: str, max_bytes: int) -> str:
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    suffix = "\n\n> 通知内容过长，部分内容已省略。"
    available = max_bytes - len(suffix.encode("utf-8"))
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(text[:middle].encode("utf-8")) <= available:
            low = middle
        else:
            high = middle - 1
    return f"{text[:low]}{suffix}"


def build_webhook_payload(
    task_id: str,
    dry_run: bool,
    results: list[TargetResult],
    screenshots: list[Path],
    template: str | None = None,
) -> dict:
    """构建通用 Webhook 负载。

    Args:
        task_id: 任务 ID
        dry_run: 是否为 Dry Run 模式
        results: 执行结果列表
        screenshots: 截图文件列表
        template: 自定义 JSON 模板，支持以下变量：
            - {task_id}: 任务 ID
            - {mode}: 运行模式（检查模式/正式发送）
            - {status}: 执行状态（全部成功/存在失败）
            - {success_count}: 成功数量
            - {failed_count}: 失败数量
            - {total_count}: 总数量
            - {timestamp}: 时间戳（ISO 8601）
            - {results_json}: 完整结果 JSON（转义后）

    Returns:
        Webhook 负载字典
    """
    successes = [result for result in results if result.status == "success"]
    failures = [result for result in results if result.status == "failed"]
    status = "全部成功" if not failures else "存在失败"
    mode = "检查模式（未发送消息）" if dry_run else "正式发送"
    finished = datetime.now(timezone.utc).astimezone(NOTIFY_TIMEZONE).isoformat()

    # 构建结果摘要
    results_data = [
        {
            "target": result.target,
            "status": result.status,
            "sent": result.sent,
            "error": result.error,
        }
        for result in results
    ]

    # 如果没有自定义模板，使用默认格式
    if not template:
        return {
            "task_id": task_id,
            "mode": mode,
            "status": status,
            "dry_run": dry_run,
            "success_count": len(successes),
            "failed_count": len(failures),
            "total_count": len(results),
            "timestamp": finished,
            "results": results_data,
            "screenshots": [str(path.name) for path in screenshots],
        }

    # 使用自定义模板
    try:
        template_dict = json.loads(template)
    except json.JSONDecodeError as exc:
        # 模板解析失败，回退到默认格式
        return {
            "error": "模板解析失败",
            "template_error": str(exc),
            "task_id": task_id,
            "status": status,
        }

    # 替换模板中的变量（支持字符串和数字类型）
    variables = {
        "{task_id}": task_id,
        "{mode}": mode,
        "{status}": status,
        "{success_count}": len(successes),
        "{failed_count}": len(failures),
        "{total_count}": len(results),
        "{timestamp}": finished,
        "{results_json}": results_data,  # 直接传递对象，不转 JSON 字符串
    }

    return _replace_template_vars(template_dict, variables)


def _replace_template_vars(obj, variables: dict[str, str | int | list]):
    """递归替换模板中的变量。

    支持字符串替换和直接值替换：
    - 字符串类型：在字符串中查找并替换变量占位符
    - 特殊值（如 results_json）：直接返回对象本身
    """
    if isinstance(obj, dict):
        return {key: _replace_template_vars(value, variables) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_replace_template_vars(item, variables) for item in obj]
    if isinstance(obj, str):
        # 检查是否是纯变量占位符（用于直接值替换）
        obj_stripped = obj.strip()
        if obj_stripped in variables:
            return variables[obj_stripped]
        # 否则做字符串替换
        result = obj
        for var, value in variables.items():
            if isinstance(value, str):
                result = result.replace(var, value)
            elif var in result:
                # 数字类型的变量需要转字符串
                result = result.replace(var, str(value))
        return result
    return obj


def _post_json_webhook(url: str, payload: dict, headers: dict[str, str]) -> None:
    """发送 JSON 到通用 Webhook。"""
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    # 通用 Webhook 不对响应做严格校验，只要 HTTP 状态码是 2xx 就认为成功
    # 如果需要校验响应内容，可以在这里添加
