import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from jarvis.personal import PersonalStore
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def store(tmp_path):
    return PersonalStore(tmp_path / 'notes.db')


def test_edit_text_and_normalize_tags_without_changing_identity(store):
    row = store.add_note('Old text', 'work,idea')
    result = store.edit_note(row['id'], row['text'], row['tags'], ' New text ', 'Work, Urgent')
    assert result == {**row, 'text': 'New text', 'tags': 'work,urgent'}
    assert store.search_notes('urgent')[0] == result


def test_tags_clear_and_omitted_text_preserved(store):
    row = store.add_note('Keep this text', 'work')
    result = store.edit_note(row['id'], row['text'], row['tags'], tags='')
    assert result['text'] == row['text'] and result['tags'] == ''


def test_tag_only_race_and_replay_rejected(store):
    row = store.add_note('Same text', 'work')
    store.edit_note(row['id'], row['text'], row['tags'], tags='personal')
    with pytest.raises(ValueError, match='changed'):
        store.edit_note(row['id'], row['text'], row['tags'], text='New text')
    assert store.search_notes()[0]['tags'] == 'personal'


@pytest.mark.parametrize('kwargs', [dict(text=''), dict(text=' '), dict(text='x' * 1001), dict(tags='x' * 1001),
                                   dict(text=False), dict(tags=False), {}, dict(text='Original')])
def test_invalid_edits_change_nothing(store, kwargs):
    row = store.add_note('Original')
    with pytest.raises(ValueError):
        store.edit_note(row['id'], row['text'], row['tags'], **kwargs)
    assert store.search_notes() == [row]


def test_unknown_and_wrong_id_rejected(store):
    for identifier in [True, 0, -1, 99999]:
        with pytest.raises(ValueError):
            store.edit_note(identifier, 'old', '', text='new')


def test_concurrent_edit_only_one_wins(store):
    row = store.add_note('Old', 'work')

    def edit(text):
        try:
            PersonalStore(store.path).edit_note(row['id'], 'Old', 'work', text=text)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(edit, ['first', 'second'])) == 1


def test_note_search_is_literal_not_wildcard_or_sql(store):
    store.add_note('100% done', 'work')
    store.add_note('snake_case')
    store.add_note('Ordinary')
    assert [r['text'] for r in store.search_notes('%')] == ['100% done']
    assert [r['text'] for r in store.search_notes('_')] == ['snake_case']
    assert store.search_notes("' OR 1=1 --") == []
    assert len(store.search_notes('')) == 3


@pytest.mark.parametrize('amount', [float('nan'), float('inf'), float('-inf'), 'NaN', 'Infinity', True, False])
def test_expense_nonfinite_and_boolean_inputs_fail_cleanly(store, amount):
    with pytest.raises(ValueError):
        store.add_expense(amount, 'test')
    assert store.expense_summary()['count'] == 0


def test_registry_and_emergency_stop(store, monkeypatch, tmp_path):
    from jarvis import personal
    from jarvis.security import SecurityStore
    monkeypatch.setattr(personal, '_default', store)
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    row = store.add_note('Old')
    registry = build_registry(force=True)
    args = dict(note_id=row['id'], expected_text='Old', expected_tags='', text='New')
    result = asyncio.run(registry.execute('edit_note', args))
    assert result.ok and result.data['note']['text'] == 'New'
    SecurityStore().set_stop(True)
    result = asyncio.run(registry.execute('edit_note', {**args, 'expected_text': 'New', 'text': 'Newest'}))
    assert not result.ok and store.search_notes()[0]['text'] == 'New'
