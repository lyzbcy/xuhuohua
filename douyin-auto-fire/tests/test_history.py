from pathlib import Path

import pytest

from app.history import AlreadyRunningError, History, run_lock


def test_history_persists_success(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    history = History(path)
    key = history.key("task", history.run_date("Asia/Shanghai"), "好友A", "0-abc")

    history.mark_success(key)

    assert History(path).contains(key)


def test_corrupt_history_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="发送历史损坏"):
        History(path)


def test_run_lock_rejects_second_process(tmp_path: Path) -> None:
    path = tmp_path / "run.lock"

    with run_lock(path):
        with pytest.raises(AlreadyRunningError):
            with run_lock(path):
                pass

    assert not path.exists()
