"""Calendar-week review of existing manual habit and workout records, not health advice."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _now():
    return datetime.now(UTC)


def _readonly(path):
    path = Path(path).expanduser().absolute()
    if not path.is_file():
        return None
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _habits():
    from jarvis import personal
    path = personal._default.path if personal._default is not None else Path.home() / '.jarvis' / 'personal.db'
    return _readonly(path)


def _workouts():
    from app.config import Settings
    return _readonly(Settings().jarvis_db_path)


def _rows(connect, table, query, params=()):
    conn = connect()
    if conn is None:
        return [], False
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return (conn.execute(query, params).fetchall(), True) if exists else ([], False)
    finally:
        conn.close()


def weekly_wellness_review(start_day: str, timezone: str):
    """Seven named calendar days, clipped at now, with explicit IANA timezone."""
    if not isinstance(start_day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start_day):
        raise ValueError('start_day must be YYYY-MM-DD.')
    try:
        start = date.fromisoformat(start_day)
        zone = ZoneInfo(timezone)
        end = start + timedelta(days=7)
    except (ValueError, TypeError, ZoneInfoNotFoundError, OverflowError) as exc:
        raise ValueError('Choose a valid date and IANA timezone, for example Asia/Kolkata.') from exc
    now_utc = _now().astimezone(UTC)
    now = now_utc.astimezone(zone)
    if start > now.date():
        raise ValueError('A review cannot start in the future.')
    last = min(end - timedelta(days=1), now.date())
    days = [start + timedelta(days=i) for i in range((last - start).days + 1)]
    begin_instant = datetime.combine(start, time.min, tzinfo=zone)
    end_instant = datetime.combine(end, time.min, tzinfo=zone)
    # The two existing stores are read independently. Do not imply an atomic snapshot.
    habit_rows, habit_store_present = _rows(_habits, 'habit_logs',
        'SELECT habit,day FROM habit_logs WHERE day<=? ORDER BY day DESC,habit LIMIT 10001', (last.isoformat(),))
    workout_rows, workout_store_present = _rows(_workouts, 'workouts',
        'SELECT id,activity,duration_minutes,performed_at FROM workouts ORDER BY id DESC LIMIT 10001')
    partial = len(habit_rows) > 10000 or len(workout_rows) > 10000
    habit_rows, workout_rows = habit_rows[:10000], workout_rows[:10000]
    habit_days: dict[str, set[str]] = defaultdict(set)
    invalid_habits = invalid_workouts = 0
    for row in habit_rows:
        try:
            day = date.fromisoformat(row['day'])
            name = row['habit']
            if not isinstance(name, str) or not name.strip() or len(name) > 1000:
                raise ValueError('Invalid habit')
        except (TypeError, ValueError):
            invalid_habits += 1
            continue
        if day <= last:
            habit_days[name]  # Include known habits with no log in this window.
        if start <= day <= last:
            habit_days[name].add(day.isoformat())
    sessions: Counter[str] = Counter()
    minutes: Counter[str] = Counter()
    activities: dict[str, dict[str, int]] = defaultdict(lambda: {'sessions': 0, 'minutes': 0})
    excluded_future = 0
    for row in workout_rows:
        try:
            performed = datetime.fromisoformat(row['performed_at'])
            duration, activity = row['duration_minutes'], row['activity']
            if performed.tzinfo is None or type(duration) is not int or not 1 <= duration <= 1440:
                raise ValueError('Unverifiable workout')
            if not isinstance(activity, str) or not activity.strip() or len(activity) > 120:
                raise ValueError('Invalid activity')
            performed = performed.astimezone(zone)
        except (ValueError, TypeError, OverflowError):
            invalid_workouts += 1
            continue
        instant = performed.astimezone(UTC)
        if instant > now_utc:
            excluded_future += 1
            continue
        if begin_instant.astimezone(UTC) <= instant < end_instant.astimezone(UTC):
            key = performed.date().isoformat()
            sessions[key] += 1
            minutes[key] += duration
            activities[activity]['sessions'] += 1
            activities[activity]['minutes'] += duration
    return {
        'start_day': start.isoformat(), 'end_day': (end - timedelta(days=1)).isoformat(),
        'timezone': timezone, 'as_of': now.isoformat(), 'reviewed_through_day': last.isoformat(),
        'days_in_window': 7, 'elapsed_calendar_days': len(days), 'partial_period': now_utc < end_instant.astimezone(UTC),
        'partial_records': partial,
        'stores_present': {'habits': habit_store_present, 'workouts': workout_store_present}, 'habit_breakdown_truncated': len(habit_days) > 100,
        'known_habit_count_scanned': len(habit_days),
        'habits': [{'habit': name, 'logged_days': sorted(logged), 'logged_day_count': len(logged),
                    'unlogged_days': [d.isoformat() for d in days if d.isoformat() not in logged]}
                   for name, logged in sorted(habit_days.items())[:100]],
        'workouts': {'sessions': sum(sessions.values()), 'minutes': sum(minutes.values()),
                     'activity_breakdown_truncated': len(activities) > 100,
                     'by_activity': [dict(activity=name, **totals) for name, totals in sorted(activities.items())[:100]],
                     'by_day': [dict(day=d.isoformat(), sessions=sessions[d.isoformat()], minutes=minutes[d.isoformat()]) for d in days]},
        'excluded_records': {'invalid_habit_rows_scanned': invalid_habits,
                             'unverifiable_workout_rows_scanned': invalid_workouts,
                             'future_workout_rows_scanned': excluded_future},
        'limits': 'Manual records only, not medical advice, a fitness score, goal adherence or evidence of inactivity. Unlogged means not recorded, not missed. Current day may be incomplete. Habits retain their originally logged calendar dates; timezone only buckets timestamped workouts. No notes or workout timestamps returned. Existing local habit and backend workout stores are separate non-atomic reads; newest 10000 rows per store are scanned and truncation is flagged. Habit and activity breakdowns show up to 100 alphabetically ordered groups, with truncation flags. Exclusion counts apply to all scanned records, not solely this week. Missing source tables are flagged; no database is created or migrated. No wearable/sleep/nutrition data, reminders, external access or record changes.',
    }


def register_wellness_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    registry.register(Tool(
        name='weekly_wellness_review',
        description='Read a seven-calendar-day review of manually logged habits and backend workouts. Requires start_day and IANA timezone. Missing records are not failures; no medical assessment or external access.',
        parameters={'type': 'object', 'properties': {
            'start_day': {'type': 'string', 'description': 'First calendar day, YYYY-MM-DD, not in the future.'},
            'timezone': {'type': 'string', 'description': 'Explicit IANA timezone, e.g. Asia/Kolkata.'}},
            'required': ['start_day', 'timezone']},
        handler=weekly_wellness_review, risk=Risk.SAFE, category='personal'))
