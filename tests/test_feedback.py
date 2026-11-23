import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software"))
from backend import feedback


class FeedbackTests(unittest.TestCase):
    def test_clean_install_uses_relay_and_checks_matching_receipt(self):
        with patch.dict(os.environ, {"XUHUOHUA_FEEDBACK_WEBHOOK": ""}), \
             patch.object(feedback, "CHANNEL_FILE", Path("missing-feedback-test-config.json")), \
             patch.object(feedback, "build_opener") as opener, patch.object(feedback.logger, "ok"):
            sent = []
            def opened(request, **kwargs):
                self.assertEqual(request.full_url, feedback.RELAY_URL)
                body = json.loads(request.data)
                self.assertTrue(body["text"]["content"].startswith("捞鱼火花管家 v"))
                sent.append(body["request_id"])
                result = {"errcode": 0, "state": "delivered", "request_id": body["request_id"]}
                response = MagicMock()
                response.__enter__.return_value.read.return_value = json.dumps(result).encode()
                return response
            opener.return_value.open.side_effect = opened
            for _ in range(2):
                self.assertTrue(feedback.send("捞鱼火花管家", "0.14.14", "", "测试反馈", False)["ok"])
            self.assertEqual(sent[0], sent[1])

    @patch.object(feedback.logger, "ok")
    @patch.object(feedback.logger, "today_log_text",
                  return_value="[2026-11-23 16:00:00] [FAIL] [qq] 私聊正文和账号")
    @patch.object(feedback, "build_opener")
    @patch.object(feedback, "_endpoint",
                  return_value="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=mock_key_00001")
    def test_wecom_receipt_and_diagnostic_privacy(self, endpoint, opener, logs, log_ok):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"errcode":0}'
        opened = opener.return_value.open
        opened.return_value = response
        result = feedback.send("捞鱼火花管家", "0.14.7", "定时任务", "无法启动", True)
        self.assertTrue(result["ok"])
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        body = json.loads(request.data)
        self.assertEqual(body["msgtype"], "text")
        text = body["text"]["content"]
        for expected in ("捞鱼火花管家 v0.14.7", "定时任务", "无法启动", "FAIL qq"):
            self.assertIn(expected, text)
        self.assertNotIn("私聊正文和账号", text)

        response.__enter__.return_value.read.return_value = b'{"errcode":93000}'
        with patch.object(feedback.logger, "warn"):
            self.assertFalse(feedback.send("捞鱼火花管家", "0.14.7", "", "同一问题", False)["ok"])
        text = json.loads(opened.call_args.args[0].data)["text"]["content"]
        self.assertNotIn("诊断日志", text)

    @patch.object(feedback, "build_opener")
    def test_invalid_input_does_not_send(self, opener):
        self.assertFalse(feedback.send("App", "1", "", "   ", True)["ok"])
        self.assertFalse(feedback.send("App", "1", "", "字" * 400, True)["ok"])
        self.assertFalse(feedback.send("App", "1", "unknown", "问题", True)["ok"])
        opener.assert_not_called()
