from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from playwright.async_api import Error
from app.browser import open_private_messages
from app.history import run_lock, AlreadyRunningError


@pytest.mark.asyncio
async def test_navigation_network_changed_retries():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=[Error('net::ERR_NETWORK_CHANGED'), None])
    page.wait_for_timeout = AsyncMock()
    with patch('app.browser._any_visible', new=AsyncMock(return_value=False)), patch('app.browser._first_visible_selector', new=AsyncMock(return_value='input')):
        await open_private_messages(page)
    assert page.goto.await_count == 2


@pytest.mark.asyncio
async def test_non_network_error_never_retries():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=Error('Invalid URL'))
    with pytest.raises(Error, match='Invalid URL'):
        await open_private_messages(page)
    assert page.goto.await_count == 1


@pytest.mark.asyncio
async def test_navigation_retry_is_bounded():
    page = MagicMock()
    page.goto = AsyncMock(side_effect=Error('net::ERR_NETWORK_CHANGED'))
    page.wait_for_timeout = AsyncMock()
    with pytest.raises(Error, match='ERR_NETWORK_CHANGED'):
        await open_private_messages(page)
    assert page.goto.await_count == 3


@pytest.mark.skipif(__import__('sys').platform == 'win32', reason='Linux flock runtime')
def test_stale_lock_is_not_a_running_task(tmp_path):
    path = tmp_path / 'run.lock'
    path.write_text('99999999')
    with run_lock(path):
        with pytest.raises(AlreadyRunningError):
            with run_lock(path):
                pass
    with run_lock(path):
        pass
