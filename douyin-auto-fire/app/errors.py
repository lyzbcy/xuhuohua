"""错误分类和重试策略。"""
from __future__ import annotations

from enum import Enum


class ErrorCategory(Enum):
    """错误类别，用于智能重试决策。"""

    TRANSIENT = "transient"          # 临时性错误，可以重试（网络波动、页面加载慢）
    PERMANENT = "permanent"           # 永久性错误，不应重试（好友不存在、配置错误）
    AUTHENTICATION = "authentication" # 认证失效，应立即停止所有任务
    RATE_LIMIT = "rate_limit"        # 风控/限流，需要更长延迟或停止


class RetryStrategy:
    """重试策略配置。"""

    def __init__(
        self,
        max_retries: int = 0,
        delay_seconds: float = 3.0,
        backoff_multiplier: float = 1.5,
    ):
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds
        self.backoff_multiplier = backoff_multiplier

    def should_retry(self, attempt: int) -> bool:
        """判断是否应该重试。"""
        return attempt < self.max_retries

    def get_delay(self, attempt: int) -> float:
        """获取重试延迟（指数退避）。"""
        return self.delay_seconds * (self.backoff_multiplier ** attempt)


# 各类错误的默认重试策略
RETRY_STRATEGIES = {
    ErrorCategory.TRANSIENT: RetryStrategy(max_retries=3, delay_seconds=3.0),
    ErrorCategory.PERMANENT: RetryStrategy(max_retries=0, delay_seconds=0.0),
    ErrorCategory.AUTHENTICATION: RetryStrategy(max_retries=0, delay_seconds=0.0),
    ErrorCategory.RATE_LIMIT: RetryStrategy(max_retries=1, delay_seconds=30.0),
}


def classify_error(exc: Exception) -> ErrorCategory:
    """根据异常类型和消息内容分类错误。

    Args:
        exc: 捕获的异常

    Returns:
        错误类别
    """
    from app.browser import AuthenticationError, RiskControlError, SearchBoxNotReadyError
    from app.douyin import PageOperationError
    from app.config import ConfigError

    # 认证失效 - 立即停止
    if isinstance(exc, AuthenticationError):
        return ErrorCategory.AUTHENTICATION

    # 风控检测 - 限流处理
    if isinstance(exc, RiskControlError):
        return ErrorCategory.RATE_LIMIT

    # 配置错误 - 永久性错误
    if isinstance(exc, ConfigError):
        return ErrorCategory.PERMANENT

    error_msg = str(exc).lower()

    # 好友不存在 - 永久性错误
    if any(keyword in error_msg for keyword in [
        "找不到", "不存在", "搜索不到", "未找到",
        "not found", "does not exist"
    ]):
        return ErrorCategory.PERMANENT

    # 页面元素定位问题 - 可能是DOM变化或渲染慢
    if isinstance(exc, PageOperationError) or any(keyword in error_msg for keyword in [
        "找不到页面元素", "无法确认", "element not found",
        "timeout", "locator", "selector"
    ]):
        # 搜索框未就绪是渲染慢，可以重试
        if isinstance(exc, SearchBoxNotReadyError):
            return ErrorCategory.TRANSIENT
        # 其他页面操作错误，可能是DOM变化，少量重试
        return ErrorCategory.TRANSIENT

    # 网络相关错误 - 临时性错误
    if any(keyword in error_msg for keyword in [
        "network", "connection", "timed out", "网络",
        "连接", "超时", "failed to fetch"
    ]):
        return ErrorCategory.TRANSIENT

    # 验证/风控相关 - 限流处理
    if any(keyword in error_msg for keyword in [
        "验证", "安全", "captcha", "风控", "限制",
        "frequency", "too many"
    ]):
        return ErrorCategory.RATE_LIMIT

    # 默认为临时性错误，允许少量重试
    return ErrorCategory.TRANSIENT


def get_retry_strategy(exc: Exception) -> RetryStrategy:
    """获取异常对应的重试策略。

    Args:
        exc: 捕获的异常

    Returns:
        重试策略
    """
    category = classify_error(exc)
    return RETRY_STRATEGIES[category]


def should_stop_all_tasks(exc: Exception) -> bool:
    """判断是否应该立即停止所有任务。

    认证失效和风控检测应该立即停止，避免触发更严格的限制。

    Args:
        exc: 捕获的异常

    Returns:
        是否应该停止所有任务
    """
    category = classify_error(exc)
    return category in (ErrorCategory.AUTHENTICATION, ErrorCategory.RATE_LIMIT)
