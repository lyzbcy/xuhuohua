"""Local-only, auto-refreshing QQ login QR page. Never serves NapCat credentials."""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QR = ROOT / "qq-data/cache/qrcode.png"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_AGE = 180
PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>续火花 QQ 扫码登录</title>
<style>body{font:16px system-ui,sans-serif;max-width:460px;margin:8vh auto;padding:20px;text-align:center;color:#18222e}img{width:min(80vw,320px);height:min(80vw,320px);object-fit:contain}p{line-height:1.6}small{color:#617083}</style>
<h1>QQ 扫码登录</h1><p id="status">正在读取最新二维码…</p>
<img id="qr" alt="实时更新的 QQ 登录二维码" hidden>
<p><small>页面每 2 秒更新。扫码后请在手机上确认授权，再告知部署 Agent。</small></p>
<script>
async function update(){try{
  const r=await fetch('/status.json?time='+Date.now(),{cache:'no-store'});
  const s=await r.json();
  document.getElementById('status').textContent=s.message;
  const img=document.getElementById('qr');img.hidden=!s.ready;
  if(s.ready)img.src='/qr.png?time='+Date.now();
}catch(_){document.getElementById('status').textContent='连接中断，请检查 SSH 隧道';document.getElementById('qr').hidden=true}}
update();setInterval(update,2000);
</script></html>"""


def qr_status(now=None):
    now = time.time() if now is None else now
    try:
        stat = QR.stat()
        if not QR.is_file() or stat.st_size < 8 or stat.st_size > 1_000_000:
            raise OSError("invalid size")
        age = now - stat.st_mtime
        if age < -5 or age > MAX_AGE:
            return False, "二维码已过期，请在 NapCat WebUI 刷新登录码"
        with QR.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                raise OSError("invalid PNG")
        return True, "请用手机 QQ 扫码并确认授权（二维码自动更新）"
    except OSError:
        return False, "等待 NapCat 生成二维码；若已登录，请在 WebUI 确认账号状态"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_content(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/status.json":
            ready, message = qr_status()
            self.send_content(json.dumps({"ready": ready, "message": message}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif path == "/qr.png":
            ready, _ = qr_status()
            if not ready:
                self.send_error(404)
                return
            self.send_content(QR.read_bytes(), "image/png")
        else:
            self.send_error(404)

    def send_content(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    os.umask(0o077)
    ThreadingHTTPServer(("127.0.0.1", 6100), Handler).serve_forever()
