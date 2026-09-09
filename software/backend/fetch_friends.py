# -*- coding: utf-8 -*-
"""抓取抖音聊天列表的最近会话名（供 UI 勾选好友，免手打）。

实测结论（probe3）：
- IM 会话列表在页面打开后 ~15-20 秒才异步挂载（等 IM 服务连接），抓太早 = 零结果
- 条目有稳定属性 [data-e2e="conversation-item"]，容器 conversationConversationListwrapper
- 列表是虚拟滚动（data-index），必须边滚动边增量收集
输出写到 artifacts/douyin_friends.json。
"""
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2] / "douyin-auto-fire"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.async_api import async_playwright  # noqa: E402

OUT_FILE = PROJECT_ROOT / "artifacts" / "douyin_friends.json"
CHAT_URL = "https://www.douyin.com/chat"
ITEM_SEL = '[data-e2e="conversation-item"]'
LIST_SEL = '[class*="conversationConversationListwrapper"], [class*="ConversationListwrapper"]'

# 每条 innerText 的首行是昵称；排除时间/系统字样
_JUNK = ("昨天", "星期", "刚刚", "分钟前", "小时前")


def _name_from_item(text: str) -> str:
    for ln in text.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if any(j in ln for j in _JUNK) and len(ln) <= 8:
            continue
        return ln[:25]
    return ""


async def main() -> int:
    state = PROJECT_ROOT / "storage-state.json"
    if not state.exists():
        print("FRIENDS_ERR 未登录抖音（没有 storage-state.json）", flush=True)
        return 3
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="zh-CN", storage_state=str(state),
            viewport={"width": 1440, "height": 1000})   # 与引擎一致
        page = await context.new_page()
        await page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=45000)

        # 1) 等会话列表挂载并稳定（渐进挂载：置顶条目先出，其余陆续补齐）
        stable_rounds = 0
        last_count = 0
        mounted = False
        for _ in range(40):          # 最多 ~80 秒
            cnt = await page.locator(ITEM_SEL).count()
            if cnt:
                mounted = True
                if cnt == last_count:
                    stable_rounds += 1
                    if cnt >= 3 and stable_rounds >= 2:
                        break
                else:
                    stable_rounds = 0
                last_count = cnt
            await page.wait_for_timeout(2000)
        if not mounted:
            print("FRIENDS_ERR 会话列表 80 秒内没有挂载（网络慢或抖音改版）", flush=True)
            await browser.close()
            return 2

        # 2) 边滚动边增量收集（虚拟列表：滚出视口的条目会被回收）
        names: list[str] = []
        seen: set[str] = set()
        stale_rounds = 0
        for round_no in range(25):
            items = page.locator(ITEM_SEL)
            cnt = await items.count()
            fresh = 0
            for i in range(min(cnt, 80)):
                try:
                    text = await items.nth(i).inner_text()
                except Exception:
                    continue
                name = _name_from_item(text)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
                    fresh += 1
            print("ROUND {0}: 条目 {1}，累计 {2}".format(round_no + 1, cnt, len(names)), flush=True)
            if fresh == 0:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
            # 鼠标移到列表上方用滚轮滚动（虚拟列表内部容器结构不稳，猜元素不可靠）
            try:
                box = await items.first.bounding_box()
                if box:
                    await page.mouse.move(box["x"] + box["width"] / 2,
                                          min(box["y"] + 250, 950))
                    await page.mouse.wheel(0, 500)
            except Exception:
                await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(1500)

        await browser.close()
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print("FRIENDS_OK {0}".format(len(names)), flush=True)
        for n in names[:80]:
            print("NAME " + n, flush=True)
        return 0 if names else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
