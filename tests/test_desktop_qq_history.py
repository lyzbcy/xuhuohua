"""Desktop QQ must not report success before OneBot history confirms it."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))
from backend import qq  # noqa: E402


class DesktopQQHistoryTests(unittest.TestCase):
    def test_matching_message_id_sender_and_body_is_success(self):
        response = {"data": {"messages": [{
            "message_id": 91,
            "sender": {"user_id": 345678},
            "raw_message": "早安\n来自捞鱼自动续火花",
        }]}}
        with patch.object(qq, "_onebot_call", return_value=response):
            self.assertTrue(qq._confirm_private_message(
                6098, "token", "123456", 91, "345678",
                "早安\n来自捞鱼自动续火花"))

    def test_mismatched_body_never_becomes_success(self):
        response = {"data": {"messages": [{
            "message_id": 91,
            "sender": {"user_id": 345678},
            "raw_message": "另一条消息",
        }]}}
        with patch.object(qq, "_onebot_call", return_value=response), \
             patch.object(qq.time, "sleep"):
            self.assertFalse(qq._confirm_private_message(
                6098, "token", "123456", 91, "345678", "早安"))


if __name__ == "__main__":
    unittest.main()
