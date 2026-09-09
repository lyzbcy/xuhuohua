"""测试错误分类和重试策略。"""
from __future__ import annotations

import pytest

from app.browser import AuthenticationError, RiskControlError, SearchBoxNotReadyError
from app.config import ConfigError
from app.douyin import PageOperationError
from app.errors import (
    ErrorCategory,
    RetryStrategy,
    classify_error,
    get_retry_strategy,
    should_stop_all_tasks,
)


class TestErrorClassification:
    """测试错误分类。"""

    def test_authentication_error(self):
        """认证失效错误应该归类为 AUTHENTICATION。"""
        exc = AuthenticationError("登录状态失效")
        assert classify_error(exc) == ErrorCategory.AUTHENTICATION

    def test_risk_control_error(self):
        """风控错误应该归类为 RATE_LIMIT。"""
        exc = RiskControlError("安全验证")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT

    def test_config_error(self):
        """配置错误应该归类为 PERMANENT。"""
        exc = ConfigError("配置文件格式错误")
        assert classify_error(exc) == ErrorCategory.PERMANENT

    def test_friend_not_found(self):
        """好友不存在应该归类为 PERMANENT。"""
        exc = PageOperationError("搜索不到目标好友")
        assert classify_error(exc) == ErrorCategory.PERMANENT

    def test_search_box_not_ready(self):
        """搜索框未就绪应该归类为 TRANSIENT（可重试）。"""
        exc = SearchBoxNotReadyError("搜索框未就绪")
        assert classify_error(exc) == ErrorCategory.TRANSIENT

    def test_page_operation_timeout(self):
        """页面操作超时应该归类为 TRANSIENT。"""
        exc = PageOperationError("timeout waiting for element")
        assert classify_error(exc) == ErrorCategory.TRANSIENT

    def test_network_error(self):
        """网络错误应该归类为 TRANSIENT。"""
        exc = Exception("network connection failed")
        assert classify_error(exc) == ErrorCategory.TRANSIENT

    def test_security_verification(self):
        """安全验证应该归类为 RATE_LIMIT。"""
        exc = Exception("需要完成安全验证")
        assert classify_error(exc) == ErrorCategory.RATE_LIMIT

    def test_unknown_error_defaults_to_transient(self):
        """未知错误默认归类为 TRANSIENT。"""
        exc = Exception("some unknown error")
        assert classify_error(exc) == ErrorCategory.TRANSIENT


class TestRetryStrategy:
    """测试重试策略。"""

    def test_should_retry_within_limit(self):
        """在限制内应该重试。"""
        strategy = RetryStrategy(max_retries=3)
        assert strategy.should_retry(0) is True
        assert strategy.should_retry(1) is True
        assert strategy.should_retry(2) is True

    def test_should_not_retry_at_limit(self):
        """达到限制不应该重试。"""
        strategy = RetryStrategy(max_retries=3)
        assert strategy.should_retry(3) is False
        assert strategy.should_retry(4) is False

    def test_exponential_backoff(self):
        """测试指数退避延迟。"""
        strategy = RetryStrategy(max_retries=3, delay_seconds=2.0, backoff_multiplier=2.0)
        assert strategy.get_delay(0) == 2.0
        assert strategy.get_delay(1) == 4.0
        assert strategy.get_delay(2) == 8.0

    def test_transient_error_strategy(self):
        """临时性错误应该允许重试。"""
        exc = Exception("network timeout")
        strategy = get_retry_strategy(exc)
        assert strategy.max_retries > 0

    def test_permanent_error_strategy(self):
        """永久性错误不应该重试。"""
        exc = PageOperationError("搜索不到目标好友")
        strategy = get_retry_strategy(exc)
        assert strategy.max_retries == 0

    def test_authentication_error_strategy(self):
        """认证失效不应该重试。"""
        exc = AuthenticationError("登录失效")
        strategy = get_retry_strategy(exc)
        assert strategy.max_retries == 0


class TestStopAllTasks:
    """测试是否应该停止所有任务。"""

    def test_authentication_error_stops_all(self):
        """认证失效应该停止所有任务。"""
        exc = AuthenticationError("登录失效")
        assert should_stop_all_tasks(exc) is True

    def test_risk_control_stops_all(self):
        """风控应该停止所有任务。"""
        exc = RiskControlError("安全验证")
        assert should_stop_all_tasks(exc) is True

    def test_page_error_does_not_stop_all(self):
        """页面操作错误不应该停止所有任务。"""
        exc = PageOperationError("搜索不到目标好友")
        assert should_stop_all_tasks(exc) is False

    def test_network_error_does_not_stop_all(self):
        """网络错误不应该停止所有任务。"""
        exc = Exception("network timeout")
        assert should_stop_all_tasks(exc) is False
