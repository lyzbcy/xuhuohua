"""Webhook 配置解析测试。"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import load_settings, ConfigError, _parse_webhook_headers


def test_parse_webhook_headers_json():
    """测试 JSON 格式的 headers。"""
    headers = _parse_webhook_headers('{"Authorization": "Bearer token", "X-Custom": "value"}')
    assert headers == {"Authorization": "Bearer token", "X-Custom": "value"}


def test_parse_webhook_headers_keyvalue():
    """测试键值对格式的 headers。"""
    headers = _parse_webhook_headers("Authorization=Bearer token,X-Custom=value")
    assert headers == {"Authorization": "Bearer token", "X-Custom": "value"}


def test_parse_webhook_headers_keyvalue_with_spaces():
    """测试带空格的键值对。"""
    headers = _parse_webhook_headers(" Authorization = Bearer token , X-Custom = value ")
    assert headers == {"Authorization": "Bearer token", "X-Custom": "value"}


def test_parse_webhook_headers_empty():
    """测试空 headers。"""
    assert _parse_webhook_headers(None) is None
    assert _parse_webhook_headers("") is None
    assert _parse_webhook_headers("   ") is None


def test_parse_webhook_headers_invalid_json():
    """测试无效 JSON。"""
    with pytest.raises(ConfigError, match="WEBHOOK_HEADERS JSON 格式错误"):
        _parse_webhook_headers('{"invalid": json}')


def test_parse_webhook_headers_json_not_object():
    """测试 JSON 不是对象。"""
    with pytest.raises(ConfigError, match="WEBHOOK_HEADERS JSON 必须是对象，不能是数组"):
        _parse_webhook_headers('["array"]')


def test_parse_webhook_headers_invalid_keyvalue():
    """测试无效键值对。"""
    with pytest.raises(ConfigError, match="WEBHOOK_HEADERS 键值对格式错误"):
        _parse_webhook_headers("invalid_no_equals")


def test_load_settings_with_webhook(tmp_path):
    """测试加载 Webhook 配置。"""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"friends": [], "messages": []}')

    with patch.dict(os.environ, {
        "TASK_CONFIG": str(config_file),
        "WEBHOOK_URL": "https://example.com/webhook",
        "WEBHOOK_HEADERS": '{"Authorization": "Bearer token"}',
        "WEBHOOK_TEMPLATE": '{"text": "test"}',
    }, clear=True):
        settings = load_settings()
        assert settings.webhook_url == "https://example.com/webhook"
        assert settings.webhook_headers == {"Authorization": "Bearer token"}
        assert settings.webhook_template == '{"text": "test"}'


def test_load_settings_webhook_optional(tmp_path):
    """测试 Webhook 配置可选。"""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"friends": [], "messages": []}')

    with patch.dict(os.environ, {
        "TASK_CONFIG": str(config_file),
    }, clear=True):
        settings = load_settings()
        assert settings.webhook_url is None
        assert settings.webhook_headers is None
        assert settings.webhook_template is None
