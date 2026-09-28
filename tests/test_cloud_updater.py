"""Offline checks for the optional daily Skill updater."""

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "cloud-skill/xuhuohua-cloud/scripts/update-skill.py"
spec = importlib.util.spec_from_file_location("cloud_update_skill", SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def release_zip(version="0.13.5"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        files = {
            "VERSION": version + "\n",
            "SKILL.md": "new skill",
            "scripts/check-update.sh": "#!/bin/bash\nexit 0\n",
            "scripts/update-skill.py": "# new updater\n",
            "scripts/notify-result.py": "# new notifier\n",
        }
        for name, value in files.items():
            archive.writestr("xuhuohua-cloud/" + name, value)
    return stream.getvalue()


class CloudUpdaterTests(unittest.TestCase):
    def make_install(self, directory):
        root = Path(directory) / "release"
        runtime = root / "xuhuohua-cloud"
        (runtime / "scripts").mkdir(parents=True)
        (runtime / "SKILL.md").write_text("old skill", encoding="utf-8")
        (runtime / "notify-webhook").write_text("private-key", encoding="utf-8")
        installed = Path(directory) / "agent-skills/xuhuohua-cloud"
        installed.mkdir(parents=True)
        (installed / "release-path.txt").write_text(str(root), encoding="utf-8")
        (installed / "VERSION").write_text("0.13.4\n", encoding="ascii")
        (installed / "SKILL.md").write_text("old skill", encoding="utf-8")
        return installed, runtime

    def test_verified_update_preserves_private_state(self):
        package = release_zip()
        release = {"tag_name": "v0.13.5", "assets": [
            {"name": "xuhuohua-cloud.zip", "browser_download_url": "https://example.invalid/cloud.zip"},
            {"name": "xuhuohua-cloud.zip.sha256", "browser_download_url": "https://example.invalid/cloud.sha256"},
        ]}
        responses = {updater.API: json.dumps(release).encode(),
                     "https://example.invalid/cloud.zip": package,
                     "https://example.invalid/cloud.sha256":
                         (hashlib.sha256(package).hexdigest() + "  xuhuohua-cloud.zip\n").encode()}
        with tempfile.TemporaryDirectory() as directory:
            installed, runtime = self.make_install(directory)
            with patch.object(updater, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=2, LOCK_NB=4)), \
                 patch.object(updater, "fetch", side_effect=lambda url, _: responses[url]):
                self.assertEqual(updater.update(installed), "updated")
                self.assertEqual(updater.update(installed), "already-checked")
            self.assertEqual((installed / "VERSION").read_text().strip(), "0.13.5")
            self.assertEqual((installed / "SKILL.md").read_text(), "new skill")
            self.assertEqual((runtime / "scripts/notify-result.py").read_text(), "# new notifier\n")
            self.assertEqual((runtime / "notify-webhook").read_text(), "private-key")

    def test_bad_checksum_keeps_current_skill(self):
        package = release_zip()
        release = {"tag_name": "v0.13.5", "assets": [
            {"name": "xuhuohua-cloud.zip", "browser_download_url": "https://example.invalid/cloud.zip"},
            {"name": "xuhuohua-cloud.zip.sha256", "browser_download_url": "https://example.invalid/cloud.sha256"},
        ]}
        responses = {updater.API: json.dumps(release).encode(),
                     "https://example.invalid/cloud.zip": package,
                     "https://example.invalid/cloud.sha256": ("0" * 64 + "  xuhuohua-cloud.zip\n").encode()}
        with tempfile.TemporaryDirectory() as directory:
            installed, runtime = self.make_install(directory)
            with patch.object(updater, "fcntl", SimpleNamespace(flock=lambda *_: None, LOCK_EX=2, LOCK_NB=4)), \
                 patch.object(updater, "fetch", side_effect=lambda url, _: responses[url]):
                with self.assertRaises(ValueError):
                    updater.update(installed)
            self.assertEqual((installed / "VERSION").read_text().strip(), "0.13.4")
            self.assertEqual((runtime / "SKILL.md").read_text(), "old skill")
            self.assertFalse((installed / ".last-update-check").exists())


if __name__ == "__main__":
    unittest.main()
