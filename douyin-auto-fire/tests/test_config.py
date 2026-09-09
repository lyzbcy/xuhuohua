import json
from pathlib import Path

import pytest

from app.config import ConfigError, load_task
from app.models import Settings


def settings_for(path: Path) -> Settings:
    return Settings(
        task_config_path=path,
        storage_state='{"cookies": [], "origins": []}',
        cookie=None,
        headless=True,
        browser_path=None,
        artifacts_dir=path.parent / "artifacts",
        trace=True,
    )


def write_config(tmp_path: Path, payload: dict) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "tasks.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_loads_multiple_targets_and_text(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "targets": [
                {"name": "好友A", "messages": [{"type": "text", "content": "你好"}]},
                {"name": "好友B", "messages": [{"type": "text", "content": "早上好"}]},
            ]
        },
    )

    task = load_task(settings_for(path))

    assert [target.name for target in task.targets] == ["好友A", "好友B"]
    assert task.targets[0].messages[0].content == "你好"


def test_rejects_empty_targets(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"targets": []})

    with pytest.raises(ConfigError, match="targets 必须是非空数组"):
        load_task(settings_for(path))


def test_rejects_missing_image(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {"targets": [{"name": "好友A", "messages": [{"type": "image", "path": "data/missing.png"}]}]},
    )

    with pytest.raises(ConfigError, match="文件不存在"):
        load_task(settings_for(path))


def test_requires_sticker_mapping(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {"targets": [{"name": "好友A", "messages": [{"type": "douyin_sticker", "sticker": "未知"}]}]},
    )

    with pytest.raises(ConfigError, match="原生表情未在"):
        load_task(settings_for(path))


def test_loads_sticker_mapping(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {"targets": [{"name": "好友A", "messages": [{"type": "douyin_sticker", "sticker": "比心"}]}]},
    )
    (path.parent / "stickers.json").write_text(
        json.dumps({"比心": {"accessible_name": "比心", "fallback_index": 2}}, ensure_ascii=False),
        encoding="utf-8",
    )

    task = load_task(settings_for(path))

    assert task.stickers["比心"].fallback_index == 2


def test_loads_simple_config(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "friends": ["好友A", "好友B"],
            "messages": [{"type": "text", "value": "你好"}],
        },
    )

    task = load_task(settings_for(path))

    assert len(task.targets) == 2
    assert task.targets[1].messages[0].content == "你好"


def test_loads_target_open_retries_and_timeout(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "targets": [{"name": "好友A", "messages": [{"type": "text", "content": "你好"}]}],
            "target_open_retries": 3,
            "target_open_timeout_seconds": 20,
        },
    )

    task = load_task(settings_for(path))

    assert task.target_open_retries == 3
    assert task.target_open_timeout_seconds == 20


def test_defaults_target_open_retries_and_timeout(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"targets": [{"name": "好友A", "messages": [{"type": "text", "content": "你好"}]}]})

    task = load_task(settings_for(path))

    assert task.target_open_retries == 1
    assert task.target_open_timeout_seconds == 15.0


def test_rejects_negative_target_open_retries(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "targets": [{"name": "好友A", "messages": [{"type": "text", "content": "你好"}]}],
            "target_open_retries": -1,
        },
    )

    with pytest.raises(ConfigError, match="target_open_retries"):
        load_task(settings_for(path))


def test_rejects_non_positive_target_open_timeout(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        {
            "targets": [{"name": "好友A", "messages": [{"type": "text", "content": "你好"}]}],
            "target_open_timeout_seconds": 0,
        },
    )

    with pytest.raises(ConfigError, match="target_open_timeout_seconds"):
        load_task(settings_for(path))
