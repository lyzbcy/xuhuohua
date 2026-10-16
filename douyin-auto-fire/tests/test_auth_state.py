import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.auth_state import SessionSaveError, revision, save_verified_state, state_file


def state(value='fresh'):
    return {'cookies': [{'name': 'sessionid', 'value': value, 'domain': '.douyin.com',
                         'expires': -1}], 'origins': []}


@pytest.mark.asyncio
async def test_rotation_is_restorable_and_keeps_private_backup(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps(state('old')))
    old = path.read_bytes()
    ctx = AsyncMock()
    ctx.storage_state.return_value = state()
    updated = await save_verified_state(ctx, path, revision(path))
    assert json.loads(path.read_text()) == state()
    assert path.with_name('state.json.last-good').read_bytes() == old
    assert updated == revision(path)
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.with_name('state.json.last-good').stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
@pytest.mark.parametrize('candidate', [{'cookies': [], 'origins': []},
    {'cookies': [{'name':'sessionid','value':'x','domain':'.douyin.com','expires':1}]},
    {'cookies': [{'name':'sessionid','value':'x','domain':'.other.com','expires':-1}]}])
async def test_empty_expired_or_wrong_domain_never_replaces_state(tmp_path, candidate):
    path = tmp_path/'state.json'
    path.write_text(json.dumps(state('old')))
    old = path.read_bytes()
    ctx = AsyncMock()
    ctx.storage_state.return_value = candidate
    with pytest.raises(SessionSaveError):
        await save_verified_state(ctx, path, revision(path))
    assert path.read_bytes() == old


@pytest.mark.asyncio
async def test_new_manual_login_is_not_overwritten(tmp_path):
    path = tmp_path/'state.json'
    path.write_text(json.dumps(state('old')))
    expected = revision(path)
    path.write_text(json.dumps(state('manual-login')))
    ctx = AsyncMock()
    ctx.storage_state.return_value = state('stale-run')
    with pytest.raises(SessionSaveError, match='其他进程'):
        await save_verified_state(ctx, path, expected)
    assert json.loads(path.read_text()) == state('manual-login')


@pytest.mark.asyncio
async def test_failed_atomic_replace_keeps_original_and_cleans_temp(tmp_path):
    path = tmp_path/'state.json'
    path.write_text(json.dumps(state('old')))
    old = path.read_bytes()
    ctx = AsyncMock()
    ctx.storage_state.return_value = state()
    with patch('app.auth_state.os.replace', side_effect=OSError('sensitive detail')):
        with pytest.raises(SessionSaveError) as error:
            await save_verified_state(ctx,path,revision(path))
    assert 'sensitive' not in str(error.value)
    assert path.read_bytes() == old
    assert list(tmp_path.glob('.state*')) == []


@pytest.mark.asyncio
async def test_inline_credentials_have_no_write_target():
    ctx = AsyncMock()
    assert state_file('{"cookies":[]}') is None
    assert await save_verified_state(ctx,None,None) is None
    ctx.storage_state.assert_not_called()
