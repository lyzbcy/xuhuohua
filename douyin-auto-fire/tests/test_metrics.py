"""测试监控指标模块。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.metrics import Metrics, HistoricalMetrics, format_metrics_summary


class TestMetrics:
    """测试指标收集。"""

    def test_initial_metrics(self):
        """测试初始指标值。"""
        metrics = Metrics()
        assert metrics.total_targets == 0
        assert metrics.successful_targets == 0
        assert metrics.failed_targets == 0
        assert metrics.success_rate == 0.0

    def test_record_target_success(self):
        """测试记录目标成功。"""
        metrics = Metrics()
        metrics.record_target_success(message_count=3)
        assert metrics.successful_targets == 1
        assert metrics.successful_messages == 3

    def test_record_target_failure(self):
        """测试记录目标失败。"""
        metrics = Metrics()
        metrics.record_target_failure("PageOperationError", sent_count=1)
        assert metrics.failed_targets == 1
        assert metrics.successful_messages == 1
        assert metrics.error_counts["PageOperationError"] == 1

    def test_success_rate(self):
        """测试成功率计算。"""
        metrics = Metrics()
        metrics.record_target_success(2)
        metrics.record_target_success(3)
        metrics.record_target_failure("Error", 0)
        metrics.finalize()
        assert metrics.total_targets == 3
        assert metrics.success_rate == pytest.approx(2 / 3)

    def test_message_success_rate(self):
        """测试消息成功率。"""
        metrics = Metrics()
        metrics.successful_messages = 8
        metrics.failed_messages = 2
        assert metrics.message_success_rate == pytest.approx(0.8)

    def test_record_skipped_message(self):
        """测试记录跳过消息。"""
        metrics = Metrics()
        metrics.record_skipped_message()
        metrics.record_skipped_message()
        assert metrics.skipped_messages == 2

    def test_record_message_time(self):
        """测试记录消息时间。"""
        metrics = Metrics()
        metrics.record_message_time(2.5)
        metrics.record_message_time(1.5)
        metrics.record_message_time(3.0)

        assert metrics.min_message_time_seconds == 1.5
        assert metrics.max_message_time_seconds == 3.0

    def test_finalize(self):
        """测试完成统计。"""
        metrics = Metrics()
        metrics.started_at = "2026-01-01T00:00:00"
        metrics.record_target_success(5)
        metrics.record_skipped_message()
        metrics.total_duration_seconds = 10.0

        metrics.finalize()

        assert metrics.total_targets == 1
        assert metrics.total_messages == 6  # 5 成功 + 1 跳过
        assert metrics.average_message_time_seconds == pytest.approx(2.0)
        assert metrics.finished_at != ""

    def test_save_and_load(self, tmp_path: Path):
        """测试保存和加载指标。"""
        metrics = Metrics()
        metrics.record_target_success(3)
        metrics.record_target_failure("Error1", 1)
        metrics.finalize()

        # 保存
        path = tmp_path / "metrics.json"
        metrics.save(path)
        assert path.exists()

        # 加载
        loaded = Metrics.load(path)
        assert loaded is not None
        assert loaded.total_targets == 2
        assert loaded.successful_targets == 1
        assert loaded.error_counts["Error1"] == 1

    def test_load_nonexistent_file(self, tmp_path: Path):
        """测试加载不存在的文件。"""
        path = tmp_path / "nonexistent.json"
        loaded = Metrics.load(path)
        assert loaded is None

    def test_to_dict(self):
        """测试转换为字典。"""
        metrics = Metrics()
        metrics.record_target_success(2)
        data = metrics.to_dict()

        assert isinstance(data, dict)
        assert data["successful_targets"] == 1
        assert data["successful_messages"] == 2
        assert isinstance(data["error_counts"], dict)


class TestHistoricalMetrics:
    """测试历史指标。"""

    def test_initial_historical_metrics(self):
        """测试初始历史指标。"""
        historical = HistoricalMetrics()
        assert historical.total_runs == 0
        assert historical.total_successful_runs == 0
        assert historical.average_success_rate == 0.0

    def test_update_with_successful_run(self):
        """测试更新成功运行。"""
        historical = HistoricalMetrics()
        metrics = Metrics()
        metrics.successful_targets = 5
        metrics.failed_targets = 0
        metrics.successful_messages = 10
        metrics.finished_at = "2026-01-01T00:00:00"

        historical.update(metrics)

        assert historical.total_runs == 1
        assert historical.total_successful_runs == 1
        assert historical.total_messages_sent == 10
        assert historical.average_success_rate == 1.0

    def test_update_with_failed_run(self):
        """测试更新失败运行。"""
        historical = HistoricalMetrics()
        metrics = Metrics()
        metrics.successful_targets = 3
        metrics.failed_targets = 2
        metrics.successful_messages = 6
        metrics.finished_at = "2026-01-01T00:00:00"

        historical.update(metrics)

        assert historical.total_runs == 1
        assert historical.total_successful_runs == 0  # 有失败目标
        assert historical.total_messages_sent == 6

    def test_average_success_rate_calculation(self):
        """测试平均成功率计算。"""
        historical = HistoricalMetrics()

        # 第一次运行：成功
        metrics1 = Metrics()
        metrics1.failed_targets = 0
        metrics1.finished_at = "2026-01-01T00:00:00"
        historical.update(metrics1)

        # 第二次运行：失败
        metrics2 = Metrics()
        metrics2.failed_targets = 1
        metrics2.finished_at = "2026-01-02T00:00:00"
        historical.update(metrics2)

        # 第三次运行：成功
        metrics3 = Metrics()
        metrics3.failed_targets = 0
        metrics3.finished_at = "2026-01-03T00:00:00"
        historical.update(metrics3)

        assert historical.total_runs == 3
        assert historical.total_successful_runs == 2
        assert historical.average_success_rate == pytest.approx(2 / 3)

    def test_save_and_load(self, tmp_path: Path):
        """测试保存和加载历史指标。"""
        historical = HistoricalMetrics()
        metrics = Metrics()
        metrics.successful_messages = 5
        metrics.finished_at = "2026-01-01T00:00:00"
        metrics.started_at = "2026-01-01T00:00:00"
        historical.update(metrics)

        # 保存
        path = tmp_path / "history.json"
        historical.save(path)
        assert path.exists()

        # 加载
        loaded = HistoricalMetrics.load(path)
        assert loaded.total_runs == 1
        assert loaded.last_run_at == "2026-01-01T00:00:00"


class TestFormatMetricsSummary:
    """测试指标摘要格式化。"""

    def test_format_basic_summary(self):
        """测试基本摘要格式化。"""
        metrics = Metrics()
        metrics.successful_targets = 4
        metrics.failed_targets = 1
        metrics.successful_messages = 8
        metrics.failed_messages = 2
        metrics.skipped_messages = 1
        metrics.total_duration_seconds = 25.5
        metrics.started_at = "2026-01-01T10:00:00"
        metrics.finalize()  # 需要调用 finalize 来计算 total_messages 和 total_targets

        summary = format_metrics_summary(metrics)

        assert "总目标数: 5" in summary
        assert "成功: 4" in summary
        assert "失败: 1" in summary
        assert "总消息数: 11" in summary
        assert "执行时间: 25.5秒" in summary

    def test_format_with_message_times(self):
        """测试包含消息时间的摘要。"""
        metrics = Metrics()
        metrics.successful_messages = 3
        metrics.record_message_time(2.0)
        metrics.record_message_time(3.0)
        metrics.record_message_time(1.0)
        metrics.total_duration_seconds = 6.0
        metrics.finalize()

        summary = format_metrics_summary(metrics)

        assert "平均每条消息: 2.0秒" in summary
        assert "最快: 1.0秒" in summary
        assert "最慢: 3.0秒" in summary

    def test_format_with_errors(self):
        """测试包含错误统计的摘要。"""
        metrics = Metrics()
        metrics.record_target_failure("AuthenticationError")
        metrics.record_target_failure("PageOperationError")
        metrics.record_target_failure("PageOperationError")

        summary = format_metrics_summary(metrics)

        assert "错误统计:" in summary
        assert "PageOperationError: 2次" in summary
        assert "AuthenticationError: 1次" in summary
