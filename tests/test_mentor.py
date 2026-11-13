import asyncio

import pytest

from jarvis.mentor import LESSONS, MentorStore
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def store(tmp_path):
    return MentorStore(tmp_path / 'mentor.db')


def test_every_domain_has_lesson_practice_and_objective_feedback(store):
    assert len(store.catalog()) == 12
    for key in LESSONS:
        lesson = store.lesson(key)
        assert lesson['notes'] and lesson['practice']
        quiz = store.quiz(key)
        assert 'answer' not in quiz
        assert len(quiz['options']) == 3
        for choice in range(3):
            result = store.submit(key, choice)
            assert result['correct'] == (choice == LESSONS[key]['answer'])
            assert result['feedback']


def test_progress_uses_latest_result_without_inflating_topic_count(store):
    key = 'programming'
    store.submit(key, 0)
    assert store.progress()['weak_areas'] == [key]
    store.submit(key, 1)
    progress = store.progress()
    assert progress['passed_checkpoints'] == 1
    assert progress['attempted_checkpoints'] == 1
    assert progress['answers'][0]['attempts'] == 2
    assert not progress['weak_areas']
    assert MentorStore(store.path).progress()['passed_checkpoints'] == 1


def test_plan_dates_roll_over_month_and_year(store):
    result = store.plan(['programming', 'linux', 'cloud'], '2026-12-31', 25)
    assert [row['date'] for row in result['sessions']] == ['2026-12-31', '2027-01-01', '2027-01-02']
    assert len(store.progress('2027-01-02')['overdue']) == 2
    store.submit('programming', 1)
    assert len(store.progress('2027-01-02')['overdue']) == 1


def test_plan_upsert_retains_other_sessions(store):
    store.plan(['linux', 'cloud'], '2026-11-15')
    store.plan(['linux'], '2026-11-20')
    rows = store.progress()['sessions']
    assert len(rows) == 2
    assert next(row for row in rows if row['lesson_id'] == 'linux')['scheduled_date'] == '2026-11-20'


@pytest.mark.parametrize('ids,day,minutes', [([], '2026-11-15', 30), (['linux', 'linux'], '2026-11-15', 30), (['missing'], '2026-11-15', 30), (['linux'], 'not-a-date', 30), (['linux'], '2026-11-15', 0), (['linux'], '2026-11-15', True)])
def test_plan_validation_is_atomic(store, ids, day, minutes):
    with pytest.raises(ValueError):
        store.plan(ids, day, minutes)
    assert store.progress()['sessions'] == []


@pytest.mark.parametrize('choice', [-1, 3, '1', True, None])
def test_invalid_answers_not_recorded(store, choice):
    with pytest.raises(ValueError):
        store.submit('linux', choice)
    assert store.progress()['answers'] == []


def test_unknown_lesson_rejected(store):
    with pytest.raises(ValueError):
        store.quiz('missing')


def test_registered_tools_run_through_existing_execution_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_MENTOR_DB', str(tmp_path / 'mentor.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    registry = build_registry(force=True)
    async def run():
        assert len(registry.names('mentor')) == 12
        catalog = await registry.execute('mentor_catalog')
        assert catalog.ok and len(catalog.data['data']) == 12
        assert (await registry.execute('mentor_plan', {'lesson_ids': ['linux'], 'start_date': '2026-11-15'})).ok
        assert (await registry.execute('mentor_submit', {'lesson_id': 'linux', 'choice': 1})).ok
        progress = await registry.execute('mentor_progress')
        assert progress.ok and progress.data['data']['passed_checkpoints'] == 1
        from jarvis.security import SecurityStore
        SecurityStore().set_stop(True)
        assert not (await registry.execute('mentor_submit', {'lesson_id': 'cloud', 'choice': 1})).ok
        assert (await registry.execute('mentor_progress')).ok
    asyncio.run(run())


def test_tool_arguments_cannot_select_another_method(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_MENTOR_DB', str(tmp_path / 'mentor.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    registry = build_registry(force=True)
    result = asyncio.run(registry.execute('mentor_catalog', {'_method': 'submit', 'lesson_id': 'linux', 'choice': 1}))
    assert not result.ok
    assert MentorStore(tmp_path / 'mentor.db').progress()['answers'] == []
