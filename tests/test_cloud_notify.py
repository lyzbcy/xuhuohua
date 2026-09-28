"""Cloud QQ result semantics without sending real messages."""

import importlib.util
import io
import json
import tempfile
import sys
from types import SimpleNamespace
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cloud-skill/xuhuohua-cloud/scripts/notify-result.py"
spec = importlib.util.spec_from_file_location("cloud_notify_result", SCRIPT)
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)
BEIJING = timezone(timedelta(hours=8))


class CloudNotifyTests(unittest.TestCase):
    def setUp(self):
        self.due = datetime(2026, 9, 29, 8, 30, tzinfo=BEIJING)
        self.config = {"enabled": True, "friendSpark_enable": True,
                       "friendSpark_time": "08:30:00", "stats": {}}

    def test_qq_reports_only_fresh_complete_batch(self):
        self.assertIsNone(notify.qq_result(self.config, self.due - timedelta(seconds=1)))
        self.config["stats"] = {"friendSparkCompletedAt": int((self.due - timedelta(days=1)).timestamp() * 1000),
                                "friendSparkSucceeded": 2, "friendSparkFailed": 0}
        self.assertIsNone(notify.qq_result(self.config, self.due + timedelta(minutes=1)))
        self.config["stats"]["friendSparkCompletedAt"] = int((self.due + timedelta(seconds=30)).timestamp() * 1000)
        result = notify.qq_result(self.config, self.due + timedelta(minutes=1))
        self.assertEqual(result[0], "成功")
        self.assertIn("成功 2，失败 0", result[1])

    def test_qq_partial_failure_and_missing_run_are_failures(self):
        self.config["stats"] = {"friendSparkCompletedAt": int((self.due + timedelta(minutes=1)).timestamp() * 1000),
                                "friendSparkSucceeded": 1, "friendSparkFailed": 1}
        self.assertEqual(notify.qq_result(self.config, self.due + timedelta(minutes=2))[0], "失败")
        self.config["stats"] = {}
        self.assertIsNone(notify.qq_result(self.config, self.due + timedelta(minutes=59)))
        self.assertEqual(notify.qq_result(self.config, self.due + timedelta(minutes=60))[0], "失败")

    def test_disabled_qq_is_not_reported(self):
        self.config["friendSpark_enable"] = False
        self.assertIsNone(notify.qq_result(self.config, self.due + timedelta(hours=2)))

    def test_optional_skip_is_silent_but_test_requires_adapter(self):
        with patch.object(notify, "webhook_url", return_value=None), \
             patch.object(notify, "command_path", return_value=None), \
             patch.object(sys, "argv", ["notify-result.py", "qq"]):
            self.assertEqual(notify.main(), 0)
        with patch.object(notify, "webhook_url", return_value=None), \
             patch.object(notify, "command_path", return_value=None), \
             patch.object(sys, "argv", ["notify-result.py", "test"]):
            self.assertEqual(notify.main(), 2)

    def test_qq_result_is_sent_once_per_beijing_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "config.json"
            self.config["stats"] = {
                "friendSparkCompletedAt": int((self.due + timedelta(seconds=15)).timestamp() * 1000),
                "friendSparkSucceeded": 1, "friendSparkFailed": 0,
            }
            config_file.write_text(json.dumps(self.config), encoding="utf-8")
            with patch.object(notify, "QQ_CONFIG", config_file), \
                 patch.object(notify, "STATE_FILE", root / "state.json"), \
                 patch.object(notify, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=1)), \
                 patch.object(notify, "send", return_value=True) as sent:
                now = self.due + timedelta(minutes=1)
                self.assertEqual(notify.notify_qq(Path("unused"), now), 0)
                self.assertEqual(notify.notify_qq(Path("unused"), now), 0)
                sent.assert_called_once()
                self.assertEqual(json.loads((root / "state.json").read_text())["qq_notified_day"], "2026-09-29")

    def test_release_prompt_advises_optional_webhook_and_update(self):
        import sys
        sys.path.insert(0, str(ROOT / "software"))
        from backend.cloud import prompt
        value = prompt()
        self.assertIn("企业微信群机器人 webhook", value)
        self.assertIn("可选项", value)
        self.assertIn("notify-result.py test", value)
        self.assertIn("check-update.sh", value)

    def test_group_webhook_receives_text_without_logging_key(self):
        url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + "a" * 36
        file_stub = SimpleNamespace(exists=lambda: True,
                                    stat=lambda: SimpleNamespace(st_mode=0o600),
                                    read_text=lambda **_: url)
        with patch.object(notify, "WEBHOOK_FILE", file_stub), \
             patch.object(notify.urllib.request, "urlopen", return_value=io.BytesIO(b'{"errcode":0}')) as opened:
            self.assertEqual(notify.transport(), ("webhook", url))
            self.assertTrue(notify.send(("webhook", url), "续火花成功"))
            request = opened.call_args.args[0]
            self.assertEqual(json.loads(request.data)["text"]["content"], "续火花成功")

    def test_non_wecom_webhook_is_rejected(self):
        file_stub = SimpleNamespace(exists=lambda: True,
                                    stat=lambda: SimpleNamespace(st_mode=0o600),
                                    read_text=lambda **_: "https://example.com/cgi-bin/webhook/send?key=secret")
        with patch.object(notify, "WEBHOOK_FILE", file_stub):
            with self.assertRaises(ValueError):
                notify.webhook_url()

    def test_portable_copy_excludes_private_notification_state(self):
        from scripts.make_portable_zip import copy_filtered
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            target = Path(directory) / "target"
            source.mkdir()
            (source / "SKILL.md").write_text("public", encoding="utf-8")
            (source / "notify-command").write_text("private", encoding="utf-8")
            (source / "notify-webhook").write_text("private", encoding="utf-8")
            (source / "notify-state.json").write_text("private", encoding="utf-8")
            copy_filtered(source, target)
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["SKILL.md"])


if __name__ == "__main__":
    unittest.main()
