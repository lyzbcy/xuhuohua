# -*- coding: utf-8 -*-
"""界面内扫码登录器（改编自上游 scripts/login.py）：
- 打开可见浏览器到抖音首页
- 后台每 3 秒检查一次登录 Cookie（sessionid）
- 检测到登录成功 → 自动保存 storage-state.json，无需按回车
- 超时 5 分钟自动退出
在 douyin-auto-fire 目录下用其 venv 运行。
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2] / "douyin-auto-fire"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright  # noqa: E402

DOUYIN_URL = "https://www.douyin.com/"
TIMEOUT_SECONDS = 300


async def _open_login(page) -> None:
    for text in ("登录", "扫码登录"):
        try:
            el = page.get_by_text(text, exact=True)
            if await el.count():
                await el.first.click(timeout=3000)
        except Exception:
            pass


async def main() -> int:
    state_tmp = PROJECT_ROOT / "storage-state.json.tmp"
    state = PROJECT_ROOT / "storage-state.json"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()
        await page.goto(DOUYIN_URL, wait_until="domcontentloaded")
        await _open_login(page)
        print("等待扫码中……（检测到登录成功会自动保存并关闭浏览器）", flush=True)
        waited = 0
        while waited < TIMEOUT_SECONDS:
            await asyncio.sleep(3)
            waited += 3
            cookies = await context.cookies()
            if any(c["name"] in ("sessionid", "sessionid_ss") for c in cookies):
                await context.storage_state(path=str(state_tmp))
                await browser.close()
                state_tmp.replace(state)
                print("LOGIN_OK 登录成功，凭证已保存", flush=True)
                return 0
            if waited % 30 == 0:
                print("仍在等待扫码……（{0}/{1}秒）".format(waited, TIMEOUT_SECONDS), flush=True)
        print("LOGIN_TIMEOUT 超时未登录，请重试", flush=True)
        await browser.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
