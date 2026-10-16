from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright
from app.auth_state import revision, save_verified_state
from app.browser import open_private_messages
from app.history import run_lock


DOUYIN_URL = "https://www.douyin.com/"

async def login() -> None:
    state_path = PROJECT_ROOT / "storage-state.json"
    expected = revision(state_path)
    async with async_playwright() as playwright:
        launch = {"headless": False}
        if os.environ.get("BROWSER_PATH"):
            launch["executable_path"] = os.environ["BROWSER_PATH"]
        browser = await playwright.chromium.launch(**launch)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()
        await page.goto(DOUYIN_URL, wait_until="domcontentloaded")
        await _open_login(page)
        print("请在浏览器中扫码登录。登录完成并看到抖音首页后，回到终端按 Enter。")
        await asyncio.to_thread(input)
        try:
            # Homepage login is insufficient: verify the actual private-message page.
            await open_private_messages(page)
            await save_verified_state(context, state_path, expected)
        finally:
            await browser.close()
        print("私信页验证通过，登录态已安全保存；仍需定时入口独立演练")


async def _open_login(page) -> None:
    login = page.get_by_text("登录", exact=True)
    if await login.count():
        try:
            await login.first.click(timeout=10_000)
        except Exception:
            pass

    qr_login = page.get_by_text("扫码登录", exact=True)
    if await qr_login.count():
        try:
            await qr_login.first.click(timeout=5_000)
        except Exception:
            pass


async def _verify_home_login(page) -> None:
    login = page.get_by_text("登录", exact=True)
    if await login.count() and await login.first.is_visible():
        raise RuntimeError("未检测到登录成功，请重新运行并完成扫码确认")


if __name__ == "__main__":
    with run_lock(PROJECT_ROOT / "artifacts" / "run.lock"):
        asyncio.run(login())
