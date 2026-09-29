"""QR page serves only fresh local PNG data and never stale login screenshots."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "cloud-skill/xuhuohua-cloud/scripts/qq-login-page.py"
spec = importlib.util.spec_from_file_location("qq_login_page", SCRIPT)
page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(page)


class QQLoginPageTests(unittest.TestCase):
    def test_only_fresh_png_is_displayed(self):
        with tempfile.TemporaryDirectory() as directory:
            qr = Path(directory) / "qrcode.png"
            qr.write_bytes(page.PNG_SIGNATURE + b"picture")
            with patch.object(page, "QR", qr):
                mtime = qr.stat().st_mtime
                self.assertTrue(page.qr_status(mtime + 10)[0])
                self.assertFalse(page.qr_status(mtime + 181)[0])
                qr.write_bytes(b"not-a-png")
                self.assertFalse(page.qr_status(qr.stat().st_mtime + 1)[0])


if __name__ == "__main__":
    unittest.main()
