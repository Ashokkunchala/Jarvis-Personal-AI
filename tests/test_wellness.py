import asyncio
from datetime import UTC, datetime

import pytest

from jarvis import wellness
from jarvis.personal import PersonalStore
from jarvis.tools.builtin_tools import build_registry


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'backend.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    personal = PersonalStore(tmp_path / 'personal.db')
    monkeypatch.setattr(wellness, '_habits', personal._connect)
    monkeypatch.setattr(wellness, '_now', lambda: datetime(2026, 11, 13, 12, tzinfo=UTC))
    from app.personal_data import _connect
    monkeypatch.setattr(wellness, '_workouts', _connect)
    return personal


def workout(activity, minutes, when):
    with wellness._workouts() as db:
        db.execute('INSERT INTO workouts(activity,duration_minutes,performed_at,created_at,notes) VALUES(?,?,?,?,?)',
                   (activity, minutes, when, '2026-11-13T12:00:00Z', 'PRIVATE NOTE'))


def habit(personal, name, day):
    with personal._connect() as db:
        db.execute('INSERT INTO habit_logs(habit,day) VALUES(?,?)', (name, day))


def test_combines_existing_stores_without_new_schema(stores):
    habit(stores, 'walk', '2026-11-09')
    habit(stores, 'walk', '2026-11-11')
    habit(stores, 'read', '2026-11-01')
    workout('walking', 30, '2026-11-09T08:00:00+05:30')
    workout('yoga', 20, '2026-11-11T08:00:00+05:30')
    result = wellness.weekly_wellness_review('2026-11-09', 'Asia/Kolkata')
    assert result['workouts']['sessions'] == 2 and result['workouts']['minutes'] == 50
    assert result['elapsed_calendar_days'] == 5 and result['partial_period']
    assert result['habits'][0]['habit'] == 'read' and result['habits'][0]['logged_day_count'] == 0
    assert result['habits'][1]['logged_day_count'] == 2
    assert result['habits'][1]['unlogged_days'] == ['2026-11-10', '2026-11-12', '2026-11-13']
    assert 'PRIVATE NOTE' not in str(result)


def test_empty_records_are_not_diagnosed_as_inactivity(stores):
    result = wellness.weekly_wellness_review('2026-11-02', 'Asia/Kolkata')
    assert result['habits'] == [] and result['workouts']['sessions'] == 0
    assert not result['partial_period'] and len(result['workouts']['by_day']) == 7
    assert 'not medical advice' in result['limits'] and 'not missed' in result['limits']


def test_timezone_buckets_offsets_and_exclusive_end(stores):
    workout('walk', 10, '2026-11-01T20:00:00Z')  # Nov 2 in India
    workout('walk', 20, '2026-11-08T18:29:59Z')  # Nov 8 in India
    workout('walk', 40, '2026-11-08T18:30:00Z')  # Nov 9, outside
    result = wellness.weekly_wellness_review('2026-11-02', 'Asia/Kolkata')
    assert result['workouts']['minutes'] == 30 and result['workouts']['sessions'] == 2
    assert result['workouts']['by_day'][0]['minutes'] == 10
    assert result['workouts']['by_day'][-1]['minutes'] == 20


def test_same_day_future_and_bad_timestamps_are_excluded(stores):
    workout('walk', 10, '2026-11-13T12:00:00Z')
    workout('walk', 20, '2026-11-13T12:01:00Z')
    workout('walk', 30, '2026-11-13T08:00:00')
    workout('walk', 40, 'bad')
    result = wellness.weekly_wellness_review('2026-11-09', 'UTC')
    assert result['workouts']['minutes'] == 10
    assert result['excluded_records']['future_workout_rows_scanned'] == 1
    assert result['excluded_records']['unverifiable_workout_rows_scanned'] == 2


def test_dst_fold_compares_instants_not_wall_clock(stores, monkeypatch):
    monkeypatch.setattr(wellness, '_now', lambda: datetime(2026, 11, 1, 6, 15, tzinfo=UTC))
    workout('walk', 10, '2026-11-01T01:45:00-04:00')  # earlier first 1:45
    workout('walk', 20, '2026-11-01T01:30:00-05:00')  # later second 1:30
    result = wellness.weekly_wellness_review('2026-10-26', 'America/New_York')
    assert result['workouts']['minutes'] == 10
    assert result['excluded_records']['future_workout_rows_scanned'] == 1


@pytest.mark.parametrize('start,zone', [('2026-11-14', 'UTC'), ('2026-02-30', 'UTC'), ('20261109', 'UTC'),
                                       ('2026-11-09', 'Not/AZone'), ('2026-11-09', '../UTC'), (True, 'UTC')])
def test_invalid_requests_rejected(stores, start, zone):
    with pytest.raises(ValueError):
        wellness.weekly_wellness_review(start, zone)


def test_future_habit_dates_not_included(stores):
    habit(stores, 'future-only', '2026-11-15')
    habit(stores, 'walk', '2026-11-14')
    assert wellness.weekly_wellness_review('2026-11-09', 'UTC')['habits'] == []


def test_read_only_repeatable_and_registered(stores):
    workout('walk', 10, '2026-11-10T12:00:00Z')
    result = asyncio.run(build_registry(force=True).execute('weekly_wellness_review', {'start_day': '2026-11-09', 'timezone': 'UTC'}))
    assert result.ok and result.data['workouts']['minutes'] == 10
    assert wellness.weekly_wellness_review('2026-11-09', 'UTC') == result.data
    with wellness._workouts() as db:
        assert db.execute('SELECT COUNT(*) FROM workouts').fetchone()[0] == 1


def test_record_scan_limit_visible(stores):
    with wellness._workouts() as db:
        db.executemany('INSERT INTO workouts(activity,duration_minutes,performed_at,created_at) VALUES(?,?,?,?)',
                       [('walk', 1, '2026-11-10T12:00:00Z', '')] * 10001)
    result = wellness.weekly_wellness_review('2026-11-09', 'UTC')
    assert result['partial_records'] and result['workouts']['sessions'] == 10000


def test_breakdown_limits_do_not_hide_total(stores):
    for i in range(101):
        habit(stores, f'habit-{i}', '2026-11-10')
        workout(f'activity-{i}', 1, '2026-11-10T12:00:00Z')
    result = wellness.weekly_wellness_review('2026-11-09', 'UTC')
    assert result['habit_breakdown_truncated'] and len(result['habits']) == 100
    assert result['workouts']['activity_breakdown_truncated'] and result['workouts']['sessions'] == 101


def test_missing_stores_do_not_create_files(tmp_path, monkeypatch):
    path = tmp_path / 'absent.db'
    monkeypatch.setattr(wellness, '_habits', lambda: wellness._readonly(path))
    monkeypatch.setattr(wellness, '_workouts', lambda: wellness._readonly(path))
    result = wellness.weekly_wellness_review('2020-01-06', 'UTC')
    assert result['stores_present'] == {'habits': False, 'workouts': False}
    assert not path.exists()


def test_real_readonly_connection_blocks_mutation(stores, tmp_path):
    with wellness._readonly(stores.path) as db:
        import sqlite3
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO habit_logs(habit,day) VALUES('x','2026-11-10')")
