from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Message
from app.douyin import PageOperationError
from app.selectors import IMAGE_INPUTS
from app.sender import (
    LATEST_OUTGOING_MESSAGE,
    MESSAGE_CONFIRM_ANCHOR,
    SEND_BUTTONS,
    SEND_FAILURE_MARKERS,
    SEND_PENDING_MARKERS,
    _await_send_terminal_state,
    _click_and_confirm_sticker,
    _confirm_outgoing_message,
    _confirm_sticker_sent,
    _publish_ready,
    _restore_composer,
    _sticker_resource_key,
    _trigger_send,
    send_message,
    send_text,
)
import app.sender as sender_module


# ---------------------------------------------------------------------------
# Fake page harness
#
# The real Douyin DOM (Issue #11) renders an outgoing bubble *before* its send
# status is resolved: the bubble appears, a `.semi-spin` spinner may sit beside
# it, and only later does it either clear (success) or flip to a retry marker
# (`ContentSideSendStatusretry`). A single static mock cannot represent that
# transition, so the harness below scripts a per-iteration (failure, pending)
# visibility timeline advanced by `wait_for_timeout`.
#
# Only the small subset of the Playwright async API exercised by the sender is
# implemented; every marker of the same kind reads the same timeline frame so a
# test declares a *state transition*, not a single snapshot.
# ---------------------------------------------------------------------------


class _Timeline:
    """Per polling-iteration (failure_visible, pending_visible) visibility.

    ``clock`` is in *seconds* to match production ``_monotonic`` units, so the
    deadline math in ``_await_send_terminal_state`` (seconds) stays consistent.
    Each short poll/settle wait advances the timeline by that wait in seconds
    AND consumes one state frame; long pre-send waits (image upload
    stabilization) advance time but do not consume a state frame.
    """

    def __init__(self, frames, repeat_last=False):
        self.frames = list(frames)
        self.repeat_last = repeat_last
        self.round = 0
        self.clock = 0.0

    def _frame(self):
        if self.round < len(self.frames):
            return self.frames[self.round]
        if self.repeat_last and self.frames:
            return self.frames[-1]
        return (False, False)

    def failure(self):
        return self._frame()[0]

    def pending(self):
        return self._frame()[1]

    def advance(self, ms):
        self.clock += ms / 1000.0
        # Only the short poll/stable waits of the state loop advance the state
        # frame. Long pre-send waits (e.g. image upload stabilization) must not
        # consume a state frame.
        if ms <= 1000:
            self.round += 1


class _Marker:
    def __init__(self, timeline, kind):
        self._timeline = timeline
        self._kind = kind

    async def count(self):
        return 1 if self._visible() else 0

    async def is_visible(self):
        return self._visible()

    def _visible(self):
        return self._timeline.failure() if self._kind == "failure" else self._timeline.pending()


class _MarkerGroup:
    def __init__(self, marker):
        self._marker = marker

    @property
    def first(self):
        return self._marker


class _Message:
    def __init__(self, timeline):
        self._timeline = timeline

    def locator(self, selector):
        if selector in SEND_FAILURE_MARKERS:
            return _MarkerGroup(_Marker(self._timeline, "failure"))
        if selector in SEND_PENDING_MARKERS:
            return _MarkerGroup(_Marker(self._timeline, "pending"))
        return _MarkerGroup(_Marker(self._timeline, "failure"))


class _MessageGroup:
    def __init__(self, message):
        self._message = message

    @property
    def first(self):
        return self._message


class _Anchors:
    def __init__(self):
        self.evaluate_all = AsyncMock()


class _FileInput:
    def __init__(self):
        self.set_input_files = AsyncMock()

    async def count(self):
        return 1


class _FileInputGroup:
    def __init__(self, file_input):
        self._file_input = file_input

    @property
    def first(self):
        return self._file_input


class _ContentGroup:
    def __init__(self, count_value=1):
        self.count = AsyncMock(return_value=count_value)


class _GenericLocator:
    def __init__(self):
        self.first = self

    async def count(self):
        return 0


class _FakePage:
    def __init__(self, timeline, content_count=1):
        self._timeline = timeline
        self._message = _Message(timeline)
        self._anchors = _Anchors()
        self._file_group = _FileInputGroup(_FileInput())
        self._content = _ContentGroup(content_count)
        self.keyboard = MagicMock()
        self.keyboard.press = AsyncMock()
        self.wait_for_function = AsyncMock(return_value=True)
        self.timeout_calls = []

    def locator(self, selector):
        if selector == LATEST_OUTGOING_MESSAGE:
            return _MessageGroup(self._message)
        if "data-douyin-sender-anchor" in selector:
            return self._anchors
        if selector == '[data-e2e="msg-item-content"]':
            return self._content
        if selector in IMAGE_INPUTS:
            return self._file_group
        return _GenericLocator()

    async def wait_for_timeout(self, ms):
        self.timeout_calls.append(ms)
        self._timeline.advance(ms)


# ---------------------------------------------------------------------------
# Existing behaviour contracts (kept)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_random_message_delegates_to_selected_choice(monkeypatch) -> None:
    editor = AsyncMock()
    page = MagicMock()
    message_items = MagicMock()
    message_items.count = AsyncMock(return_value=0)
    missing_first = MagicMock()
    missing_first.count = AsyncMock(return_value=0)
    message_items.first = missing_first
    page.locator.return_value = message_items
    page.keyboard.insert_text = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    editor.page = page
    chat = AsyncMock()
    chat.message_input.return_value = editor
    text = Message(type="text", content="你好")
    message = Message(type="random", choices=(text,))
    monkeypatch.setattr("app.sender.random.choice", lambda choices: choices[0])
    monkeypatch.setattr("app.sender._mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "")))
    monkeypatch.setattr("app.sender._confirm_outgoing_message", AsyncMock())

    await send_message(page, chat, message, {})

    page.keyboard.insert_text.assert_awaited_once_with("你好")
    page.keyboard.press.assert_awaited_once_with("Enter")


@pytest.mark.asyncio
async def test_trigger_send_clicks_publish_button_when_visible() -> None:
    page = MagicMock()
    button = MagicMock()
    button.count = AsyncMock(return_value=1)
    button.is_visible = AsyncMock(return_value=True)
    button.click = AsyncMock()
    publish = MagicMock()
    publish.first = button
    missing_loc = MagicMock()
    missing_first = MagicMock()
    missing_first.count = AsyncMock(return_value=0)
    missing_loc.first = missing_first
    page.locator.side_effect = lambda selector: publish if selector == SEND_BUTTONS[0] else missing_loc

    await _trigger_send(page)

    button.click.assert_awaited_once_with()
    page.keyboard.press.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_send_falls_back_to_enter() -> None:
    page = MagicMock()
    missing = MagicMock()
    missing.first = MagicMock()
    missing.first.count = AsyncMock(return_value=0)
    page.locator.return_value = missing
    page.keyboard.press = AsyncMock()

    await _trigger_send(page)

    page.keyboard.press.assert_awaited_once_with("Enter")


@pytest.mark.asyncio
async def test_publish_ready_true_when_button_visible() -> None:
    page = MagicMock()
    button = MagicMock()
    button.count = AsyncMock(return_value=1)
    button.is_visible = AsyncMock(return_value=True)
    publish = MagicMock()
    publish.first = button
    missing = MagicMock()
    missing.first = MagicMock()
    missing.first.count = AsyncMock(return_value=0)
    page.locator.side_effect = lambda selector: publish if selector == SEND_BUTTONS[0] else missing

    assert await _publish_ready(page) is True


@pytest.mark.asyncio
async def test_sticker_click_retries_via_publish_when_staged(monkeypatch) -> None:
    item = MagicMock()
    item.get_attribute = AsyncMock(return_value=None)
    item.click = AsyncMock()
    img_first = MagicMock()
    img_first.count = AsyncMock(return_value=0)
    img_loc = MagicMock()
    img_loc.first = img_first
    item.locator.return_value = img_loc
    page = MagicMock()
    calls = {"confirm": 0, "publish": 0}

    async def fake_confirm(_page, _before, _name, _key=""):
        calls["confirm"] += 1
        if calls["confirm"] == 1:
            raise PageOperationError("未检测到新的已发送消息")
        return None

    async def fake_trigger(_page):
        calls["publish"] += 1

    async def fake_ready(_page):
        return True

    monkeypatch.setattr("app.sender._confirm_sticker_sent", fake_confirm)
    monkeypatch.setattr("app.sender._trigger_send", fake_trigger)
    monkeypatch.setattr("app.sender._publish_ready", fake_ready)

    await _click_and_confirm_sticker(page, item, ("anchor", "old"), "比心")

    assert calls["confirm"] == 2
    assert calls["publish"] == 1


@pytest.mark.asyncio
async def test_sticker_click_raises_when_not_staged(monkeypatch) -> None:
    item = MagicMock()
    item.get_attribute = AsyncMock(return_value=None)
    item.click = AsyncMock()
    img_first = MagicMock()
    img_first.count = AsyncMock(return_value=0)
    img_loc = MagicMock()
    img_loc.first = img_first
    item.locator.return_value = img_loc
    page = MagicMock()

    async def fake_confirm(_page, _before, _name, _key=""):
        raise PageOperationError("未检测到新的已发送消息")

    async def fake_trigger(_page):
        raise AssertionError("不应触发发送")

    async def fake_ready(_page):
        return False

    monkeypatch.setattr("app.sender._confirm_sticker_sent", fake_confirm)
    monkeypatch.setattr("app.sender._trigger_send", fake_trigger)
    monkeypatch.setattr("app.sender._publish_ready", fake_ready)

    with pytest.raises(PageOperationError):
        await _click_and_confirm_sticker(page, item, ("anchor", "old"), "比心")


@pytest.mark.asyncio
async def test_missing_sticker_mapping_fails() -> None:
    with pytest.raises(Exception, match="没有原生表情映射"):
        await send_message(AsyncMock(), AsyncMock(), Message(type="douyin_sticker", sticker="比心"), {})


@pytest.mark.asyncio
async def test_image_message_requires_path() -> None:
    with pytest.raises(Exception, match="缺少文件路径"):
        await send_message(AsyncMock(), AsyncMock(), Message(type="image", path=None), {})


@pytest.mark.asyncio
async def test_sticker_confirmation_reports_page_send_failure() -> None:
    page = MagicMock()
    page.wait_for_function = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    latest_group = MagicMock()
    latest = MagicMock()
    latest_group.first = latest
    marker_group = MagicMock()
    marker = MagicMock()
    marker_group.first = marker
    marker.count = AsyncMock(return_value=1)
    marker.is_visible = AsyncMock(return_value=True)
    latest.locator.return_value = marker_group
    anchors = MagicMock()
    anchors.evaluate_all = AsyncMock()
    page.locator.side_effect = lambda selector: latest_group if selector == LATEST_OUTGOING_MESSAGE else anchors

    with pytest.raises(PageOperationError, match="发送失败"):
        await _confirm_sticker_sent(page, ("anchor", "old-content"), "比心")


@pytest.mark.asyncio
async def test_sticker_confirmation_reports_missing_new_message() -> None:
    page = MagicMock()
    page.wait_for_function = AsyncMock(side_effect=TimeoutError)
    anchors = MagicMock()
    anchors.evaluate_all = AsyncMock()
    page.locator.return_value = anchors

    with pytest.raises(PageOperationError, match="没有检测到新的已发送消息"):
        await _confirm_sticker_sent(page, ("anchor", "old-content"), "比心")


@pytest.mark.asyncio
async def test_sticker_resource_key_ignores_signed_query_string() -> None:
    item = MagicMock()
    item.get_attribute = AsyncMock(
        return_value="https://p26-sign.douyinpic.com/obj/im-resource/sticker-key?x-signature=temporary"
    )

    assert await _sticker_resource_key(item) == "sticker-key"


@pytest.mark.asyncio
async def test_send_text_confirms_outgoing_message_without_retry(monkeypatch) -> None:
    page = MagicMock()
    page.keyboard.insert_text = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    editor = MagicMock()
    editor.click = AsyncMock()
    editor.page = page
    chat = MagicMock()
    chat.message_input = AsyncMock(return_value=editor)
    calls = {"trigger": 0, "confirm": 0}

    async def fake_mark(_page):
        return ("anchor", "old-content")

    async def fake_trigger(_page):
        calls["trigger"] += 1

    async def fake_confirm(_page, before, label, resource_key="", expected_text=""):
        calls["confirm"] += 1
        assert before == ("anchor", "old-content")
        assert label == "文字"
        assert expected_text == "你好"

    monkeypatch.setattr("app.sender._mark_latest_outgoing_message", fake_mark)
    monkeypatch.setattr("app.sender._trigger_send", fake_trigger)
    monkeypatch.setattr("app.sender._confirm_outgoing_message", fake_confirm)

    await send_text(chat, "你好")

    assert calls["trigger"] == 1
    assert calls["confirm"] == 1


@pytest.mark.asyncio
async def test_send_text_raises_when_confirmation_fails(monkeypatch) -> None:
    page = MagicMock()
    page.keyboard.insert_text = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    editor = MagicMock()
    editor.click = AsyncMock()
    editor.page = page
    chat = MagicMock()
    chat.message_input = AsyncMock(return_value=editor)

    monkeypatch.setattr("app.sender._mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "")))
    monkeypatch.setattr("app.sender._trigger_send", AsyncMock())

    async def fail(_page, *_args, **_kwargs):
        raise PageOperationError("文字已发送，但没有检测到新的已发送消息")

    monkeypatch.setattr("app.sender._confirm_outgoing_message", fail)

    with pytest.raises(PageOperationError, match="没有检测到新的已发送消息"):
        await send_text(chat, "你好")


@pytest.mark.asyncio
async def test_restore_composer_presses_escape_and_focuses(monkeypatch) -> None:
    page = MagicMock()
    page.keyboard.press = AsyncMock()
    editor = MagicMock()
    editor.click = AsyncMock()
    editor.focus = AsyncMock()
    monkeypatch.setattr("app.sender.first_visible", AsyncMock(return_value=editor))

    await _restore_composer(page)

    page.keyboard.press.assert_awaited_once_with("Escape")
    editor.click.assert_awaited_once()
    editor.focus.assert_awaited_once()


# ---------------------------------------------------------------------------
# Selector guards (Issue #11)
# ---------------------------------------------------------------------------


def test_failure_markers_include_issue_eleven_retry_selectors() -> None:
    joined = " ".join(SEND_FAILURE_MARKERS)
    assert '[class*="ContentSideSendStatusretry"]' in joined
    assert '[class*="SendStatusretry"]' in joined


def test_send_statusicon_is_not_a_failure_marker() -> None:
    # `[class*="SendStatusicon"]` is too broad: other send states reuse that
    # class and would produce false failures. It must not gate failure alone.
    assert not any("SendStatusicon" in marker for marker in SEND_FAILURE_MARKERS)


def test_pending_markers_include_spin_selectors() -> None:
    joined = " ".join(SEND_PENDING_MARKERS)
    assert ".semi-spin" in joined
    assert '[class*="im-saas-message-spin"]' in joined
    assert '[data-icon="spin"]' in joined


# ---------------------------------------------------------------------------
# Send terminal-state transitions (Issue #11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_pending_then_success() -> None:
    # bubble appears -> spinner present -> spinner present -> spinner gone -> gone
    timeline = _Timeline([(False, True), (False, True), (False, False), (False, False)])
    page = _FakePage(timeline)

    await _confirm_outgoing_message(page, ("anchor", "old"), "文字", expected_text="测试文字")

    # State was polled; no fixed 3s sleep is used to declare success.
    assert 3_000 not in page.timeout_calls
    assert page.timeout_calls  # polling actually happened


@pytest.mark.asyncio
async def test_confirm_pending_then_failure() -> None:
    # bubble -> spinner -> spinner gone -> retry marker appears
    timeline = _Timeline([(False, True), (False, False), (True, False)])
    page = _FakePage(timeline)

    with pytest.raises(PageOperationError, match="发送失败"):
        await _confirm_outgoing_message(page, ("anchor", "old"), "文字", expected_text="测试文字")


@pytest.mark.asyncio
async def test_confirm_failure_immediate() -> None:
    timeline = _Timeline([(True, False)])
    page = _FakePage(timeline)

    with pytest.raises(PageOperationError, match="发送失败"):
        await _confirm_outgoing_message(page, ("anchor", "old"), "文字", expected_text="测试文字")


@pytest.mark.asyncio
async def test_confirm_pending_timeout_never_succeeds(monkeypatch) -> None:
    # Spinner never resolves. The clock is faked so the deadline is reached
    # without real wall-clock time. Success must never be returned.
    timeline = _Timeline([(False, True)], repeat_last=True)
    monkeypatch.setattr(sender_module, "_monotonic", lambda: timeline.clock)
    page = _FakePage(timeline)
    scope = page.locator(LATEST_OUTGOING_MESSAGE).first

    with pytest.raises(PageOperationError, match="发送状态未能确认"):
        await _await_send_terminal_state(page, scope, "文字", timeout_ms=50)


@pytest.mark.asyncio
async def test_confirm_clean_then_late_failure_fails(monkeypatch) -> None:
    # The exact E2E regression (Run 32843213569): bubble is clean for several
    # polls (longer than the old single 500ms stable window), THEN a retry
    # mounts. Must FAIL -- the initial-clean grace window keeps observing past
    # the old stable cutoff and catches the late retry.
    # Frames: many clean, then failure.
    frames = [(False, False)] * 6 + [(True, False)]
    timeline = _Timeline(frames)
    monkeypatch.setattr(sender_module, "_monotonic", lambda: timeline.clock)
    page = _FakePage(timeline)

    with pytest.raises(PageOperationError, match="发送失败"):
        await _confirm_outgoing_message(page, ("anchor", "old"), "文字", expected_text="测试文字")


@pytest.mark.asyncio
async def test_confirm_sustained_clean_reaches_success_via_grace(monkeypatch) -> None:
    # Normal fast send: no spinner/retry ever appears. The bubble must reach
    # success once the initial-clean grace window elapses fully clean, WITHOUT
    # waiting the full total timeout (15s). Frames stay clean throughout.
    # Enough clean frames to outlast the 2s grace window at 300ms/500ms polls.
    frames = [(False, False)] * 20
    timeline = _Timeline(frames)
    monkeypatch.setattr(sender_module, "_monotonic", lambda: timeline.clock)
    page = _FakePage(timeline)

    await _confirm_outgoing_message(page, ("anchor", "old"), "文字", expected_text="测试文字")
    # Grace window (2s) is well below the total timeout (15s).
    assert timeline.clock < 15.0


@pytest.mark.asyncio
async def test_confirm_text_success_passes_expected_text() -> None:
    timeline = _Timeline([(False, False), (False, False)])
    page = _FakePage(timeline)

    await _confirm_outgoing_message(page, ("anchor", "old-content"), "文字", expected_text="测试文字")

    assert page.wait_for_function.await_args.kwargs["arg"] == [
        LATEST_OUTGOING_MESSAGE,
        "anchor",
        "old-content",
        "",
        "测试文字",
    ]


@pytest.mark.asyncio
async def test_confirm_sticker_success_passes_resource_key(monkeypatch) -> None:
    timeline = _Timeline([(False, False), (False, False)])
    page = _FakePage(timeline)

    await _confirm_sticker_sent(page, ("anchor", "old-content"), "比心", "resource-key")

    assert page.wait_for_function.await_args.kwargs["arg"] == [
        LATEST_OUTGOING_MESSAGE,
        "anchor",
        "old-content",
        "resource-key",
        "",
    ]


# ---------------------------------------------------------------------------
# Image confirmation now waits for a terminal state (Issue #11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_image_fails_when_retry_appears(monkeypatch) -> None:
    # The image bubble has already appeared (count increased), but a retry
    # marker shows up. This must fail, not be counted as success.
    timeline = _Timeline([(True, False)])
    page = _FakePage(timeline, content_count=1)
    monkeypatch.setattr(sender_module, "_mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "old")))
    monkeypatch.setattr(sender_module, "_trigger_send", AsyncMock())

    with pytest.raises(PageOperationError, match="发送失败"):
        await sender_module.send_image(page, "image.png")

    # The file was actually uploaded before confirmation.
    page._file_group.first.set_input_files.assert_awaited_once_with("image.png")


@pytest.mark.asyncio
async def test_send_image_waits_for_terminal_state(monkeypatch) -> None:
    # Image bubble appears with a spinner; only once the spinner clears and the
    # state stabilises is it accepted.
    timeline = _Timeline([(False, True), (False, True), (False, False), (False, False)])
    page = _FakePage(timeline, content_count=1)
    monkeypatch.setattr(sender_module, "_mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "old")))
    monkeypatch.setattr(sender_module, "_trigger_send", AsyncMock())

    await sender_module.send_image(page, "image.png")  # must not raise

    # State polling happened (not a single count check).
    assert page.wait_for_function.await_count >= 1
    assert 3_000 not in page.timeout_calls


# ===========================================================================
# Real Playwright DOM tests (Issue #11 real DOM)
#
# These load the actual Issue #11 sibling structure via page.set_content and
# mutate it with page.evaluate, so they prove the selectors hit the real DOM
# (not just the Fake harness). A virtual clock advances on each
# wait_for_timeout, so tests run in milliseconds while simulating multi-second
# initial-clean grace windows. The DOM mutation schedule is expressed in
# virtual ms to mirror real Douyin timing (bubble -> clean -> late spin/retry).
# ===========================================================================

pytestmark_real_dom = pytest.mark.asyncio

# Issue #11 real DOM: content + Sidewrapper are siblings inside rowBox.
_REAL_DOM_BASE = """
<div class="messageMessageListlist">
  <div data-index="0">
    <div class="messageMessageBoxmessageBox">
      <div class="messageMessageBoxcontentBox messageMessageBoxisFromMe">
        <div class="MessageBoxContentrowBox" data-douyin-sender-anchor="anchor">
          <div data-e2e="msg-item-content" class="MessageBoxContentactiveClickArea">
            <div class="MessageItemTextcontainer MessageItemTextisFromMe">
              <span>测试消息</span>
            </div>
          </div>
          <!-- Sidewrapper mounts here as a sibling when state resolves -->
        </div>
      </div>
    </div>
  </div>
</div>
<input type="file" accept="image/*" />
"""

_RETRY_INNER = '<svg class="ContentSideSendStatusicon" width="16" height="16"></svg>'
_SPIN_INNER = '<svg data-icon="spin" width="14" height="14"></svg>'


class _VirtualClock:
    """Advances virtual time (seconds) on each wait_for_timeout.

    Production ``_monotonic`` returns seconds and ``wait_for_timeout(ms)``
    sleeps ms milliseconds, so virtual time must advance in *seconds* to keep
    the units consistent with the deadline math in ``_await_send_terminal_state``.
    Schedules are therefore expressed in virtual milliseconds and converted.
    """

    def __init__(self, schedules=None):
        # schedules: list of (fire_at_virtual_ms, async_callable)
        self.now = 0.0
        self.schedules = sorted(schedules or [], key=lambda s: s[0])

    async def wait_for_timeout(self, ms, page=None):
        self.now += ms / 1000.0
        remaining = []
        for deadline_ms, fn in self.schedules:
            if deadline_ms / 1000.0 <= self.now:
                if page is not None:
                    await fn(page)
            else:
                remaining.append((deadline_ms, fn))
        self.schedules = remaining


async def _make_real_page():
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch()
    page = await browser.new_page()
    await page.set_content(_REAL_DOM_BASE)
    # Keep handles for teardown.
    page._pw = pw
    page._browser = browser
    return page


async def _teardown_real_page(page):
    try:
        await page._browser.close()
    finally:
        await page._pw.stop()


def _patch_clock(monkeypatch, clock):
    monkeypatch.setattr(sender_module, "_monotonic", lambda: clock.now)


async def _set_side_inner(page, kind):
    inner = _RETRY_INNER if kind == "retry" else _SPIN_INNER
    await page.evaluate(
        """([kind, inner]) => {
            const row = document.querySelector('.MessageBoxContentrowBox');
            let wrap = row.querySelector('.MessageBoxContentSidewrapper');
            if (!wrap) {
                wrap = document.createElement('div');
                wrap.className = 'MessageBoxContentSidewrapper';
                row.appendChild(wrap);
            }
            if (kind === 'retry') {
                wrap.innerHTML = '<div class="ContentSideSendStatusretry">' + inner + '</div>';
            } else {
                wrap.innerHTML = '<div class="semi-spin im-saas-message-spin semi-spin-small">' + inner + '</div>';
            }
        }""",
        [kind, inner],
    )


async def _clear_side(page):
    await page.evaluate(
        """() => {
            const wrap = document.querySelector('.MessageBoxContentSidewrapper');
            if (wrap) wrap.innerHTML = '';
        }"""
    )


async def _scope(page):
    return page.locator(LATEST_OUTGOING_MESSAGE).first


@pytest.mark.asyncio
async def test_real_retry_dom_is_scoped_and_fails(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        await _set_side_inner(page, "retry")
        clock = _VirtualClock()
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送失败"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=50)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_spinner_dom_is_pending_not_success(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        await _set_side_inner(page, "spin")
        clock = _VirtualClock()
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送状态未能确认"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=5)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_clean_then_delayed_pending_then_failure(monkeypatch) -> None:
    # Bubble appears clean. The spinner mounts *after* the old single stable
    # window would have ended, then flips to retry. Must NOT return success
    # during the clean phase -- the initial-clean grace window must keep
    # observing and catch the late spinner.
    page = await _make_real_page()
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        async def to_retry(pg):
            await _set_side_inner(pg, "retry")

        clock = _VirtualClock(
            schedules=[
                (600, mount_spin),
                (700, to_retry),
            ]
        )
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送失败"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=5000)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_clean_then_delayed_retry_fails(monkeypatch) -> None:
    # THE critical E2E regression (Run 32843213569): bubble clean, then a retry
    # mounts *after* the old 500ms stable window ended -> old code returned
    # SUCCESS before the real failure marker appeared. Must now FAIL.
    page = await _make_real_page()
    try:
        async def mount_retry(pg):
            await _set_side_inner(pg, "retry")

        # Retry fires at virtual 600ms, past the old 500ms stable window, so the
        # old logic declared success at ~500ms. The new initial-clean grace must
        # still be observing at 600ms and catch it.
        clock = _VirtualClock(schedules=[(600, mount_retry)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送失败"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=5000)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_clean_then_delayed_pending_then_success(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        async def clear_spin(pg):
            await _clear_side(pg)

        clock = _VirtualClock(
            schedules=[
                (40, mount_spin),
                (120, clear_spin),
            ]
        )
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        # Should succeed: clean grace + pending appeared then cleared + stable.
        await _await_send_terminal_state(page, scope, "文字", timeout_ms=2000)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_sustained_clean_fast_success(monkeypatch) -> None:
    # Normal fast send: no spinner ever appears. Must succeed once the
    # initial-clean grace elapses, WITHOUT waiting the full total timeout.
    page = await _make_real_page()
    try:
        clock = _VirtualClock()
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        await _await_send_terminal_state(page, scope, "文字", timeout_ms=10_000)
        # Grace is bounded; virtual time should be far below the 10s total.
        assert clock.now < 5_000
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_pending_then_failure(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        async def to_retry(pg):
            await _set_side_inner(pg, "retry")

        clock = _VirtualClock(schedules=[(10, mount_spin), (60, to_retry)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送失败"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=2000)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_pending_then_success(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        async def clear_spin(pg):
            await _clear_side(pg)

        clock = _VirtualClock(schedules=[(10, mount_spin), (80, clear_spin)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        await _await_send_terminal_state(page, scope, "文字", timeout_ms=2000)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_pending_timeout_never_success(monkeypatch) -> None:
    page = await _make_real_page()
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        clock = _VirtualClock(schedules=[(10, mount_spin)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        scope = await _scope(page)
        with pytest.raises(PageOperationError, match="发送状态未能确认"):
            await _await_send_terminal_state(page, scope, "文字", timeout_ms=500)
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_image_delayed_failure(monkeypatch, tmp_path) -> None:
    # Image bubble present. The retry mounts *after* send_image's own upload
    # stabilization wait AND after the old stable window would have ended, i.e.
    # during _await_send_terminal_state. Must FAIL, never success.
    page = await _make_real_page()
    img = tmp_path / "image.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        async def mount_retry(pg):
            await _set_side_inner(pg, "retry")

        # send_image waits 1500ms to stabilize the upload before confirming.
        # Schedule the retry at virtual 2200ms so it mounts after that pre-wait,
        # during the terminal-state observation (past the old 500ms window).
        clock = _VirtualClock(schedules=[(2200, mount_retry)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        monkeypatch.setattr(sender_module, "_mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "old")))
        monkeypatch.setattr(sender_module, "_trigger_send", AsyncMock())

        async def wf_fn(*a, **k):
            return True

        page.wait_for_function = AsyncMock(side_effect=wf_fn)

        with pytest.raises(PageOperationError, match="发送失败"):
            await sender_module.send_image(page, img.as_posix())
    finally:
        await _teardown_real_page(page)


@pytest.mark.asyncio
async def test_real_image_pending_then_success(monkeypatch, tmp_path) -> None:
    page = await _make_real_page()
    img = tmp_path / "image.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        async def mount_spin(pg):
            await _set_side_inner(pg, "spin")

        async def clear_spin(pg):
            await _clear_side(pg)

        clock = _VirtualClock(schedules=[(40, mount_spin), (120, clear_spin)])
        _patch_clock(monkeypatch, clock)
        page.wait_for_timeout = lambda ms: clock.wait_for_timeout(ms, page)
        monkeypatch.setattr(sender_module, "_mark_latest_outgoing_message", AsyncMock(return_value=("anchor", "old")))
        monkeypatch.setattr(sender_module, "_trigger_send", AsyncMock())
        page.wait_for_function = AsyncMock(side_effect=lambda *a, **k: True)

        await sender_module.send_image(page, img.as_posix())
    finally:
        await _teardown_real_page(page)
