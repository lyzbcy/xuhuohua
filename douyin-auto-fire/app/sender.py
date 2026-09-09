from __future__ import annotations

import asyncio
import random
import secrets
from urllib.parse import urlsplit

from playwright.async_api import Locator, Page

from app.douyin import DouyinChat, PageOperationError, first_visible
from app.models import Message, Sticker
from app.selectors import IMAGE_INPUTS, MESSAGE_INPUTS, STICKER_BUTTONS, STICKER_PANELS


def _monotonic() -> float:
    """Monotonic clock for the send-state deadline.

    Indirected (rather than calling ``asyncio.get_running_loop().time()``
    inline) so tests can fast-forward the clock without real wall-clock waits.
    """
    return asyncio.get_running_loop().time()


SEND_BUTTONS = (
    '[class*="messageMsgInputpublishBtn"]',
    '.e2e-send-msg-bt',
    'button[aria-label*="发送"]',
    '[role="button"][aria-label*="发送"]',
)


async def _trigger_send(page: Page) -> None:
    button = None
    for selector in SEND_BUTTONS:
        candidate = page.locator(selector).first
        try:
            if await candidate.count() and await candidate.is_visible():
                button = candidate
                break
        except Exception:
            continue
    if button is not None:
        await button.click()
    else:
        await page.keyboard.press("Enter")


async def _publish_ready(page: Page) -> bool:
    for selector in SEND_BUTTONS:
        candidate = page.locator(selector).first
        try:
            if await candidate.count() and await candidate.is_visible():
                return True
        except Exception:
            continue
    return False


LATEST_OUTGOING_MESSAGE = (
    '.messageMessageListlist [data-index="0"] '
    '.messageMessageBoxmessageBox:has(.messageMessageBoxcontentBox.messageMessageBoxisFromMe)'
)
MESSAGE_CONFIRM_ANCHOR = "data-douyin-sender-anchor"

# Send-status markers, scoped to the single outgoing message being confirmed.
#
# Douyin renders an outgoing bubble *before* its send status is resolved: the
# bubble appears, a spinner sits beside it, and only later does it clear
# (success) or flip to a retry marker. We must wait for a terminal state
# rather than assume a visible bubble means success (Issue #11).
#
# Failure: the red `!` retry control. `ContentSideSendStatusretry` is the real
# Douyin class from Issue #11; `SendStatusretry` is a stable fallback. The bare
# `SendStatusicon` class is intentionally excluded -- it is shared by other
# send states and would cause false failures.
SEND_FAILURE_MARKERS = (
    "text=发送失败",
    '[aria-label*="重试"]',
    '[title*="重试"]',
    '[class*="sendFailed"]',
    '[class*="SendFailed"]',
    '[class*="ContentSideSendStatusretry"]',
    '[class*="SendStatusretry"]',
)
# Pending: the in-flight spinner beside the bubble. These are checked only on
# the scoped outgoing message, never page-wide, so unrelated loading spinners
# cannot produce a false pending state.
SEND_PENDING_MARKERS = (
    ".semi-spin",
    '[class*="im-saas-message-spin"]',
    '[data-icon="spin"]',
)

# Overall budget for confirming a single message reaches a terminal state. A
# stuck spinner past this is treated as failure/uncertain, never success.
SEND_CONFIRM_TIMEOUT_MS = 15_000
# Poll interval for re-checking pending/failure state.
SEND_POLL_INTERVAL_MS = 300
# Short grace after pending clears: the retry marker can mount a tick after the
# spinner disappears, so require a stable non-pending frame before success.
SEND_STABLE_INTERVAL_MS = 500
# Initial-clean grace window. A freshly matched bubble with no spinner and no
# failure marker is NOT yet success -- Douyin mounts the spinner/retry *after*
# the bubble. We must keep observing until either a state appears or the whole
# grace window stays clean (Issue #11 E2E regression: late-mounting retry was
# missed because the old single 500ms check ended before the retry mounted).
# This is a continuous observation window, NOT a single sleep: the loop polls
# every SEND_POLL_INTERVAL_MS throughout it.
SEND_INITIAL_CLEAN_GRACE_MS = 2_000


async def send_message(page: Page, chat: DouyinChat, message: Message, stickers: dict[str, Sticker]) -> None:
    if message.type == "random":
        await send_message(page, chat, random.choice(message.choices), stickers)
        return
    if message.type == "text":
        await send_text(chat, message.content or "")
        return
    if message.type == "image":
        if message.path is None:
            raise PageOperationError("图片消息缺少文件路径")
        await send_image(page, message.path.as_posix())
        return
    if message.type == "douyin_sticker":
        sticker = stickers.get(message.sticker or "")
        if sticker is None:
            raise PageOperationError(f"没有原生表情映射: {message.sticker}")
        await send_douyin_sticker(page, sticker)
        return
    raise PageOperationError(f"不支持的消息类型: {message.type}")


async def send_text(chat: DouyinChat, content: str) -> None:
    editor = await chat.message_input()
    page = editor.page
    await editor.click()
    await page.keyboard.insert_text(content)
    try:
        await page.wait_for_function(
            """([txt]) => {
                const es = [...document.querySelectorAll('[class*=messageEditor] [contenteditable=true], .messageEditorinputArea')];
                return es.some(e => (e.innerText || '').includes(txt));
            }""",
            arg=[content],
            timeout=5_000,
        )
    except Exception as exc:
        raise PageOperationError("文字未能写入聊天输入框") from exc

    before = await _mark_latest_outgoing_message(page)
    await page.wait_for_timeout(300)
    await _trigger_send(page)
    await _confirm_outgoing_message(page, before, label="文字", expected_text=content)


async def send_image(page: Page, image_path: str) -> None:
    before = await _mark_latest_outgoing_message(page)
    file_input = None
    for selector in IMAGE_INPUTS:
        candidate = page.locator(selector).first
        if await candidate.count():
            file_input = candidate
            break
    if file_input is None:
        raise PageOperationError("找不到图片上传控件")
    await file_input.set_input_files(image_path)
    await page.wait_for_timeout(1_500)

    await _trigger_send(page)
    try:
        # The image bubble appearing is only the *start* of confirmation: the
        # send may still be in flight or already failed. Anchor on the latest
        # outgoing message (the freshly inserted image bubble) and wait for it
        # to reach a real terminal state, exactly as text/sticker does. A mere
        # bubble count increase is not success (Issue #11).
        await page.wait_for_function(
            """([selector, anchor]) => {
                const message = document.querySelector(selector);
                if (!message) return false;
                return message.getAttribute('data-douyin-sender-anchor') !== anchor;
            }""",
            arg=[LATEST_OUTGOING_MESSAGE, before[0]],
            timeout=15_000,
        )
        latest = page.locator(LATEST_OUTGOING_MESSAGE).first
        await _await_send_terminal_state(page, latest, "图片")
    except PageOperationError:
        raise
    except Exception as exc:
        raise PageOperationError("图片消息已触发发送，但无法确认是否发送成功；为避免重复不会自动重试") from exc

async def _restore_composer(page: Page, timeout_ms: int = 10_000) -> None:
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        editor = await first_visible(page, MESSAGE_INPUTS, timeout_ms)
    except Exception:
        return
    try:
        await editor.click(timeout=timeout_ms)
        await editor.focus()
    except Exception:
        pass


async def send_douyin_sticker(page: Page, sticker: Sticker) -> None:
    before = await _mark_latest_outgoing_message(page)
    try:
        button = await first_visible(page, STICKER_BUTTONS)
        await button.click(force=True)
        panel = await first_visible(page, STICKER_PANELS)

        if sticker.category:
            category = panel.get_by_text(sticker.category, exact=True)
            if await category.count() and await category.first.is_visible():
                await category.first.click()

        name = sticker.accessible_name or sticker.name
        item = panel.locator('.emojiEmojiItememojiItem').filter(has_text=name)
        for index in range(await item.count()):
            candidate = item.nth(index)
            description = candidate.locator('.emojiEmojiItememojiItemDesc')
            if await description.count() and (await description.first.inner_text()).strip() == name:
                await _click_and_confirm_sticker(page, candidate, before, name)
                return

        candidates = (
            panel.get_by_role("img", name=name, exact=True),
            panel.get_by_role("button", name=name, exact=True),
            panel.locator(f'[aria-label="{_css_escape(name)}"]'),
            panel.locator(f'[title="{_css_escape(name)}"]'),
            panel.locator(f'[alt="{_css_escape(name)}"]'),
        )
        for candidate in candidates:
            if await candidate.count() and await candidate.first.is_visible():
                await _click_and_confirm_sticker(page, candidate.first, before, name)
                return

        if sticker.fallback_index is not None:
            items = panel.locator('[role="button"], img, [aria-label], [title]')
            if await items.count() > sticker.fallback_index:
                await _click_and_confirm_sticker(page, items.nth(sticker.fallback_index), before, name)
                return
        raise PageOperationError(f"在抖音表情面板中找不到原生表情: {sticker.name}")
    finally:
        await _restore_composer(page)


def _css_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _mark_latest_outgoing_message(page: Page) -> tuple[str, str]:
    anchor = secrets.token_hex(8)
    latest = page.locator(LATEST_OUTGOING_MESSAGE).first
    if not await latest.count():
        return anchor, ""

    content = latest.locator('[data-e2e="msg-item-content"]').first
    before_content = await content.inner_html() if await content.count() else await latest.inner_html()
    await latest.evaluate(
        "(element, value) => element.setAttribute('data-douyin-sender-anchor', value)",
        anchor,
    )
    return anchor, before_content


async def _click_and_confirm_sticker(page: Page, item, before: tuple[str, str], name: str) -> None:
    resource_key = await _sticker_resource_key(item)
    await item.click(force=True)
    try:
        await _confirm_sticker_sent(page, before, name, resource_key)
    except PageOperationError:
        if await _publish_ready(page):
            await _trigger_send(page)
            await _confirm_sticker_sent(page, before, name, resource_key)
        else:
            raise


async def _sticker_resource_key(item) -> str:
    src = await item.get_attribute("src")
    if not src:
        image = item.locator("img").first
        if await image.count():
            src = await image.get_attribute("src")
    if not src:
        return ""
    return urlsplit(src).path.rsplit("/", 1)[-1]


async def _confirm_sticker_sent(
    page: Page,
    before: tuple[str, str],
    name: str,
    resource_key: str = "",
) -> None:
    await _confirm_outgoing_message(page, before, f"原生表情“{name}”", resource_key=resource_key)


async def _marker_visible(scope: Locator, selectors: tuple[str, ...]) -> bool:
    """True if any selector in ``selectors`` resolves to a visible element.

    Scoped to ``scope`` (the single outgoing message) so unrelated page-wide
    spinners cannot influence the verdict.
    """
    for selector in selectors:
        marker = scope.locator(selector).first
        try:
            if await marker.count() and await marker.is_visible():
                return True
        except Exception:
            continue
    return False


async def _await_send_terminal_state(
    page: Page,
    scope: Locator,
    label: str,
    timeout_ms: int = SEND_CONFIRM_TIMEOUT_MS,
) -> None:
    """Wait for ``scope`` (one outgoing message) to reach a terminal state.

    State machine (Issue #11):

        MATCHED
           |
           v
        OBSERVING_INITIAL  (bubble matched, status not yet resolved)
           |  failure visible            -> FAILED
           |  pending visible            -> WAITING_PENDING
           |  clean for the whole grace  -> SUCCESS
           v
        WAITING_PENDING  (spinner visible)
           |  failure visible            -> FAILED
           |  pending gone              -> STABILIZING
           v
        STABILIZING  (spinner just cleared)
           |  failure visible            -> FAILED
           |  pending reappeared         -> WAITING_PENDING
           |  stable clean window held   -> SUCCESS

    Critical correctness rule: a *newly* matched bubble that is clean is treated
    as UNKNOWN/OBSERVING, never as success, because Douyin mounts the spinner or
    retry marker *after* the bubble (Issue #11 E2E regression: the old code
    declared success after a single 500ms check, before a late retry mounted).
    The initial-clean grace window therefore polls continuously; success only
    after the bubble stays clean for the full window (or pending clears + holds).

    ``timeout_ms`` is the overall budget; a stuck spinner past it raises, never
    success. ``page.wait_for_timeout`` advances the injectable monotonic clock,
    so tests run in milliseconds while simulating multi-second windows.
    """
    deadline = _monotonic() + timeout_ms / 1000

    # Phase 1: observe the freshly matched bubble. It is UNKNOWN until either a
    # state marker appears or the initial-clean grace window elapses clean.
    grace_deadline = _monotonic() + SEND_INITIAL_CLEAN_GRACE_MS / 1000
    while _monotonic() < grace_deadline:
        if _monotonic() >= deadline:
            raise PageOperationError(
                f"{label}发送状态未能确认（发送超时或状态不确定），为避免重复不会自动重试"
            )
        if await _marker_visible(scope, SEND_FAILURE_MARKERS):
            raise PageOperationError(f"{label}发送失败，页面提示可以重试")
        if await _marker_visible(scope, SEND_PENDING_MARKERS):
            break  # -> resolve pending in Phase 2
        await page.wait_for_timeout(SEND_POLL_INTERVAL_MS)
    else:
        # Grace window elapsed fully clean -> fast success (normal fast send).
        return

    # Phase 2: a spinner appeared. Wait for it to clear (or flip to failure),
    # then require a stable clean window before success.
    while True:
        if _monotonic() >= deadline:
            raise PageOperationError(
                f"{label}发送状态未能确认（发送超时或状态不确定），为避免重复不会自动重试"
            )
        if await _marker_visible(scope, SEND_FAILURE_MARKERS):
            raise PageOperationError(f"{label}发送失败，页面提示可以重试")
        if not await _marker_visible(scope, SEND_PENDING_MARKERS):
            # Spinner gone. Require it to STAY clear across the stable window --
            # the retry marker can mount a tick after the spinner disappears.
            await page.wait_for_timeout(SEND_STABLE_INTERVAL_MS)
            if await _marker_visible(scope, SEND_FAILURE_MARKERS):
                raise PageOperationError(f"{label}发送失败，页面提示可以重试")
            if not await _marker_visible(scope, SEND_PENDING_MARKERS):
                return  # terminal: success
            # spinner reappeared -> keep waiting
        await page.wait_for_timeout(SEND_POLL_INTERVAL_MS)


async def _confirm_outgoing_message(
    page: Page,
    before: tuple[str, str],
    label: str,
    resource_key: str = "",
    expected_text: str = "",
) -> None:
    anchor, before_content = before
    try:
        await page.wait_for_function(
            """([selector, anchor, previousContent, expectedResource, expectedText]) => {
                const message = document.querySelector(selector);
                if (!message) return false;
                const content = message.querySelector('[data-e2e="msg-item-content"]') || message;
                const isNewMessage =
                    message.getAttribute('data-douyin-sender-anchor') !== anchor ||
                    content.innerHTML !== previousContent;
                if (!isNewMessage) return false;
                if (expectedText) {
                    const normalize = value => (value || '').replace(/[\\s\\u200B\\u200C\\u200D\\uFEFF]+/g, ' ').trim();
                    return normalize(content.innerText).includes(normalize(expectedText));
                }
                if (!expectedResource) return true;
                const images = [...content.querySelectorAll('img')];
                return images.some(image => (image.src || '').includes(expectedResource)) || images.length > 0;
            }""",
            arg=[LATEST_OUTGOING_MESSAGE, anchor, before_content, resource_key, expected_text],
            timeout=15_000,
        )
        # The bubble now matches our payload, but the send may still be in
        # flight or have already failed. Wait for a real terminal state rather
        # than treating a visible bubble as success (Issue #11).
        latest = page.locator(LATEST_OUTGOING_MESSAGE).first
        await _await_send_terminal_state(page, latest, label)
    except PageOperationError:
        raise
    except Exception as exc:
        raise PageOperationError(f"{label}已发送，但没有检测到新的已发送消息") from exc
    finally:
        anchors = page.locator(f"[{MESSAGE_CONFIRM_ANCHOR}]")
        try:
            await anchors.evaluate_all(
                "elements => elements.forEach(element => element.removeAttribute('data-douyin-sender-anchor'))"
            )
        except Exception:
            pass
