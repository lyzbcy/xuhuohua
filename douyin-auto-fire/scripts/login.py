from __future__ import annotations

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright


DOUYIN_URL = "https://www.douyin.com/"

async def login() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()
        await page.goto(DOUYIN_URL, wait_until="domcontentloaded")
        await _open_login(page)
        print("请在浏览器中扫码登录。登录完成并看到抖音首页后，回到终端按 Enter。")
        await asyncio.to_thread(input)
        await page.goto(DOUYIN_URL, wait_until="domcontentloaded")
        await _verify_home_login(page)
        await context.storage_state(path="storage-state.json.tmp")
        await browser.close()
        Path("storage-state.json.tmp").replace("storage-state.json")
        print("登录状态已保存到 storage-state.json")


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
    asyncio.run(login())
