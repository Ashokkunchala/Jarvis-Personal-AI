import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from jarvis.personal import PersonalStore
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def store(tmp_path):
    return PersonalStore(tmp_path / 'expenses.db')


def add(store, amount=100, category='food', note='receipt', day='2026-01-05'):
    row = store.add_expense(amount, category, note, day)
    return next(r for r in store.list_expenses(day[:7])['expenses'] if r['id'] == row['id'])


def test_correct_entry_without_duplicate_and_summary_follows_month(store):
    row = add(store)
    result = store.edit_expense(row['id'], row['revision'], amount=25, category='Travel', note='', spent_on='2026-02-01')['expense']
    assert result['id'] == row['id'] and result['created_at'] == row['created_at']
    assert result['amount'] == 25 and result['category'] == 'travel' and result['note'] == ''
    assert result['revision'] != row['revision']
    assert store.expense_summary('2026-01')['count'] == 0
    assert store.expense_summary('2026-02')['total'] == 25


def test_omitted_fields_preserved_and_stale_token_refused(store):
    row = add(store)
    result = store.edit_expense(row['id'], row['revision'], note='corrected')['expense']
    assert result == {**row, 'note': 'corrected', 'revision': result['revision']}
    with pytest.raises(ValueError, match='changed'):
        store.edit_expense(row['id'], row['revision'], amount=1)
    assert store.expense_summary('2026-01')['total'] == 100


@pytest.mark.parametrize('kwargs', [{}, dict(amount=True), dict(amount=float('nan')), dict(amount=float('inf')),
                                   dict(amount=0), dict(amount=-1), dict(amount=10**9), dict(amount='bad'),
                                   dict(category=' '), dict(note='x'*1001), dict(spent_on='2026-02-30'),
                                   dict(spent_on='20260105'), dict(amount=100)])
def test_invalid_or_noop_edits_do_not_change_row(store, kwargs):
    row = add(store)
    with pytest.raises(ValueError):
        store.edit_expense(row['id'], row['revision'], **kwargs)
    assert store.list_expenses('2026-01')['expenses'] == [row]


def test_unknown_and_wrong_id_or_revision_refused(store):
    for identifier, revision in [(True, 'a'*64), (0, 'a'*64), (999, 'a'*64), (1, 'bad')]:
        with pytest.raises(ValueError):
            store.edit_expense(identifier, revision, amount=1)


def test_review_limit_and_literal_month_validation(store):
    add(store)
    add(store)
    result = store.list_expenses('2026-01', 1)
    assert result['truncated'] and len(result['expenses']) == 1
    for month in ['2026-1', '2026-13', '202601', '2026-01 ', "' OR 1=1 --", True]:
        with pytest.raises(ValueError):
            store.list_expenses(month)
        with pytest.raises(ValueError):
            store.expense_summary(month)
    for limit in [0, 201, True]:
        with pytest.raises(ValueError):
            store.list_expenses('2026-01', limit)


def test_concurrent_corrections_only_one_wins(store):
    row = add(store)

    def edit(amount):
        try:
            PersonalStore(store.path).edit_expense(row['id'], row['revision'], amount=amount)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(edit, [1, 2])) == 1
    assert store.expense_summary('2026-01')['count'] == 1


def test_registry_boundary_blocks_edit_after_stop(store, monkeypatch, tmp_path):
    from jarvis import personal
    from jarvis.security import SecurityStore
    monkeypatch.setattr(personal, '_default', store)
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'safety.db'))
    row = add(store)
    registry = build_registry(force=True)
    SecurityStore().set_stop(True)
    result = asyncio.run(registry.execute('edit_expense', dict(expense_id=row['id'], expected_revision=row['revision'], amount=1)))
    assert not result.ok
    result = asyncio.run(registry.execute('list_expenses', {'month': '2026-01'}))
    assert result.ok and result.data['expenses'][0]['amount'] == 100
