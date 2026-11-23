import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))
from backend import cloud

spec = importlib.util.spec_from_file_location("shared_cloud_policy",
    ROOT / "cloud-skill/xuhuohua-cloud/scripts/message_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class CloudMessagePolicyTests(unittest.TestCase):
    def test_plain_text_import_includes_only_shareable_fields(self):
        valid = {"texts": ["早上好", "早上好"], "signature_enabled": True, "signature_text": "晚点聊"}
        self.assertEqual(policy.parse(json.dumps(valid).encode())["texts"], ["早上好"])
        with self.assertRaises(ValueError):
            policy.parse(json.dumps({**valid, "token": "fake"}).encode())
        with self.assertRaises(ValueError):
            policy.parse(json.dumps({**valid, "signature_text": "[CQ:bad]"}).encode())

    def test_qq_custom_or_disabled_signature_preserves_legacy_when_no_text_pool(self):
        old = "打卡\n" + policy.DEFAULT_SIGNATURE
        base = {"texts": [], "signature_enabled": False, "signature_text": ""}
        self.assertEqual(policy.qq_message(old, base), "打卡")
        custom = {**base, "signature_enabled": True, "signature_text": "自定义"}
        self.assertEqual(policy.qq_message(old, custom), "打卡\n自定义")
        self.assertEqual(policy.qq_message(old, {**custom, "texts": ["今天续一下"]}),
                         "今天续一下\n自定义")

    def test_douyin_overlay_keeps_targets_and_source(self):
        image = {"type": "image", "path": "sticker.png"}
        original = {"targets": [{"name": "fixture", "messages": [
            image, {"type": "text", "content": policy.DEFAULT_SIGNATURE}]}],
            "prevent_duplicates": True}
        draft = {"texts": [], "signature_enabled": False, "signature_text": ""}
        self.assertEqual(policy.douyin_config(original, draft)["targets"][0]["messages"], [image])
        output = policy.douyin_config(original, {**draft, "texts": ["打卡"], "signature_enabled": True})
        self.assertEqual(output["targets"][0]["name"], "fixture")
        self.assertTrue(output["prevent_duplicates"])
        self.assertEqual(output["targets"][0]["messages"][0]["choices"][0]["content"], "打卡")
        self.assertEqual(output["targets"][0]["messages"][-1]["content"], policy.DEFAULT_SIGNATURE)
        self.assertEqual(len(original["targets"][0]["messages"]), 2)

    def test_no_file_keeps_existing_platform_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(policy.load(Path(directory)))

    def test_desktop_export_round_trip_and_platform_payloads(self):
        guides = ROOT / "software/ui/assets/guide"
        settings = {"texts": ["打卡"], "signature_enabled": True, "signature_text": "晚点聊"}
        with tempfile.TemporaryDirectory() as directory:
            cloud_dir = Path(directory)
            bundle = cloud_dir / "library.zip"
            with patch.object(cloud, "DOUYIN_STICKERS", guides):
                cloud.export_library(settings, ["happy.png"], bundle)
            library = policy.import_library(bundle, cloud_dir)
            self.assertEqual(policy.load(cloud_dir), library)
            self.assertEqual(set(library["stickers"]), {p.name for p in guides.glob("*.png")})
            name, path = policy.selected_assets(library, cloud_dir)[0]
            self.assertEqual(name, "happy.png")
            self.assertEqual(path.read_bytes(), (guides / name).read_bytes())
            original = {"targets": [{"name": "fixture", "messages": [{"type": "text", "content": "旧"}]}]}
            items = policy.douyin_config(original, library, cloud_dir)["targets"][0]["messages"]
            self.assertEqual(items[0]["choices"], [
                {"type": "text", "content": "打卡"}, {"type": "image", "path": str(path)}])
            self.assertEqual(items[-1]["content"], "晚点聊")
            with patch.object(policy.random, "choice", side_effect=lambda choices: choices[-1]):
                wire, summary, tail = policy.qq_payload("旧", library, cloud_dir)
            self.assertEqual(tail, "晚点聊")
            self.assertIn("happy.png", summary)
            self.assertEqual(wire[1], {"type": "text", "data": {"text": tail}})
            encoded = wire[0]["data"]["file"].removeprefix("base64://")
            sent = policy.base64.b64decode(encoded)
            from app.sticker_transfer import compress_png
            self.assertEqual(sent, compress_png(path.read_bytes()))
            self.assertLess(len(sent), 30_000)

            with zipfile.ZipFile(bundle, "a") as archive:
                archive.writestr("stickers/../extra.png", b"bad")
            with self.assertRaises(ValueError):
                policy.import_library(bundle, cloud_dir)
            self.assertEqual(policy.load(cloud_dir), library)
