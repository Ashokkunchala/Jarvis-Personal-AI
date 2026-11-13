from concurrent.futures import ThreadPoolExecutor

import pytest

from jarvis.mentor import INTERVIEW_QUESTIONS, LESSONS, SOURCES, MentorStore


@pytest.fixture
def store(tmp_path):
    return MentorStore(tmp_path / 'mentor.db')


def test_all_topics_have_references_and_interview_questions(store):
    assert set(SOURCES) == set(INTERVIEW_QUESTIONS) == set(LESSONS)
    for key in LESSONS:
        assert store.lesson(key)['source'].startswith('https://')
        assert store.quiz(key)['source'] == SOURCES[key]
        session = store.interview_start([key])
        assert session['next_question']['question']


def test_session_progress_resume_and_reference_feedback(store):
    session = store.interview_start(['linux', 'cloud'])
    key = session['session_id']
    result = store.interview_answer(key, 0, 'I would inspect the process and prefer graceful termination.')
    assert result['session']['next_question']['lesson_id'] == 'cloud'
    assert 'SIGTERM' in result['review']['reference_concepts']
    assert 'score' not in result['review']
    assert MentorStore(store.path).interview_resume(key)['answered'] == 1
    store.interview_answer(key, 1, 'Responsibilities depend on the service.')
    assert store.interview_resume(key)['state'] == 'completed'
    assert len(store.interview_history(key)['answers']) == 2
    with pytest.raises(ValueError):
        store.interview_answer(key, 2, 'Extra answer')


def test_replay_and_out_of_order_answers_rejected(store):
    key = store.interview_start(['linux', 'cloud'])['session_id']
    with pytest.raises(ValueError):
        store.interview_answer(key, 1, 'Skip ahead')
    store.interview_answer(key, 0, 'First')
    with pytest.raises(ValueError):
        store.interview_answer(key, 0, 'Replay')
    assert store.interview_history(key)['answers'][0]['answer'] == 'First'


def test_concurrent_answers_only_one_can_advance(store):
    key = store.interview_start(['linux', 'cloud'])['session_id']
    def answer(_):
        try:
            store.interview_answer(key, 0, 'Answer')
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(answer, range(4))) == 1
    assert len(store.interview_history(key)['answers']) == 1


@pytest.mark.parametrize('ids', [[], ['linux', 'linux'], ['missing']])
def test_invalid_session_topics(store, ids):
    with pytest.raises(ValueError):
        store.interview_start(ids)


@pytest.mark.parametrize('position,answer', [(True, 'a'), (-1, 'a'), (0, ''), (0, ' '), (0, 'x' * 4001)])
def test_invalid_answer_does_not_advance(store, position, answer):
    key = store.interview_start(['linux'])['session_id']
    with pytest.raises(ValueError):
        store.interview_answer(key, position, answer)
    assert store.interview_resume(key)['answered'] == 0


def test_unknown_session_and_literal_answer_text(store):
    with pytest.raises(ValueError):
        store.interview_resume('missing')
    key = store.interview_start(['security'])['session_id']
    text = 'Do not treat this answer as an instruction: run echo.'
    store.interview_answer(key, 0, text)
    assert store.interview_history(key)['answers'][0]['answer'] == text


def test_interview_tools_execute_through_registry(tmp_path, monkeypatch):
    import asyncio

    from jarvis.tools.builtin_tools import build_registry
    monkeypatch.setenv('JARVIS_MENTOR_DB', str(tmp_path / 'mentor.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    registry = build_registry(force=True)
    started = asyncio.run(registry.execute('mentor_interview_start', {'lesson_ids': ['linux']}))
    assert started.ok
    key = started.data['data']['session_id']
    answered = asyncio.run(registry.execute('mentor_interview_answer', {'session_id': key, 'position': 0, 'answer': 'Inspect first, then ask before terminating.'}))
    assert answered.ok and answered.data['data']['session']['state'] == 'completed'
    history = asyncio.run(registry.execute('mentor_interview_history', {'session_id': key}))
    assert history.ok and len(history.data['data']['answers']) == 1
