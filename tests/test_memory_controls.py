import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.personal_data import MemoryCreate, create_memory, get_memory_context
from jarvis.memory.controls import (
    purge_expired_memories,
    retention_status,
    search_memories,
    set_memory_expiry,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'memory.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'safety.db'))
    monkeypatch.setenv('JARVIS_API_TOKEN', 'test-token-that-is-at-least-32-characters')


def test_expired_context_exclusion_search_and_explicit_purge():
    past = datetime.now(UTC) - timedelta(hours=1)
    expired = create_memory(MemoryCreate(text='Temporary interview date', category='career', expires_at=past))
    active = create_memory(MemoryCreate(text='Prefers Telugu', category='language'))
    assert 'Temporary interview date' not in get_memory_context()
    assert 'Prefers Telugu' in get_memory_context()
    assert [row['id'] for row in search_memories()] == [active['id']]
    assert len(search_memories(include_expired=True)) == 2
    assert retention_status()['expired_ids'] == [expired['id']]
    assert purge_expired_memories()['deleted_rows'] == 1
    assert purge_expired_memories()['deleted_rows'] == 0
    assert len(search_memories()) == 1


def test_literal_search_and_category():
    create_memory(MemoryCreate(text='I use 100% of a _ wildcard literally', category='technical'))
    create_memory(MemoryCreate(text='another note', category='personal'))
    assert len(search_memories('100%', 'technical')) == 1
    assert search_memories("' OR 1=1 --") == []
    assert search_memories('another', 'technical') == []


def test_expiry_correction_and_removal():
    row = create_memory(MemoryCreate(text='Temporary preference'))
    set_memory_expiry(row['id'], '2026-01-01T09:00:00+05:30')
    assert not search_memories()
    set_memory_expiry(row['id'])
    assert len(search_memories()) == 1
    with pytest.raises(ValueError):
        set_memory_expiry(row['id'], '2026-12-01T09:00:00')
    with pytest.raises(ValueError):
        set_memory_expiry(9999)


def test_api_preserves_expiry_on_unrelated_edits_and_allows_explicit_clear():
    headers = {'Authorization': 'Bearer test-token-that-is-at-least-32-characters'}
    with TestClient(app) as client:
        row = client.post('/api/memories', headers=headers, json={'text': 'Old', 'expires_at': '2026-01-01T00:00:00Z'}).json()
        response = client.put(f"/api/memories/{row['id']}", headers=headers, json={'text': 'Corrected'})
        assert response.status_code == 200 and response.json()['expires_at']
        assert client.get('/api/memories?include_expired=false', headers=headers).json()['items'] == []
        response = client.put(f"/api/memories/{row['id']}", headers=headers, json={'text': 'Corrected', 'expires_at': None})
        assert response.json()['expires_at'] is None
        assert client.get('/api/memories?query=Correct&category=general', headers=headers).json()['items'][0]['text'] == 'Corrected'
        assert client.get('/api/memories?query=Correct').status_code == 401
        assert client.post('/api/memories', headers=headers, json={'text': ' ', 'expires_at': '2026-01-01T09:00:00'}).status_code == 422


def test_registry_purge_needs_real_confirmation():
    from jarvis.tools.builtin_tools import build_registry
    create_memory(MemoryCreate(text='Expired', expires_at=datetime.now(UTC) - timedelta(days=1)))
    registry = build_registry(force=True)
    result = asyncio.run(registry.execute('memory_purge_expired', auto_approve=True))
    assert not result.ok and retention_status()['expired_count'] == 1
    async def reject(tool, args):
        return False
    assert not asyncio.run(registry.execute('memory_purge_expired', confirm=reject)).ok
    assert retention_status()['expired_count'] == 1
    async def approve(tool, args):
        return True
    assert asyncio.run(registry.execute('memory_purge_expired', confirm=approve)).ok
    assert retention_status()['expired_count'] == 0


@pytest.mark.parametrize('query,category,expired', [('x' * 501, '', False), ('', 'x' * 41, False), ('', '', 'false')])
def test_search_validation(query, category, expired):
    with pytest.raises(ValueError):
        search_memories(query, category, expired)


def test_existing_document_search_remains_registered():
    from jarvis.tools.builtin_tools import build_registry
    registry = build_registry(force=True)
    assert registry.get('memory_search') is not None
    assert registry.get('memory_search_saved') is not None
    assert 'folder' in registry.get('memory_add_folder').parameters['properties']


def test_existing_schema_migrates_without_losing_rows(monkeypatch, tmp_path):
    import sqlite3
    path = tmp_path / 'legacy.db'
    monkeypatch.setenv('JARVIS_DB_PATH', str(path))
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE memories(id INTEGER PRIMARY KEY,text TEXT NOT NULL,category TEXT NOT NULL,created_at TEXT NOT NULL); INSERT INTO memories VALUES(1,'Keep me','general','2026-11-01');")
    rows = search_memories()
    assert rows[0]['text'] == 'Keep me' and rows[0]['expires_at'] is None
