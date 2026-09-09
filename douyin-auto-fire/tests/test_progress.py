"""测试进度显示模块。"""
from __future__ import annotations

import io
import sys

import pytest

from app.progress import ProgressBar, MultiStageProgress, TargetProgress


class TestProgressBar:
    """测试进度条。"""

    def test_initial_state(self):
        """测试初始状态。"""
        bar = ProgressBar(total=10, prefix="测试")
        assert bar.total == 10
        assert bar.current == 0
        assert bar.prefix == "测试"

    def test_update_progress(self):
        """测试更新进度。"""
        bar = ProgressBar(total=10)
        bar.update(3)
        assert bar.current == 3
        bar.update(2)
        assert bar.current == 5

    def test_update_does_not_exceed_total(self):
        """测试更新不会超过总数。"""
        bar = ProgressBar(total=10)
        bar.update(8)
        bar.update(5)  # 尝试超过总数
        assert bar.current == 10  # 应该被限制在 10

    def test_zero_total(self):
        """测试总数为 0 的情况。"""
        bar = ProgressBar(total=0)
        bar.update(1)
        assert bar.current == 0

    def test_render_does_not_crash(self, monkeypatch):
        """测试渲染不会崩溃（即使不在 TTY）。"""
        # 模拟非 TTY 环境
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        bar = ProgressBar(total=10, prefix="测试")
        bar.update(5)
        bar.finish()
        # 不应该抛出异常

    def test_finish(self, monkeypatch):
        """测试完成进度条。"""
        output = io.StringIO()
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", output.write)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)

        bar = ProgressBar(total=5)
        bar.update(5)
        bar.finish()

        # 应该有换行符
        assert "\n" in output.getvalue() or output.getvalue() == ""


class TestMultiStageProgress:
    """测试多阶段进度。"""

    def test_initial_state(self):
        """测试初始状态。"""
        stages = ["阶段1", "阶段2", "阶段3"]
        progress = MultiStageProgress(stages)
        assert progress.stages == stages
        assert progress.current_stage == 0

    def test_start_stage_without_items(self, monkeypatch, capsys):
        """测试开始无具体数量的阶段。"""
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        stages = ["阶段1", "阶段2"]
        progress = MultiStageProgress(stages)
        progress.start_stage(0)
        captured = capsys.readouterr()
        assert "[1/2] 阶段1..." in captured.out

    def test_start_stage_with_items(self):
        """测试开始有具体数量的阶段。"""
        stages = ["阶段1", "阶段2"]
        progress = MultiStageProgress(stages)
        progress.start_stage(0, total_items=10)
        assert progress.progress_bar is not None
        assert progress.progress_bar.total == 10

    def test_update_progress(self):
        """测试更新进度。"""
        stages = ["阶段1"]
        progress = MultiStageProgress(stages)
        progress.start_stage(0, total_items=5)
        progress.update_progress(2)
        assert progress.progress_bar.current == 2

    def test_finish_stage(self):
        """测试完成阶段。"""
        stages = ["阶段1"]
        progress = MultiStageProgress(stages)
        progress.start_stage(0, total_items=5)
        progress.finish_stage()
        assert progress.progress_bar is None

    def test_finish_all(self, monkeypatch, capsys):
        """测试完成所有阶段。"""
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        stages = ["阶段1", "阶段2"]
        progress = MultiStageProgress(stages)
        progress.start_stage(0)
        progress.finish_stage()
        progress.start_stage(1)
        progress.finish_stage()
        progress.finish_all()
        captured = capsys.readouterr()
        assert "✓ 所有阶段完成" in captured.out


class TestTargetProgress:
    """测试目标进度。"""

    def test_initial_state(self):
        """测试初始状态。"""
        progress = TargetProgress(total_targets=10, label="好友")
        assert progress.total == 10
        assert progress.current == 0
        assert progress.success == 0
        assert progress.failed == 0

    def test_start_target(self, monkeypatch, capsys):
        """测试开始处理目标。"""
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        progress = TargetProgress(total_targets=5, label="好友")
        progress.start_target("张三")
        assert progress.current == 1
        captured = capsys.readouterr()
        assert "[1/5] 好友: 张三" in captured.out

    def test_finish_target_success(self):
        """测试完成成功目标。"""
        progress = TargetProgress(total_targets=5)
        progress.start_target("张三")
        progress.finish_target("success")
        assert progress.success == 1
        assert progress.failed == 0

    def test_finish_target_failed(self):
        """测试完成失败目标。"""
        progress = TargetProgress(total_targets=5)
        progress.start_target("张三")
        progress.finish_target("failed")
        assert progress.success == 0
        assert progress.failed == 1

    def test_multiple_targets(self):
        """测试多个目标。"""
        progress = TargetProgress(total_targets=5)
        progress.start_target("张三")
        progress.finish_target("success")
        progress.start_target("李四")
        progress.finish_target("failed")
        progress.start_target("王五")
        progress.finish_target("success")

        assert progress.current == 3
        assert progress.success == 2
        assert progress.failed == 1

    def test_get_summary(self):
        """测试获取摘要。"""
        progress = TargetProgress(total_targets=5)
        progress.start_target("张三")
        progress.finish_target("success")
        progress.start_target("李四")
        progress.finish_target("failed")

        summary = progress.get_summary()
        assert "完成 2/5" in summary
        assert "成功 1" in summary
        assert "失败 1" in summary


class TestProgressFactories:
    """测试进度工厂函数。"""

    def test_create_account_progress(self):
        """测试创建账号进度。"""
        from app.progress import create_account_progress

        multi_stage, target_progress = create_account_progress("account1", 10)
        assert len(multi_stage.stages) == 3
        assert "account1" in multi_stage.stages[2]
        assert target_progress.total == 10
        assert target_progress.label == "好友"

    def test_create_single_run_progress(self):
        """测试创建单次运行进度。"""
        from app.progress import create_single_run_progress

        multi_stage, target_progress = create_single_run_progress(8)
        assert len(multi_stage.stages) == 3
        assert target_progress.total == 8
        assert target_progress.label == "好友"
