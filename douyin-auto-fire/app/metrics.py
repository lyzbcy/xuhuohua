"""监控指标收集和报告。"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Metrics:
    """运行指标统计。"""

    # 基础统计
    total_targets: int = 0
    successful_targets: int = 0
    failed_targets: int = 0
    total_messages: int = 0
    successful_messages: int = 0
    failed_messages: int = 0
    skipped_messages: int = 0  # 防重复跳过的消息

    # 性能统计
    total_duration_seconds: float = 0.0
    average_message_time_seconds: float = 0.0
    min_message_time_seconds: float | None = None
    max_message_time_seconds: float | None = None

    # 错误统计
    error_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # 时间戳
    started_at: str = ""
    finished_at: str = ""

    def __post_init__(self):
        """确保 error_counts 是 defaultdict。"""
        if not isinstance(self.error_counts, defaultdict):
            self.error_counts = defaultdict(int, self.error_counts or {})

    @property
    def success_rate(self) -> float:
        """成功率（基于目标数）。"""
        if self.total_targets == 0:
            return 0.0
        return self.successful_targets / self.total_targets

    @property
    def message_success_rate(self) -> float:
        """消息成功率。"""
        total = self.successful_messages + self.failed_messages
        if total == 0:
            return 0.0
        return self.successful_messages / total

    def record_target_success(self, message_count: int):
        """记录目标处理成功。"""
        self.successful_targets += 1
        self.successful_messages += message_count

    def record_target_failure(self, error_type: str, sent_count: int = 0):
        """记录目标处理失败。"""
        self.failed_targets += 1
        self.successful_messages += sent_count
        self.error_counts[error_type] += 1

    def record_skipped_message(self):
        """记录跳过的消息（防重复）。"""
        self.skipped_messages += 1

    def record_message_time(self, duration_seconds: float):
        """记录单条消息发送时间。"""
        if self.min_message_time_seconds is None:
            self.min_message_time_seconds = duration_seconds
        else:
            self.min_message_time_seconds = min(self.min_message_time_seconds, duration_seconds)

        if self.max_message_time_seconds is None:
            self.max_message_time_seconds = duration_seconds
        else:
            self.max_message_time_seconds = max(self.max_message_time_seconds, duration_seconds)

    def finalize(self):
        """完成统计计算。"""
        self.finished_at = datetime.now().astimezone().isoformat()

        # 计算总消息数
        self.total_messages = self.successful_messages + self.failed_messages + self.skipped_messages

        # 计算总目标数
        self.total_targets = self.successful_targets + self.failed_targets

        # 计算平均时间
        if self.successful_messages > 0 and self.total_duration_seconds > 0:
            self.average_message_time_seconds = self.total_duration_seconds / self.successful_messages

    def to_dict(self) -> dict:
        """转换为字典，便于JSON序列化。"""
        # 不使用 dataclasses.asdict()，因为它无法正确复制 defaultdict，
        # 在 Python 3.11 上会抛出 TypeError: first argument must be callable or None。
        # 手动构建字典，将 defaultdict 转为普通 dict 以确保 JSON 可序列化。
        data = vars(self).copy()
        data["error_counts"] = dict(self.error_counts)
        return data

    def save(self, path: Path):
        """保存指标到文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Metrics | None:
        """从文件加载指标。"""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except (json.JSONDecodeError, TypeError):
            return None


@dataclass
class HistoricalMetrics:
    """历史指标汇总。"""

    total_runs: int = 0
    total_successful_runs: int = 0
    total_messages_sent: int = 0
    average_success_rate: float = 0.0
    last_run_at: str = ""
    first_run_at: str = ""

    def update(self, metrics: Metrics):
        """用新的运行指标更新历史统计。"""
        self.total_runs += 1
        if metrics.failed_targets == 0:
            self.total_successful_runs += 1
        self.total_messages_sent += metrics.successful_messages
        self.last_run_at = metrics.finished_at
        if not self.first_run_at:
            self.first_run_at = metrics.started_at

        # 重新计算平均成功率
        self.average_success_rate = self.total_successful_runs / self.total_runs if self.total_runs > 0 else 0.0

    def save(self, path: Path):
        """保存历史指标。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(vars(self).copy(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> HistoricalMetrics:
        """从文件加载历史指标。"""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except (json.JSONDecodeError, TypeError):
            return cls()


def format_metrics_summary(metrics: Metrics) -> str:
    """格式化指标摘要，用于日志输出。

    Args:
        metrics: 指标对象

    Returns:
        格式化的摘要文本
    """
    lines = [
        "=" * 60,
        "运行指标摘要",
        "=" * 60,
        f"总目标数: {metrics.total_targets}",
        f"  成功: {metrics.successful_targets}",
        f"  失败: {metrics.failed_targets}",
        f"  成功率: {metrics.success_rate:.1%}",
        "",
        f"总消息数: {metrics.total_messages}",
        f"  发送成功: {metrics.successful_messages}",
        f"  发送失败: {metrics.failed_messages}",
        f"  跳过（防重复）: {metrics.skipped_messages}",
        f"  消息成功率: {metrics.message_success_rate:.1%}",
        "",
        f"执行时间: {metrics.total_duration_seconds:.1f}秒",
    ]

    if metrics.successful_messages > 0:
        lines.append(f"  平均每条消息: {metrics.average_message_time_seconds:.1f}秒")
        if metrics.min_message_time_seconds is not None:
            lines.append(f"  最快: {metrics.min_message_time_seconds:.1f}秒")
        if metrics.max_message_time_seconds is not None:
            lines.append(f"  最慢: {metrics.max_message_time_seconds:.1f}秒")

    if metrics.error_counts:
        lines.extend([
            "",
            "错误统计:",
        ])
        for error_type, count in sorted(metrics.error_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {error_type}: {count}次")

    lines.extend([
        "",
        f"开始时间: {metrics.started_at}",
        f"结束时间: {metrics.finished_at}",
        "=" * 60,
    ])

    return "\n".join(lines)
