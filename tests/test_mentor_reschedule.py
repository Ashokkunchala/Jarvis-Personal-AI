import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from jarvis.mentor import LESSONS, MentorStore
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def store(tmp_path):
    return MentorStore(tmp_path / 'mentor.db')


def day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def test_preview_is_readonly_and_skips_existing_dates(store):
    store.plan(['linux', 'cloud'], day(-4), 45)
    store.plan(['security'], day(0), 20)
    before = store.progress()
    result = store.reschedule_preview(day(0))
    assert not result['changed']
    assert [r['new_date'] for r in result['proposals']] == [day(1), day(2)]
    assert all(r['minutes'] == 45 for r in result['proposals'])
    assert store.progress() == before


def test_passed_checkpoint_not_proposed_or_moved(store):
    store.plan(['linux'], day(-2))
    store.submit('linux', LESSONS['linux']['answer'])
    assert not store.reschedule_preview(day(0))['proposals']
    with pytest.raises(ValueError, match='passed'):
        store.reschedule_session('linux', day(-2), day(0))


def test_exact_session_moves_and_progress_persists(store):
    store.plan(['linux', 'cloud'], day(-3), 40)
    before = store.progress()['answers']
    result = store.reschedule_session('linux', day(-3), day(1))
    assert result['date'] == day(1) and result['minutes'] == 40
    progress = MentorStore(store.path).progress()
    assert progress['answers'] == before
    assert progress['overdue'][0]['lesson_id'] == 'cloud'
    assert len(progress['overdue']) == 1


def test_stale_or_replayed_proposals_fail(store):
    store.plan(['linux'], day(-3))
    store.reschedule_session('linux', day(-3), day(1))
    with pytest.raises(ValueError, match='changed'):
        store.reschedule_session('linux', day(-3), day(2))
    assert store.progress()['sessions'][0]['scheduled_date'] == day(1)


def test_occupied_target_does_not_change_anything(store):
    store.plan(['linux'], day(-3))
    store.plan(['cloud'], day(1))
    before = store.progress()
    with pytest.raises(ValueError, match='already has'):
        store.reschedule_session('linux', day(-3), day(1))
    assert before == store.progress()


@pytest.mark.parametrize('old,new', [(-2, -1), (0, 1), (1, 2)])
def test_only_overdue_to_nonpast_is_allowed(store, old, new):
    store.plan(['linux'], day(old))
    with pytest.raises(ValueError):
        store.reschedule_session('linux', day(old), day(new))


def test_future_start_required_for_preview_and_unknown_session_rejected(store):
    with pytest.raises(ValueError):
        store.reschedule_preview(day(-1))
    with pytest.raises(ValueError):
        store.reschedule_session('linux', day(-1), day(0))


def test_concurrent_reschedules_cannot_claim_same_day(store):
    store.plan(['linux', 'cloud'], day(-4))

    def move(args):
        key, old = args
        try:
            return MentorStore(store.path).reschedule_session(key, old, day(1))['changed']
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(move, [('linux', day(-4)), ('cloud', day(-3))]))
    assert sum(outcomes) == 1


def test_registration_and_exact_arguments(store, monkeypatch, tmp_path):
    monkeypatch.setenv('JARVIS_MENTOR_DB', store.path)
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    store.plan(['linux'], day(-1))
    registry = build_registry(force=True)
    result = asyncio.run(registry.execute('mentor_reschedule_preview', {'start_date': day(0)}))
    assert result.ok and not result.data['data']['changed']
    proposal = result.data['data']['proposals'][0]
    proposal.pop('minutes')
    result = asyncio.run(registry.execute('mentor_reschedule_session', proposal))
    assert result.ok and result.data['data']['changed']


def test_preview_calendar_boundary_fails_without_mutation(store):
    store.plan(['linux', 'cloud'], day(-4))
    before = store.progress()
    with pytest.raises(ValueError, match='calendar dates'):
        store.reschedule_preview('9999-12-31')
    assert store.progress() == before
