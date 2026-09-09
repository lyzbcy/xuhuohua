"""通用 Webhook 通知测试。"""
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from app.models import TargetResult
from app.notifier import build_webhook_payload, send_webhook_notification


def test_build_webhook_payload_default():
    """测试默认 Webhook 负载构建。"""
    results = [
        TargetResult(target="好友01", status="success", sent=2),
        TargetResult(target="好友02", status="failed", error="网络错误"),
    ]
    screenshots = [Path("screenshot1.png"), Path("screenshot2.png")]

    payload = build_webhook_payload("daily-task", False, results, screenshots)

    assert payload["task_id"] == "daily-task"
    assert payload["mode"] == "正式发送"
    assert payload["status"] == "存在失败"
    assert payload["dry_run"] is False
    assert payload["success_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["total_count"] == 2
    assert "timestamp" in payload
    assert len(payload["results"]) == 2
    assert payload["results"][0]["target"] == "好友01"
    assert payload["results"][0]["status"] == "success"
    assert payload["results"][0]["sent"] == 2
    assert payload["results"][1]["error"] == "网络错误"
    assert payload["screenshots"] == ["screenshot1.png", "screenshot2.png"]


def test_build_webhook_payload_dry_run():
    """测试 Dry Run 模式的负载。"""
    results = [TargetResult(target="好友01", status="success", sent=0)]
    payload = build_webhook_payload("test", True, results, [])

    assert payload["mode"] == "检查模式（未发送消息）"
    assert payload["dry_run"] is True


def test_build_webhook_payload_custom_template():
    """测试自定义模板。"""
    results = [
        TargetResult(target="好友01", status="success", sent=2),
        TargetResult(target="好友02", status="failed", error="错误"),
    ]
    template = '''{
        "text": "任务 {task_id} 执行完成",
        "status": "{status}",
        "mode": "{mode}",
        "stats": {
            "success": "{success_count}",
            "failed": "{failed_count}",
            "total": "{total_count}"
        },
        "timestamp": "{timestamp}"
    }'''

    payload = build_webhook_payload("daily", False, results, [], template)

    assert payload["text"] == "任务 daily 执行完成"
    assert payload["status"] == "存在失败"
    assert payload["mode"] == "正式发送"
    # 当变量在引号中时，替换后是字符串；作为纯占位符时是原始类型
    assert payload["stats"]["success"] == 1
    assert payload["stats"]["failed"] == 1
    assert payload["stats"]["total"] == 2
    assert "{timestamp}" not in payload["timestamp"]


def test_build_webhook_payload_template_with_results_json():
    """测试模板中嵌入完整结果 JSON。"""
    results = [TargetResult(target="好友01", status="success", sent=1)]
    template = '{"message": "完成", "data": "{results_json}"}'

    payload = build_webhook_payload("task", False, results, [], template)

    assert payload["message"] == "完成"
    # results_json 作为纯变量占位符时，应直接替换为对象
    assert isinstance(payload["data"], list)
    assert payload["data"][0]["target"] == "好友01"
    assert payload["data"][0]["status"] == "success"


def test_build_webhook_payload_invalid_template():
    """测试无效模板回退到默认格式。"""
    results = [TargetResult(target="好友01", status="success", sent=1)]
    template = "invalid json {"

    payload = build_webhook_payload("task", False, results, [], template)

    assert "error" in payload
    assert payload["error"] == "模板解析失败"
    assert payload["task_id"] == "task"


@pytest.mark.asyncio
async def test_send_webhook_notification_success():
    """测试发送 Webhook 通知成功。"""
    results = [TargetResult(target="好友01", status="success", sent=1)]

    with patch("app.notifier.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = None

        await send_webhook_notification(
            "https://example.com/webhook",
            "task-id",
            False,
            results,
            [],
        )

        mock_thread.assert_called_once()
        call_args = mock_thread.call_args
        assert call_args[0][0].__name__ == "_post_json_webhook"
        assert call_args[0][1] == "https://example.com/webhook"
        payload = call_args[0][2]
        assert payload["task_id"] == "task-id"


@pytest.mark.asyncio
async def test_send_webhook_notification_with_custom_headers():
    """测试自定义请求头。"""
    results = [TargetResult(target="好友01", status="success", sent=1)]
    custom_headers = {"Authorization": "Bearer token123", "X-Custom": "value"}

    with patch("app.notifier.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = None

        await send_webhook_notification(
            "https://example.com/webhook",
            "task-id",
            False,
            results,
            [],
            headers=custom_headers,
        )

        call_args = mock_thread.call_args
        headers = call_args[0][3]
        assert headers["Authorization"] == "Bearer token123"
        assert headers["X-Custom"] == "value"
        assert "Content-Type" in headers  # 默认添加


@pytest.mark.asyncio
async def test_send_webhook_notification_with_template():
    """测试使用自定义模板发送。"""
    results = [TargetResult(target="好友01", status="success", sent=2)]
    template = '{"msg": "{status}", "count": "{success_count}"}'

    with patch("app.notifier.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = None

        await send_webhook_notification(
            "https://example.com/webhook",
            "task-id",
            False,
            results,
            [],
            template=template,
        )

        call_args = mock_thread.call_args
        payload = call_args[0][2]
        assert payload["msg"] == "全部成功"
        assert payload["count"] == 1  # 纯占位符返回整数
