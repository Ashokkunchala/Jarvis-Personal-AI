import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.personal_data import MemoryCreate, _connect, create_memory
from jarvis.memory.controls import correct_memory, review_memory_duplicates, search_memories
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'memory.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    with _connect():
        pass


def test_correction_preserves_identity_category_expiry_and_other_records():
    expired = datetime.now(UTC) - timedelta(days=1)
    row = create_memory(MemoryCreate(text='Old city', category='location', expires_at=expired))
    other = create_memory(MemoryCreate(text='Different fact', category='general'))
    result = correct_memory(row['id'], 'Old city', '  Corrected city  ')
    assert result['memory_id'] == row['id'] and result['text'] == 'Corrected city'
    assert result['category'] == 'location' and result['expires_at'] == row['expires_at']
    assert [r['id'] for r in search_memories()] == [other['id']]
    assert search_memories('Corrected', include_expired=True)[0]['id'] == row['id']


def test_expected_text_is_exact_not_normalized_or_interpreted():
    row = create_memory(MemoryCreate(text="A quote's meaning", category='general'))
    with pytest.raises(ValueError, match='changed'):
        correct_memory(row['id'], "a quote's meaning", 'new')
    correct_memory(row['id'], "A quote's meaning", "value ' OR 1=1 --")
    assert search_memories()[0]['text'] == "value ' OR 1=1 --"


def test_replayed_stale_or_missing_edits_rejected():
    row = create_memory(MemoryCreate(text='old'))
    correct_memory(row['id'], 'old', 'new')
    with pytest.raises(ValueError, match='changed'):
        correct_memory(row['id'], 'old', 'newer')
    with pytest.raises(ValueError, match='not found'):
        correct_memory(9999, 'old', 'new')
    assert search_memories()[0]['text'] == 'new'


@pytest.mark.parametrize('identifier,expected,new', [(True, 'old', 'new'), (0, 'old', 'new'), (1, '', 'new'),
                                                   (1, 'x' * 2001, 'new'), (1, 'old', ' '), (1, 'old', 'x' * 2001),
                                                   (1, 'old', None), (1, 'old', 'old')])
def test_invalid_correction_rejected(identifier, expected, new):
    with pytest.raises(ValueError):
        correct_memory(identifier, expected, new)


def test_concurrent_edits_only_one_wins():
    row = create_memory(MemoryCreate(text='old'))

    def edit(new):
        try:
            correct_memory(row['id'], 'old', new)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(edit, ['first', 'second']))
    assert sum(outcomes) == 1
    assert search_memories()[0]['text'] in ('first', 'second')


def test_duplicate_review_is_literal_same_category_and_readonly():
    a = create_memory(MemoryCreate(text='Uses  Python', category='work'))
    b = create_memory(MemoryCreate(text='uses\npython', category='work'))
    create_memory(MemoryCreate(text='uses python', category='personal'))
    create_memory(MemoryCreate(text='Does not use Python', category='work'))
    before = search_memories(include_expired=True)
    result = review_memory_duplicates()
    assert result['duplicate_groups'] == [{'category': 'work', 'memory_ids': [b['id'], a['id']]}]
    assert 'uses python' not in str(result)
    assert before == search_memories(include_expired=True)


def test_expired_duplicates_excluded_by_default():
    a = create_memory(MemoryCreate(text='same'))
    b = create_memory(MemoryCreate(text='same', expires_at=datetime.now(UTC) - timedelta(days=1)))
    assert review_memory_duplicates()['duplicate_groups'] == []
    assert review_memory_duplicates(True)['duplicate_groups'][0]['memory_ids'] == [b['id'], a['id']]
    with pytest.raises(ValueError):
        review_memory_duplicates('true')


def test_review_is_bounded_and_flags_partial_results():
    with _connect() as db:
        db.executemany('INSERT INTO memories(text,category,created_at) VALUES(?,?,?)', [('same', 'general', '')] * 1001)
    result = review_memory_duplicates()
    assert result['partial_records'] and result['records_reviewed'] == 1000
    assert len(result['duplicate_groups'][0]['memory_ids']) == 1000
    assert 1 not in result['duplicate_groups'][0]['memory_ids']


def test_new_tools_respect_existing_emergency_stop():
    from jarvis.security import SecurityStore
    row = create_memory(MemoryCreate(text='old'))
    registry = build_registry(force=True)
    SecurityStore().set_stop(True)
    result = asyncio.run(registry.execute('memory_correct_saved', {'memory_id': row['id'], 'expected_text': 'old', 'new_text': 'new'}))
    assert not result.ok and search_memories()[0]['text'] == 'old'
    assert asyncio.run(registry.execute('memory_review_duplicates', {})).ok
