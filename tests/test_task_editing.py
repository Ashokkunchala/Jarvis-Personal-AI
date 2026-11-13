import asyncio
import sqlite3

import pytest

from jarvis.ownership import OwnershipStore


@pytest.fixture
def store(tmp_path):
    return OwnershipStore(tmp_path / 'tasks.db')


def test_correct_prioritize_postpone_and_clear(store):
    item = store.add('Draft plan', '2026-11-10T12:00:00+05:30')
    assert item['due_at'] == '2026-11-10T06:30:00+00:00'
    edited = store.edit(item['id'], text='Review plan', due_at='2026-12-01T09:00:00+05:30', priority=1)
    assert edited['text'] == 'Review plan' and edited['priority'] == 1
    assert not edited['done'] and edited['due_at'] == '2026-12-01T03:30:00+00:00'
    assert store.edit(item['id'], clear_due=True)['due_at'] is None
    assert OwnershipStore(store.path).list()[0]['text'] == 'Review plan'


def test_timezone_offsets_compare_actual_instants(store, monkeypatch):
    monkeypatch.setattr('jarvis.ownership._now_iso', lambda: '2026-11-13T10:00:00+00:00')
    past = store.add('Actually overdue', '2026-11-13T15:00:00+05:30')
    future = store.add('Actually later', '2026-11-13T06:00:00-05:00')
    assert past['overdue'] and not future['overdue']
    assert [row['id'] for row in store.due_followups()] == [past['id']]


def test_priority_order_and_no_automatic_completion(store):
    first = store.add('Routine')
    second = store.add('Urgent')
    store.edit(second['id'], priority=1)
    assert [row['id'] for row in store.list()] == [second['id'], first['id']]
    store.complete(second['id'])
    with pytest.raises(ValueError, match='completed'):
        store.edit(second['id'], text='Changed')


@pytest.mark.parametrize('kwargs', [{'text': ' '}, {'priority': 0}, {'priority': True}, {'priority': 6}, {'due_at': '2026-12-01T09:00:00'}, {'due_at': ''}, {'due_at': '2026-12-01T09:00:00Z', 'clear_due': True}, {}, {'clear_due': 'true'}])
def test_invalid_edits_leave_original_unchanged(store, kwargs):
    item = store.add('Keep unchanged')
    with pytest.raises(ValueError):
        store.edit(item['id'], **kwargs)
    assert store.list()[0] == item


def test_new_dates_need_timezone(store):
    with pytest.raises(ValueError, match='timezone'):
        store.add('No guessing', '2026-11-15T09:00:00')


def test_legacy_schema_upgrades_and_ambiguous_date_warns(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE commitments (id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL, done INTEGER DEFAULT 0, done_at TEXT); INSERT INTO commitments(text,due_at,created_at) VALUES ('legacy','2026-11-10T09:00:00','2026-11-01');")
    store = OwnershipStore(path)
    item = store.list()[0]
    assert item['priority'] == 3 and item['date_warning'] and not item['overdue']
    store.edit(item['id'], due_at='2026-11-10T09:00:00Z')
    assert store.list()[0]['date_warning'] is None


def test_registry_edit_roundtrip(tmp_path, monkeypatch):
    from jarvis import ownership
    from jarvis.tools.builtin_tools import build_registry
    monkeypatch.setattr(ownership, '_default_store', OwnershipStore(tmp_path / 'tasks.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    task = ownership.default_store().add('Read docs')
    registry = build_registry(force=True)
    result = asyncio.run(registry.execute('edit_commitment', {'commitment_id': task['id'], 'priority': 1, 'due_at': '2026-12-01T09:00:00+05:30'}))
    assert result.ok and result.data['commitment']['priority'] == 1
