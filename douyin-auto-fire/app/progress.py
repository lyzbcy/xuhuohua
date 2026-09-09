"""进度显示模块。"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal


@dataclass
class ProgressBar:
    """简单的命令行进度条。

    不依赖第三方库，使用纯ASCII字符绘制。
    """

    total: int
    current: int = 0
    prefix: str = ""
    width: int = 40
    fill: str = "█"
    empty: str = "░"

    def update(self, step: int = 1):
        """更新进度。"""
        self.current = min(self.current + step, self.total)
        self._render()

    def _render(self):
        """渲染进度条到终端。"""
        if self.total == 0:
            percent = 100.0
            filled_length = self.width
        else:
            percent = (self.current / self.total) * 100
            filled_length = int(self.width * self.current / self.total)

        bar = self.fill * filled_length + self.empty * (self.width - filled_length)
        output = f"\r{self.prefix} |{bar}| {self.current}/{self.total} ({percent:.1f}%)"

        # 只在支持回车覆盖的终端输出
        if sys.stdout.isatty():
            sys.stdout.write(output)
            sys.stdout.flush()

    def finish(self):
        """完成进度条，换行。"""
        if sys.stdout.isatty():
            sys.stdout.write("\n")
            sys.stdout.flush()


class MultiStageProgress:
    """多阶段进度跟踪。

    支持多个阶段的进度显示，例如：
    [1/3] 打开浏览器...
    [2/3] 登录验证...
    [3/3] 发送消息... |████████████░░░░| 8/10 (80.0%)
    """

    def __init__(self, stages: list[str]):
        """初始化多阶段进度。

        Args:
            stages: 阶段名称列表
        """
        self.stages = stages
        self.current_stage = 0
        self.progress_bar: ProgressBar | None = None

    def start_stage(self, stage_index: int, total_items: int = 0):
        """开始一个阶段。

        Args:
            stage_index: 阶段索引（从0开始）
            total_items: 该阶段的总项目数（如果需要进度条）
        """
        self.current_stage = stage_index
        stage_name = self.stages[stage_index]
        prefix = f"[{stage_index + 1}/{len(self.stages)}]"

        if total_items > 0:
            # 有具体数量，显示进度条
            self.progress_bar = ProgressBar(
                total=total_items,
                prefix=f"{prefix} {stage_name}",
                width=30,
            )
            self.progress_bar._render()
        else:
            # 没有具体数量，只显示状态
            if sys.stdout.isatty():
                print(f"{prefix} {stage_name}...", flush=True)
            self.progress_bar = None

    def update_progress(self, step: int = 1):
        """更新当前阶段的进度。"""
        if self.progress_bar:
            self.progress_bar.update(step)

    def finish_stage(self):
        """完成当前阶段。"""
        if self.progress_bar:
            self.progress_bar.finish()
            self.progress_bar = None

    def finish_all(self):
        """完成所有阶段。"""
        if self.progress_bar:
            self.progress_bar.finish()
        if sys.stdout.isatty():
            print("✓ 所有阶段完成", flush=True)


class TargetProgress:
    """单个目标的进度跟踪（用于多账号或多好友）。"""

    def __init__(self, total_targets: int, label: str = "处理目标"):
        """初始化目标进度。

        Args:
            total_targets: 总目标数
            label: 进度标签
        """
        self.total = total_targets
        self.current = 0
        self.success = 0
        self.failed = 0
        self.label = label

    def start_target(self, target_name: str):
        """开始处理一个目标。"""
        self.current += 1
        if sys.stdout.isatty():
            print(f"\n[{self.current}/{self.total}] {self.label}: {target_name}", flush=True)

    def finish_target(self, status: Literal["success", "failed"]):
        """完成一个目标。"""
        if status == "success":
            self.success += 1
        else:
            self.failed += 1

    def get_summary(self) -> str:
        """获取摘要信息。"""
        return f"完成 {self.current}/{self.total}，成功 {self.success}，失败 {self.failed}"


def create_account_progress(account_id: str, total_targets: int) -> tuple[MultiStageProgress, TargetProgress]:
    """创建账号执行的进度跟踪器。

    Args:
        account_id: 账号ID
        total_targets: 总目标数

    Returns:
        (多阶段进度, 目标进度)
    """
    stages = [
        "打开浏览器",
        "验证登录",
        f"发送消息 ({account_id})",
    ]
    multi_stage = MultiStageProgress(stages)
    target_progress = TargetProgress(total_targets, label="好友")
    return multi_stage, target_progress


def create_single_run_progress(total_targets: int) -> tuple[MultiStageProgress, TargetProgress]:
    """创建单次运行的进度跟踪器。

    Args:
        total_targets: 总目标数

    Returns:
        (多阶段进度, 目标进度)
    """
    stages = [
        "打开浏览器",
        "验证登录",
        "发送消息",
    ]
    multi_stage = MultiStageProgress(stages)
    target_progress = TargetProgress(total_targets, label="好友")
    return multi_stage, target_progress
