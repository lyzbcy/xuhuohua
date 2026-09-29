"""Cloud QQ cron must use a private API and never duplicate a daily batch."""

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


configure = load("cloud_onebot_config", ROOT / "cloud-skill/xuhuohua-cloud/scripts/configure-onebot.py")
runner = load("cloud_qq_runner", ROOT / "cloud-skill/xuhuohua-cloud/scripts/qq-run.py")
BEIJING = timezone(timedelta(hours=8))


class CloudQQRunnerTests(unittest.TestCase):
    def test_onebot_setup_is_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onebot11_123456.json"
            path.write_text(json.dumps({"network": {"httpServers": []}}), encoding="utf-8")
            self.assertTrue(configure.configure(path))
            first = json.loads(path.read_text(encoding="utf-8"))
            server = first["network"]["httpServers"][0]
            self.assertEqual(server["name"], "xuhuohua-local")
            self.assertFalse(server["enableCors"])
            self.assertTrue(server["token"])
            self.assertFalse(configure.configure(path))
            self.assertEqual(first, json.loads(path.read_text(encoding="utf-8")))

    def test_due_batch_runs_once_and_updates_notification_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            config = skill / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"enabled": True, "friendSpark_enable": True,
                                          "friendSpark_time": "09:00:00",
                                          "friendSpark_targets": "123456,234567",
                                          "friendSpark_message": "早安"}), encoding="utf-8")
            (skill / "qq-data/config/onebot11_345678.json").write_text("{}", encoding="utf-8")
            now = datetime.now(BEIJING).replace(hour=9, minute=0, second=0, microsecond=0)
            calls = []

            def fake_onebot(action, payload, *_):
                calls.append(action)
                return {"message_id": len(calls)}

            with patch.object(runner, "SKILL", skill), patch.object(runner, "QQ_CONFIG", config), \
                 patch.object(runner, "STATE", skill / "state.json"), \
                 patch.object(runner, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=1)), \
                 patch.object(runner, "start_container") as started, \
                 patch.object(runner, "wait_for_login", return_value=("http://local", "secret")), \
                 patch.object(runner, "stop_container") as stopped, \
                 patch.object(runner, "onebot", side_effect=fake_onebot), \
                 patch("builtins.print"):
                self.assertEqual(runner.run_due(now), "ok")
                self.assertEqual(runner.run_due(now), "already-ran")
            started.assert_called_once()
            stopped.assert_called_once()
            self.assertEqual(calls, ["send_private_msg", "send_private_msg"])
            stats = json.loads(config.read_text(encoding="utf-8"))["stats"]
            self.assertEqual((stats["friendSparkSucceeded"], stats["friendSparkFailed"]), (2, 0))
            self.assertTrue(stats["friendSparkSessionStopped"])

    def test_dry_run_does_not_send_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            config = skill / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"enabled": True, "friendSpark_enable": True,
                                          "friendSpark_time": "09:00:00",
                                          "friendSpark_targets": "123456",
                                          "friendSpark_message": "早安"}), encoding="utf-8")
            (skill / "qq-data/config/onebot11_345678.json").write_text("{}", encoding="utf-8")
            with patch.object(runner, "SKILL", skill), patch.object(runner, "QQ_CONFIG", config), \
                 patch.object(runner, "STATE", skill / "state.json"), \
                 patch.object(runner, "endpoint", return_value=("http://local", "secret")), \
                 patch.object(runner, "check_login") as check:
                self.assertEqual(runner.run_due(dry_run=True), "ready:1")
                check.assert_called_once()
            self.assertFalse((skill / "state.json").exists())

    def test_offline_session_uses_quick_login_then_stops_without_sending(self):
        with patch.object(runner, "start_container") as started, \
             patch.object(runner, "wait_for_login", return_value=("http://local", "secret")) as waited, \
             patch.object(runner, "stop_container") as stopped, \
             patch("builtins.print"):
            self.assertEqual(runner.session_check("345678"), "session-ready")
        started.assert_called_once()
        waited.assert_called_once_with("345678")
        stopped.assert_called_once()

    def test_failed_login_still_stops_container_and_marks_batch_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            config = skill / "qq-data/config/plugins/napcat-plugin-auto-tasks/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"enabled": True, "friendSpark_enable": True,
                                          "friendSpark_time": "09:00:00",
                                          "friendSpark_targets": "123456",
                                          "friendSpark_message": "早安"}), encoding="utf-8")
            (skill / "qq-data/config/onebot11_345678.json").write_text("{}", encoding="utf-8")
            now = datetime.now(BEIJING).replace(hour=9, minute=0, second=0, microsecond=0)
            with patch.object(runner, "SKILL", skill), patch.object(runner, "QQ_CONFIG", config), \
                 patch.object(runner, "STATE", skill / "state.json"), \
                 patch.object(runner, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=1)), \
                 patch.object(runner, "start_container"), \
                 patch.object(runner, "wait_for_login", side_effect=RuntimeError("offline")), \
                 patch.object(runner, "stop_container") as stopped, patch("builtins.print"):
                self.assertEqual(runner.run_due(now), "failed")
            stopped.assert_called_once()
            stats = json.loads(config.read_text(encoding="utf-8"))["stats"]
            self.assertEqual(stats["friendSparkFailed"], 1)
            self.assertTrue(stats["friendSparkSessionStopped"])

    def test_wait_for_login_triggers_real_quick_login_action(self):
        with patch.object(runner, "endpoint", return_value=("http://local", "secret")), \
             patch.object(runner, "check_login", side_effect=[RuntimeError("offline"), None]), \
             patch.object(runner, "webui_quick_login", return_value=True) as quick, \
             patch.object(runner.time, "sleep"), \
             patch.object(runner.time, "monotonic", side_effect=[0, 0, 11, 11, 12, 13]):
            self.assertEqual(runner.wait_for_login("345678"), ("http://local", "secret"))
        quick.assert_called_once_with("345678")


if __name__ == "__main__":
    unittest.main()
