import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from jarvis.mentor_projects import PROJECTS, ProjectStore, project_brief
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / 'mentor.db')


def test_all_project_briefs_have_progressive_deliverables_and_review_checks():
    assert len(PROJECTS) == 4
    for key in PROJECTS:
        brief = project_brief(key)
        assert brief['scope'] and brief['prerequisites'] and brief['source'].startswith('https://')
        assert len(brief['milestones']) == 3
        for milestone in brief['milestones']:
            assert milestone['task'] and len(milestone['deliverables']) >= 3 and len(milestone['review_checks']) >= 2
        brief['milestones'][0]['task'] = 'changed copy'
        assert project_brief(key)['milestones'][0]['task'] != 'changed copy'


def test_invalid_project_not_started(store):
    with pytest.raises(ValueError):
        store.start('missing')
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM mentor_projects').fetchone()[0] == 0


def test_evidence_journal_survives_restart_without_grading_or_execution(store, tmp_path):
    session = store.start('python_sqlite_ledger')
    marker = tmp_path / 'should-not-exist'
    evidence = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    result = store.submit(session['session_id'], 0, evidence)
    assert result['verified'] is False and result['review_checks']
    resumed = ProjectStore(store.path).resume(session['session_id'])
    assert resumed['next_milestone']['position'] == 1
    history = store.history(session['session_id'])
    assert history['evidence'][0]['evidence'] == evidence
    assert not marker.exists() and not history['verified']
    assert 'score' not in result


def test_all_submitted_does_not_claim_completed_mastery(store):
    session = store.start('kubernetes_probe_design')['session_id']
    for position in range(3):
        result = store.submit(session, position, f'Self-reported evidence {position}')
    assert result['session']['state'] == 'all_evidence_submitted'
    assert result['session']['next_milestone'] is None
    assert 'not proof' in result['session']['notice']
    with pytest.raises(ValueError):
        store.submit(session, 3, 'extra evidence')


@pytest.mark.parametrize('position,evidence', [(True, 'valid'), (-1, 'valid'), ('0', 'valid'), (0, ''), (0, ' '), (0, 'x' * 4001), (0, None)])
def test_invalid_evidence_is_not_recorded(store, position, evidence):
    session = store.start('react_task_board')['session_id']
    with pytest.raises(ValueError):
        store.submit(session, position, evidence)
    assert store.resume(session)['evidence_submissions'] == 0


def test_replay_and_out_of_order_refused(store):
    session = store.start('trace_incident_review')['session_id']
    with pytest.raises(ValueError):
        store.submit(session, 1, 'too early')
    store.submit(session, 0, 'first evidence')
    with pytest.raises(ValueError):
        store.submit(session, 0, 'repeat evidence')
    assert len(store.history(session)['evidence']) == 1


def test_concurrent_submission_advances_once(store):
    session = store.start('python_sqlite_ledger')['session_id']

    def submit(evidence):
        try:
            ProjectStore(store.path).submit(session, 0, evidence)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(submit, ['first', 'second'])) == 1
    assert store.resume(session)['evidence_submissions'] == 1


def test_saved_brief_does_not_change_under_active_session(store, monkeypatch):
    session = store.start('trace_incident_review')['session_id']
    before = store.resume(session)
    monkeypatch.setitem(PROJECTS['trace_incident_review'], 'milestones', [])
    assert store.resume(session) == before
    assert store.submit(session, 0, 'Evidence')['session']['next_milestone']['position'] == 1


def test_missing_session_refused(store):
    for fn in [store.resume, store.history]:
        with pytest.raises(ValueError):
            fn('missing')
    with pytest.raises(ValueError):
        store.submit('missing', 0, 'Evidence')


def test_registry_stop_and_existing_mentor_progress_unchanged(store, monkeypatch, tmp_path):
    from jarvis.mentor import MentorStore
    from jarvis.security import SecurityStore
    monkeypatch.setenv('JARVIS_MENTOR_DB', store.path)
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    before = MentorStore(store.path).progress()
    registry = build_registry(force=True)
    assert len(registry.names('mentor_projects')) == 6
    started = asyncio.run(registry.execute('mentor_project_start', {'project_id': 'react_task_board'}))
    assert started.ok
    session = started.data['session_id']
    SecurityStore().set_stop(True)
    result = asyncio.run(registry.execute('mentor_project_submit', {'session_id': session, 'position': 0, 'evidence': 'Evidence'}))
    assert not result.ok and store.resume(session)['evidence_submissions'] == 0
    assert asyncio.run(registry.execute('mentor_project_resume', {'session_id': session})).ok
    assert MentorStore(store.path).progress() == before
