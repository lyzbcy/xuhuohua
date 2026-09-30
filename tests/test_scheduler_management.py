import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software"))
from backend import scheduler


class ScheduleManagementTests(unittest.TestCase):
    def test_selected_deletion_survives_repair_and_keeps_other_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            registered = set(scheduler.TASKS)
            config = Path(folder) / "schedule.json"
            config.write_text(json.dumps({"douyin_time": "09:00"}))
            def command(*args):
                name = args[args.index("/TN") + 1]
                if args[0] == "/Delete":
                    registered.remove(name)
                elif args[0] == "/Create":
                    registered.add(name)
                return subprocess.CompletedProcess(args, 0 if name in registered or args[0] == "/Delete" else 1, "", "")
            qq_config = {"friendSpark_enable": True, "friendSpark_targets": "123456", "friendSpark_time": "09:00:00"}
            with patch.object(scheduler, "SCHEDULE_FILE", config), patch.object(scheduler, "_run_schtasks", side_effect=command), patch("backend.qq.get_plugin_config", return_value=qq_config):
                selected = [scheduler.TASK_NAME, scheduler.QQ_START_TASK_NAME]
                self.assertTrue(scheduler.remove_tasks(selected)["ok"])
                scheduler.repair_all()
                self.assertFalse(registered.intersection(selected))
                self.assertEqual(registered, {scheduler.ROTATE_TASK_NAME, scheduler.WATCHDOG_TASK_NAME})
                self.assertEqual(json.loads(config.read_text(encoding="utf-8"))["douyin_time"], "09:00")
                self.assertTrue(scheduler.restore_task(scheduler.QQ_START_TASK_NAME)["ok"])
                self.assertIn(scheduler.QQ_START_TASK_NAME, registered)
                self.assertNotIn(scheduler.TASK_NAME, registered)

    def test_foreign_task_rejected_before_any_mutation(self):
        with patch.object(scheduler, "_run_schtasks") as command, patch.object(scheduler, "_set_disabled") as save:
            self.assertFalse(scheduler.remove_tasks([scheduler.TASK_NAME, "OtherApp"])["ok"])
            command.assert_not_called()
            save.assert_not_called()

    def test_failed_delete_does_not_disable_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(scheduler, "SCHEDULE_FILE", Path(folder) / "schedule.json"), patch.object(scheduler, "_run_schtasks", return_value=subprocess.CompletedProcess([], 1, "", "Access denied")):
                self.assertFalse(scheduler.remove_tasks([scheduler.WATCHDOG_TASK_NAME])["ok"])
                self.assertFalse(scheduler._disabled(scheduler.WATCHDOG_TASK_NAME))


if __name__ == "__main__":
    unittest.main()
