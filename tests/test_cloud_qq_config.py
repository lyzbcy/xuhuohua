"""Cloud QQ configuration must preserve user settings and never send messages."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "cloud-skill/xuhuohua-cloud/scripts/configure-qq.py"
spec = importlib.util.spec_from_file_location("configure_cloud_qq", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CloudQQConfigTests(unittest.TestCase):
    def test_configure_preserves_other_tasks_and_sets_daily_friend_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"groupSpark_enable": True, "stats": {"todayProcessed": 2}}), encoding="utf-8")
            result = module.configure(path, "08:30", "123456,234567,123456", "早安 ✨")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result, {"count": 2, "time": "08:30:00"})
            self.assertEqual(data["friendSpark_targets"], "123456,234567")
            self.assertEqual(data["friendSpark_message"], "早安 ✨")
            self.assertTrue(data["groupSpark_enable"])
            self.assertEqual(data["stats"]["todayProcessed"], 2)

    def test_invalid_targets_do_not_modify_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"enabled": false}', encoding="utf-8")
            with self.assertRaises(ValueError):
                module.configure(path, "08:30", "123456,bad", "✨")
            self.assertEqual(path.read_text(encoding="utf-8"), '{"enabled": false}')


if __name__ == "__main__":
    unittest.main()
