"""发布阻塞的回归测试；不启动 QQ、不发送消息。"""

import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "software"))
from backend import cloud, douyin, notify, qq, scheduler  # noqa: E402


class ReleasePathTests(unittest.TestCase):
    def test_douyin_browser_mode_defaults_to_headless_and_can_be_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            with patch.object(notify, "SETTINGS_FILE", settings), \
                 patch.object(douyin, "engine_python", return_value="python"):
                self.assertEqual(douyin._engine_env()["HEADLESS"], "true")
                notify.save_settings({"browser_headless": False})
                self.assertEqual(douyin._engine_env()["HEADLESS"], "false")

    def test_missing_registered_douyin_task_is_repaired_at_saved_time(self):
        with patch.object(scheduler, "_desired_douyin_time", return_value="08:30"), \
             patch.object(scheduler, "_needs_repair", return_value=True), \
             patch.object(scheduler, "register", return_value={"ok": True}) as register:
            self.assertTrue(scheduler.ensure_douyin()["ok"])
            register.assert_called_once_with("08:30")

    def test_existing_douyin_schedule_time_is_preserved_on_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            schedule_file = Path(directory) / "schedule.json"
            with patch.object(scheduler, "SCHEDULE_FILE", schedule_file), \
                 patch.object(scheduler, "_task_info", return_value={"exists": True,
                      "start_time": "8:30:00"}), \
                 patch.object(scheduler, "_needs_repair", return_value=False):
                self.assertTrue(scheduler.ensure_douyin()["ok"])
                self.assertEqual(json.loads(schedule_file.read_text(encoding="utf-8")),
                                 {"douyin_time": "08:30"})

    def test_watchdog_is_registered_every_thirty_minutes(self):
        with patch.object(scheduler, "_needs_repair", return_value=True), \
             patch.object(scheduler, "_run_schtasks", return_value=CompletedProcess([], 0, "", "")) as run:
            self.assertTrue(scheduler.ensure_watchdog()["ok"])
            args = run.call_args.args
            self.assertEqual(args[args.index("/MO") + 1], "30")
            self.assertIn("--repair-schedules", args[args.index("/TR") + 1])

    def test_cloud_export_excludes_local_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("0.13.6\n", encoding="ascii")
            skill = root / "cloud-skill" / "xuhuohua-cloud"
            (skill / "scripts").mkdir(parents=True)
            (skill / "SKILL.md").write_text("skill", encoding="utf-8")
            for name in ("install.sh", "install-qq.sh", "install-skill.sh",
                         "compose.qq.yaml", "qq-watchdog.sh", "verify-qq.sh",
                         "qq-qr.sh", "qq-login-page.sh", "qq-login-page.py",
                         "configure-qq.py", "prepare-douyin.sh",
                         "start-douyin-desktop.sh", "stop-douyin-desktop.sh",
                         "login-douyin.sh", "notify-result.py",
                         "check-update.sh", "update-skill.py"):
                (skill / "scripts" / name).write_text("test", encoding="utf-8")
            (skill / "scripts" / "qq-qr.sh").write_bytes(b"#!/bin/bash\r\necho ok\r\n")
            private = skill / "qq-data" / "config"
            private.mkdir(parents=True)
            (private / "plugins.json").write_text("secret", encoding="utf-8")
            (skill / "notify-webhook").write_text("private-url", encoding="utf-8")
            engine = root / "douyin-auto-fire"
            (engine / "app").mkdir(parents=True)
            (engine / "scripts").mkdir()
            for name in ("run.py", "requirements.txt", "config.example.json", "README.md", "LICENSE"):
                (engine / name).write_text("pass", encoding="utf-8")
            (engine / "scripts" / "login.py").write_text("pass", encoding="utf-8")
            (engine / "app" / "main.py").write_text("pass", encoding="utf-8")
            (engine / "storage-state.json").write_text("secret", encoding="utf-8")
            (engine / "config.json").write_text("secret", encoding="utf-8")
            plugin = root / "napcat-plugin-auto-tasks" / "dist"
            (plugin / "webui").mkdir(parents=True)
            for name in ("index.mjs", "package.json", "LICENSE", "webui/index.html"):
                (plugin / name).write_text("test", encoding="utf-8")
            (plugin / "config.json").write_text("secret", encoding="utf-8")
            with patch.object(cloud, "PROJECT_ROOT", root):
                self.assertTrue(cloud.export_bundle()["ok"])
            import zipfile
            with zipfile.ZipFile(root / cloud.EXPORT_NAME) as archive:
                self.assertIn("douyin-auto-fire/run.py", archive.namelist())
                self.assertIn("qq-plugin/index.mjs", archive.namelist())
                self.assertIn("qq-plugin/LICENSE", archive.namelist())
                self.assertIn("qq-plugin/webui/index.html", archive.namelist())
                self.assertIn("xuhuohua-cloud/scripts/install-qq.sh", archive.namelist())
                self.assertEqual(archive.read("xuhuohua-cloud/VERSION").strip(), b"0.13.6")
                self.assertIn("xuhuohua-cloud/scripts/qq-login-page.py", archive.namelist())
                self.assertIn("douyin-auto-fire/scripts/login.py", archive.namelist())
                self.assertEqual(archive.read("xuhuohua-cloud/scripts/qq-qr.sh"), b"#!/bin/bash\necho ok\n")
                self.assertFalse(any("storage-state" in n or n.endswith("config.json")
                                     or n.endswith("notify-webhook")
                                     or "qq-data" in n
                                     for n in archive.namelist()))

    def test_cloud_prompt_downloads_latest_release_before_guided_setup(self):
        value = cloud.prompt()
        self.assertIn(cloud.LATEST_RELEASE_ASSET, value)
        self.assertIn("xuhuohua-cloud.zip.sha256", value)
        self.assertIn("是否开启 QQ", value)
        self.assertIn("是否开启抖音", value)
        self.assertIn("qq-login-page.sh", value)
        self.assertIn("noVNC", value)
        self.assertIn("stop-douyin-desktop.sh", value)
        self.assertIn("虚拟桌面", value)

    def test_copy_prompt_reads_latest_release_asset_and_rejects_old_asset(self):
        with patch.object(cloud.urllib.request, "urlopen",
                          return_value=io.BytesIO(cloud.prompt().encode("utf-8"))) as fetch:
            result = cloud.latest_prompt()
        self.assertTrue(result["ok"])
        self.assertIn("是否开启 QQ", result["prompt"])
        self.assertEqual(fetch.call_args.args[0].full_url, cloud.LATEST_PROMPT_ASSET)
        with patch.object(cloud.urllib.request, "urlopen",
                          return_value=io.BytesIO(b"old prompt")):
            self.assertFalse(cloud.latest_prompt()["ok"])

    def test_packaged_qq_plugin_passes_start_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundled = root / "backend" / "assets" / "auto-tasks"
            bundled.mkdir(parents=True)
            (bundled / "index.mjs").write_text("// test", encoding="utf-8")
            with patch.object(qq, "PLUGIN_DIST", root / "missing-dist"), \
                 patch.object(qq, "BUNDLE_DIR", root), \
                 patch.object(qq, "_qq_installed", return_value=False):
                self.assertEqual(qq.plugin_source_dir(), bundled)
                self.assertIn("没有安装 QQ", qq.start()["msg"])

    def test_repeated_start_does_not_kill_running_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            bundled = Path(directory)
            (bundled / "index.mjs").write_text("// test", encoding="utf-8")
            config = {"network": {"httpServers": [{"name": qq.ONEBOT_HTTP_NAME,
                                                      "enable": True, "port": 30001,
                                                      "token": "test"}]}}
            with patch.object(qq, "plugin_source_dir", return_value=bundled), \
                 patch.object(qq, "_qq_installed", return_value=True), \
                 patch.object(qq, "qq_running", return_value=True), \
                 patch.object(qq, "_read_onebot", return_value=config), \
                 patch.object(qq, "_onebot_call", return_value={"data": {"user_id": 123}}), \
                 patch.object(qq, "_kill_frontend_qq") as killed:
                self.assertFalse(qq.start()["started"])
                killed.assert_not_called()

    def test_watcher_waits_for_new_batch_completion(self):
        with patch.object(qq.time, "sleep"), \
             patch.object(qq, "qq_running", side_effect=[True, True]), \
             patch.object(qq, "_read_friend_spark_completed_at", side_effect=[10, 11]), \
             patch.object(qq, "stop", return_value={"stopped": True}) as stopped:
            qq._auto_stop_watcher(10)
            stopped.assert_called_once()

    def test_friend_batch_marker_is_read_from_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config.json"
            target.write_text(json.dumps({"stats": {"friendSparkCompletedAt": 123}}), encoding="utf-8")
            with patch.object(qq, "PLUGIN_CONFIG_PATH", target):
                self.assertEqual(qq._read_friend_spark_completed_at(), 123)

    def test_other_enabled_tasks_disable_auto_stop(self):
        self.assertFalse(qq._has_other_enabled_tasks({"tasks": [{"enable": False}]}))
        self.assertTrue(qq._has_other_enabled_tasks({"groupSpark_enable": True}))
        self.assertTrue(qq._has_other_enabled_tasks({"tasks": [{"enable": True}]}))

    def test_qq_schedule_starts_five_minutes_before_send(self):
        with patch.object(scheduler, "_app_command", return_value='"app.exe" --qq-scheduled-run'), \
             patch.object(scheduler, "_run_schtasks", return_value=CompletedProcess([], 0, "", "")) as run:
            result = scheduler.sync_qq_start({"friendSpark_enable": True,
                                              "friendSpark_targets": "123",
                                              "friendSpark_time": "10:00:00"})
            self.assertTrue(result["ok"])
            args = run.call_args.args
            self.assertEqual(args[args.index("/ST") + 1], "09:55")
            self.assertIn("--qq-scheduled-run", args[args.index("/TR") + 1])

    def test_portable_douyin_schedule_uses_bundled_script(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "daily_douyin.ps1"
            script.touch()
            with patch.object(scheduler, "BACKEND_SCRIPT_DIR", script.parent), \
                 patch.object(scheduler, "_run_schtasks", return_value=CompletedProcess([], 0, "", "")) as run:
                self.assertTrue(scheduler.register("08:30")["ok"])
                args = run.call_args.args
                self.assertIn(str(script), args[args.index("/TR") + 1])

    def test_english_schtasks_output_flags_old_install_path(self):
        output = "Next Run Time: 2026/9/29 8:30:00\nLast Result: 2\nTask To Run: old\\daily_douyin.ps1\n"
        with patch.object(scheduler, "_run_schtasks", return_value=CompletedProcess([], 0, output, "")):
            state = scheduler.status()
            self.assertEqual(state["last_result"], "2")
            self.assertTrue(state["needs_repair"])

    def test_scheduled_qq_waits_for_batch_marker(self):
        with patch.object(qq, "get_plugin_config", return_value={"friendSpark_enable": True,
                                                                   "friendSpark_targets": "123"}), \
             patch.object(qq, "qq_account", return_value="456"), \
             patch.object(qq, "_read_friend_spark_result", side_effect=[
                 {"completed_at": 10, "succeeded": 0, "failed": 0},
                 {"completed_at": 11, "succeeded": 1, "failed": 0}]), \
             patch.object(qq, "start", return_value={"started": True}), \
             patch.object(qq, "qq_running", return_value=False):
            self.assertEqual(qq.scheduled_run(wait_seconds=10), 0)

    def test_scheduled_qq_reports_batch_failure_and_preserves_other_tasks(self):
        config = {"friendSpark_enable": True, "friendSpark_targets": "123",
                  "groupSpark_enable": True}
        with patch.object(qq, "get_plugin_config", return_value=config), \
             patch.object(qq, "qq_account", return_value="456"), \
             patch.object(qq, "_read_friend_spark_result", side_effect=[
                 {"completed_at": 10, "succeeded": 0, "failed": 0},
                 {"completed_at": 11, "succeeded": 0, "failed": 1}]), \
             patch.object(qq, "start", return_value={"started": True}), \
             patch.object(qq, "stop") as stopped, \
             patch("backend.notify.notify_event"):
            self.assertEqual(qq.scheduled_run(wait_seconds=10), 1)
            stopped.assert_not_called()

    def test_embedded_python_dependency_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            python = runtime / "python.exe"
            python.touch()
            pth = runtime / "python312._pth"
            pth.write_text("python312.zip\nimport site\n", encoding="utf-8")
            deps = root / "douyin-auto-fire" / "deps"
            deps.mkdir(parents=True)
            with patch.object(douyin, "DOUYIN_RUNTIME_PY", python), \
                 patch.object(douyin, "DOUYIN_DEPS", deps), \
                 patch.object(douyin, "DOUYIN_DIR", deps.parent), \
                 patch.object(douyin, "DOUYIN_VENV_PY", root / "missing-venv"):
                self.assertEqual(douyin.engine_python(), str(python))
                self.assertIn(os.path.relpath(deps.parent, runtime).replace("/", "\\"), pth.read_text(encoding="utf-8"))
                self.assertIn(os.path.relpath(deps, runtime).replace("/", "\\"), pth.read_text(encoding="utf-8"))
                self.assertEqual(douyin._engine_env()["PYTHONPATH"], str(deps))

    def test_login_waits_for_complete_embedded_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime" / "python.exe"
            runtime.parent.mkdir()
            runtime.touch()
            deps = root / "douyin-auto-fire" / "deps"
            with patch.object(douyin, "DOUYIN_RUNTIME_PY", runtime), \
                 patch.object(douyin, "DOUYIN_DEPS", deps), \
                 patch.object(douyin, "DOUYIN_VENV_PY", root / "missing-venv"):
                self.assertFalse(douyin.env_ready())
                self.assertFalse(douyin.start_login()["started"])
                playwright = deps / "playwright" / "__init__.py"
                playwright.parent.mkdir(parents=True)
                playwright.touch()
                self.assertFalse(douyin.env_ready())
                (deps / ".chromium_done").touch()
                self.assertTrue(douyin.env_ready())


if __name__ == "__main__":
    unittest.main()
