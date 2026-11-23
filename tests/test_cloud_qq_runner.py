"""Cloud QQ cron must use a private API and never duplicate a daily batch."""

import importlib.util
import json
import tempfile
import sys
import unittest
from io import StringIO
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
sys.path.insert(0, str(ROOT / "cloud-skill/xuhuohua-cloud/scripts"))
runner = load("cloud_qq_runner", ROOT / "cloud-skill/xuhuohua-cloud/scripts/qq-run.py")
BEIJING = timezone(timedelta(hours=8))


class CloudQQRunnerTests(unittest.TestCase):
    def test_image_confirmation_requires_matching_sender_id_signature_and_reference(self):
        entry = {"message_id": 41, "sender": {"user_id": 99}, "message": [
            {"type": "image", "data": {"file": "image-id.png"}},
            {"type": "text", "data": {"text": "签名"}},
        ]}
        for detail, expected in [
            (entry, True),
            ({**entry, "sender": {"user_id": 77}}, False),
            ({**entry, "message_id": 42}, False),
            ({**entry, "message": [{"type": "image", "data": {"file": "other.png"}},
                                   entry["message"][1]]}, False),
            ({**entry, "message": [entry["message"][0]]}, False),
        ]:
            with self.subTest(detail=detail), patch.object(
                runner, "onebot", side_effect=[{"messages": [entry]}, detail]
            ) as api:
                self.assertEqual(runner.confirm_sent("11", 41, "99", "摘要", "local", "",
                                                     attempts=1, image_tail="签名"), expected)
                self.assertEqual(api.call_args.args[:2], ("get_msg", {"message_id": 41}))

    def test_image_timeout_recovers_once_using_downloaded_bytes(self):
        image = b"test content"
        payload = [{"type": "image", "data": {"file": "base64://" + runner.base64.b64encode(image).decode()}}]
        row = {"message_id": 41, "user_id": 99, "time": 1001, "message": [
            {"type": "image", "data": {"file": "opaque-reference"}},
        ]}
        digest = runner.hashlib.sha256(image).hexdigest()
        call_results = [{"messages": []}, RuntimeError("timeout"), {"messages": [row]}, row,
                        {"file": "/app/.config/QQ/media/picture.png"}]
        with patch.object(runner, "onebot", side_effect=call_results) as api, \
             patch.object(runner.time, "time", return_value=1000), \
             patch.object(runner.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stdout=digest + "  /app/.config/QQ/media/picture.png")):
            runner.send_checked("12", payload, "摘要", "", "99", "local", "token")
        self.assertEqual([call.args[0] for call in api.call_args_list],
                         ["get_friend_msg_history", "send_private_msg", "get_friend_msg_history", "get_msg", "get_image"])

    def test_unverified_runtime_cannot_send_or_consume_daily_state(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            (skill / "qq-maintenance").write_text("version trial", encoding="utf-8")
            now = datetime.now(BEIJING).replace(hour=9, minute=0)
            with patch.object(runner, "SKILL", skill), \
                 patch.object(runner, "settings", return_value=({}, "09:00:00", ["123456"], "test")), \
                 patch.object(runner, "start_container") as start, \
                 patch.object(runner, "onebot") as api, \
                 patch.object(runner, "save_result") as save:
                self.assertEqual(runner.run_due(now), "maintenance")
                start.assert_not_called()
                api.assert_not_called()
                save.assert_not_called()
            self.assertFalse((skill / "qq-run-state.json").exists())

    def test_private_runtime_override_is_used_for_start_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            local = skill / "compose.qq.local.yaml"
            with patch.object(runner, "SKILL", skill), patch.object(runner.subprocess, "run") as run:
                runner._compose("up", "-d", "napcat")
                self.assertNotIn(str(local), run.call_args.args[0])
                local.write_text("services: {}", encoding="utf-8")
                for command in [("up", "-d", "napcat"), ("stop", "-t", "20", "napcat")]:
                    runner._compose(*command)
                    self.assertIn(str(local), run.call_args.args[0])

    def test_failed_session_check_never_prints_pass(self):
        with patch.object(runner, "start_container"), \
             patch.object(runner, "wait_for_login", side_effect=RuntimeError("expired")), \
             patch.object(runner, "stop_container") as stopped, \
             patch("builtins.print") as output:
            with self.assertRaisesRegex(RuntimeError, "expired"):
                runner.session_check("345678")
        stopped.assert_called_once()
        output.assert_not_called()

    def test_correct_account_but_offline_is_rejected(self):
        with patch.object(runner, "onebot", side_effect=[{"user_id": 345678}, {"online": False}]):
            with self.assertRaisesRegex(RuntimeError, "不在线"):
                runner.check_login("http://local", "secret", "345678")

    def test_quick_login_sends_account_as_string(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "webui.json"
            config.write_text(json.dumps({"token": "test-only-token"}), encoding="utf-8")
            calls = []

            def reply(request, **kwargs):
                calls.append(request)
                return StringIO(json.dumps({"data": {"Credential": "test-only"}}
                                           if len(calls) == 1 else {"code": 0}))

            with patch.object(runner, "WEBUI_CONFIG", config), \
                 patch.object(runner.urllib.request, "urlopen", side_effect=reply):
                self.assertTrue(runner.webui_quick_login("345678"))
            self.assertEqual(json.loads(calls[1].data), {"uin": "345678"})

    def test_stop_targets_only_main_qq_and_requires_clean_exit(self):
        def inspected(running, exit_code=0):
            return SimpleNamespace(stdout=json.dumps([{"State": {"Running": running, "ExitCode": exit_code}}]))
        for exit_code in [0, 137]:
            with self.subTest(exit_code=exit_code), \
                 patch.object(runner.subprocess, "run", side_effect=[
                     inspected(True),
                     SimpleNamespace(stdout="PID COMMAND\n133 /opt/QQ/qq --no-sandbox\n139 /opt/QQ/qq --type=zygote --no-sandbox\n"),
                     SimpleNamespace(stdout=""), inspected(False, exit_code)]) as run, \
                 patch.object(runner, "_compose"):
                if exit_code:
                    with self.assertRaisesRegex(RuntimeError, "未正常退出"):
                        runner.stop_container()
                else:
                    runner.stop_container()
                self.assertEqual(run.call_args_list[2].args[0],
                                 ["docker", "exec", "xuhuohua-napcat", "kill", "-TERM", "133"])

    def test_expired_ticket_is_reported_without_repeated_quick_login(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "webui.json"
            config.write_text(json.dumps({"token": "test-only-token"}), encoding="utf-8")
            replies = [StringIO('{"data":{"Credential":"test-only"}}'),
                       StringIO(json.dumps({"code": -1, "message": "登录态已失效，请重新登录。"}))]
            with patch.object(runner, "WEBUI_CONFIG", config), \
                 patch.object(runner.urllib.request, "urlopen", side_effect=replies) as request:
                with self.assertRaisesRegex(runner.QQLoginExpired, "需要扫码"):
                    runner.webui_quick_login("345678")
            self.assertEqual(request.call_count, 2)
        with patch.object(runner, "endpoint", side_effect=RuntimeError("not online")), \
             patch.object(runner, "webui_quick_login", side_effect=runner.QQLoginExpired("expired")) as quick, \
             patch.object(runner.time, "sleep"), \
             patch.object(runner.time, "monotonic", side_effect=[0, 0, 11, 11]):
            with self.assertRaises(runner.QQLoginExpired):
                runner.wait_for_login("345678")
        quick.assert_called_once()

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
            sent_ids = iter((101, 102))

            def fake_onebot(action, payload, *_):
                calls.append(action)
                if action == "get_friend_list":
                    return [{"user_id": 123456, "remark": "甲"},
                            {"user_id": 234567, "nickname": "乙"}]
                if action == "send_private_msg":
                    return {"message_id": next(sent_ids)}
                if action == "get_friend_msg_history":
                    message_id = 101 if payload["user_id"] == 123456 else 102
                    return {"messages": [{"message_id": message_id,
                                           "sender": {"user_id": 345678},
                                           "raw_message": "早安\n来自捞鱼自动续火花"}]}
                raise AssertionError(action)

            with patch.object(runner, "SKILL", skill), patch.object(runner, "QQ_CONFIG", config), \
                 patch.object(runner, "STATE", skill / "state.json"), \
                 patch.object(runner, "RESULT", skill / "result.json"), \
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
            self.assertEqual(calls, ["get_friend_list", "send_private_msg", "get_friend_msg_history",
                                     "send_private_msg", "get_friend_msg_history"])
            stats = json.loads(config.read_text(encoding="utf-8"))["stats"]
            self.assertEqual((stats["friendSparkSucceeded"], stats["friendSparkFailed"]), (2, 0))
            self.assertTrue(stats["friendSparkSessionStopped"])
            detail = json.loads((skill / "result.json").read_text(encoding="utf-8"))
            self.assertEqual([x["name"] for x in detail["recipients"]], ["甲", "乙"])
            self.assertTrue(all(x["confirmed"] for x in detail["recipients"]))
            self.assertIn("来自捞鱼自动续火花", detail["recipients"][0]["message"])

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
                 patch.object(runner, "RESULT", skill / "result.json"), \
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
                 patch.object(runner, "RESULT", skill / "result.json"), \
                 patch.object(runner, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=1)), \
                 patch.object(runner, "start_container"), \
                 patch.object(runner, "wait_for_login", side_effect=RuntimeError("offline")), \
                 patch.object(runner, "stop_container") as stopped, patch("builtins.print"):
                self.assertEqual(runner.run_due(now), "failed")
            stopped.assert_called_once()
            stats = json.loads(config.read_text(encoding="utf-8"))["stats"]
            self.assertEqual(stats["friendSparkFailed"], 1)
            self.assertTrue(stats["friendSparkSessionStopped"])

    def test_message_id_without_matching_history_is_failure(self):
        history = {"messages": [{"message_id": 88, "sender": {"user_id": 345678},
                                  "raw_message": "另一条消息"}]}
        with patch.object(runner, "onebot", return_value=history), patch.object(runner.time, "sleep"):
            self.assertFalse(runner.confirm_sent("123456", 88, "345678", "早安", "http://local", "token"))

    def test_matching_history_is_confirmed(self):
        history = {"messages": [{"message_id": 88, "sender": {"user_id": 345678},
                                  "raw_message": "早安\n来自捞鱼自动续火花"}]}
        self.assertTrue(runner.history_confirms(history, 88, "345678",
                                                "早安\n来自捞鱼自动续火花"))

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
