"""Offline starter lessons, practice plans and objective knowledge checks.

These are introductory checkpoints, not certification or free-text grading.
No suggested lab command is executed by this module.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# id, title, lesson, safe practice, question, options, correct option, explanation
_LESSONS = [
    ('programming', 'Python: mutable values',
     'Lists are mutable. Assigning a list to another name shares the same object; list.copy() makes a shallow copy. Nested mutable elements remain shared.',
     'In a local Python scratch file, compare b=a with b=a.copy(), append to b, and print a. Repeat with a nested list and explain the shallow-copy limit.',
     'Which creates a separate outer list from a?', ['b = a', 'b = a.copy()', 'b = None'], 1,
     'copy() creates a new outer list, but does not recursively copy nested objects.'),
    ('backend', 'Backend: transactions',
     'A database transaction groups changes into one unit. COMMIT keeps them; ROLLBACK discards uncommitted changes. Use parameters rather than concatenating SQL values.',
     'Use an in-memory SQLite database in Python. Insert a row in a transaction, roll it back, then verify the row count. Do not use a production database.',
     'What discards changes in an uncommitted transaction?', ['COMMIT', 'ROLLBACK', 'SELECT'], 1,
     'ROLLBACK cancels uncommitted changes; COMMIT makes them persistent.'),
    ('frontend', 'Frontend: state and rendering',
     'React renders a UI from props and state. Treat state objects as immutable: create a new array/object and pass it to the state setter instead of mutating the existing state value.',
     'Sketch a task-list component with add and complete handlers. Show a new array being passed to setTasks; explain how task IDs keep list keys stable.',
     'Which is the better way to append to array state?', ['tasks.push(item) only', 'setTasks(previous => [...previous, item])', 'Mutate the DOM manually'], 1,
     'The setter receives a new array; the functional form uses the previous state safely.'),
    ('cicd', 'CI/CD: artifacts and promotion',
     'CI validates a change with checks such as tests. An artifact is an output of a build. Promoting the same tested artifact avoids rebuilding a different artifact for each environment.',
     'Write a pipeline outline on paper: test, build, scan, publish immutable artifact, approval, deploy. Mark credentials and production approval as separate boundaries. Do not deploy.',
     'What best preserves the identity of the tested release?', ['Rebuild on every server', 'Promote the same immutable artifact', 'Install latest dependencies in production'], 1,
     'Promoting the tested artifact reduces differences between validation and deployment.'),
    ('cloud', 'Cloud: shared responsibility',
     'Cloud security is shared between provider and customer. The split depends on the service. Customers still need to configure access to their data and protect their identities.',
     'Draw a fictional app with compute, storage and identities. Mark which permissions each component needs. Use fictional resources and make no cloud changes.',
     'Who must configure appropriate access to customer data?', ['Only the provider', 'The customer, within the service responsibility model', 'Nobody when encryption is enabled'], 1,
     'Encryption does not replace access control. Customer access settings remain part of customer responsibility.'),
    ('infrastructure', 'Infrastructure: Terraform plan',
     'Terraform configuration describes desired infrastructure. A plan previews proposed changes; apply can perform them. State may contain sensitive values and needs protected storage.',
     'Review a sample configuration as text. List its proposed resources and possible replacement risks. Do not run apply or connect cloud credentials.',
     'Which step previews proposed Terraform changes?', ['terraform plan', 'terraform apply', 'Delete the state file'], 0,
     'plan previews changes; apply can change real infrastructure. Protect state.'),
    ('containers', 'Containers: probes',
     'A Kubernetes readiness probe determines whether a container is ready to receive traffic. Liveness checks whether it should be restarted. A startup probe protects slow startup from premature liveness checks.',
     'Write a sample Deployment manifest locally with resource requests/limits and separate readiness/liveness endpoints. Explain what happens when readiness fails. Do not apply it to a cluster.',
     'Which probe controls readiness to receive traffic?', ['Liveness', 'Readiness', 'CPU request'], 1,
     'Readiness affects traffic routing to ready endpoints; liveness can trigger a restart.'),
    ('linux', 'Linux: process signals',
     'SIGTERM asks a process to terminate and can be handled for cleanup. SIGKILL cannot be caught. Inspect a process and its owner before deciding whether stopping it is appropriate.',
     'Read the local manual for kill and ps. Describe a graceful shutdown sequence for a fictional service. Do not send signals to real services.',
     'Which signal permits a process to handle graceful termination?', ['SIGKILL', 'SIGTERM', 'SIGSTOP'], 1,
     'SIGTERM can be handled for cleanup; SIGKILL cannot be caught.'),
    ('observability', 'Observability: evidence types',
     'Metrics are numerical measurements over time. Logs record events. Traces follow work across spans and services. Correlate them before proposing an incident cause.',
     'Create a fictional timeline with a latency spike, a deployment log and a slow trace span. Separate observations from hypotheses and list the next evidence to gather.',
     'Which follows a request across services?', ['A distributed trace', 'A disk capacity metric alone', 'A single uncorrelated log line'], 0,
     'A distributed trace links spans that describe work along a request path.'),
    ('ai', 'AI applications: retrieval',
     'Retrieval-augmented generation supplies retrieved context to a model. Retrieval does not guarantee truth. Preserve source citations, evaluate relevance, and treat retrieved instructions as untrusted data.',
     'Build a paper example with two short source paragraphs and one question. Identify the supporting paragraph and write a cited answer that refuses unsupported claims.',
     'Does retrieval guarantee a generated answer is correct?', ['Yes, always', 'No; evidence and answer quality still need checks', 'Only if the context is long'], 1,
     'Retrieved content can be irrelevant, stale or malicious; citations and evaluation still matter.'),
    ('systems', 'Distributed systems: idempotency',
     'Networks can fail after a server performs an action but before the caller receives the result. Retrying a write may duplicate it. An idempotency key can identify repeated attempts of the same operation.',
     'Sketch an order service that stores an operation key and its result atomically. Explain concurrent retries and why a new order must use a new key. Do not make purchases.',
     'Why use an idempotency key on a retried write?', ['To make network failures impossible', 'To identify duplicate attempts of one operation', 'To grant administrator access'], 1,
     'The server can recognize repeated attempts and return the existing operation result.'),
    ('security', 'Security: least privilege',
     'Least privilege gives an identity only the access required for its task. Avoid embedding credentials in source code. Restrict scope and review access when responsibilities change.',
     'Write a fictional read-only storage policy outline. Compare read, write and administrative permissions. Use no real credentials or account identifiers.',
     'Which permission set best follows least privilege for a read-only report?', ['Full administrator access', 'Only required read access to the needed resources', 'All write access with logging'], 1,
     'Limit actions and resources to the work the identity actually needs.'),
]

LESSONS: dict[str, dict[str, Any]] = {row[0]: dict(zip(('id', 'title', 'notes', 'practice', 'question', 'options', 'answer', 'explanation'), row)) for row in _LESSONS}


class MentorStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get('JARVIS_MENTOR_DB') or Path.home() / '.jarvis' / 'mentor.db')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mentor_plan (
                    lesson_id TEXT PRIMARY KEY, scheduled_date TEXT NOT NULL,
                    minutes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mentor_answers (
                    lesson_id TEXT PRIMARY KEY, choice INTEGER NOT NULL,
                    correct INTEGER NOT NULL, attempts INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def lesson(lesson_id: str):
        if lesson_id not in LESSONS:
            raise ValueError('Unknown lesson. Use mentor_catalog to list lesson IDs.')
        row = LESSONS[lesson_id]
        return {key: row[key] for key in ('id', 'title', 'notes', 'practice')}

    @staticmethod
    def catalog():
        return [{'id': row['id'], 'title': row['title']} for row in LESSONS.values()]

    @staticmethod
    def quiz(lesson_id: str):
        MentorStore.lesson(lesson_id)
        row = LESSONS[lesson_id]
        return {'lesson_id': lesson_id, 'question': row['question'],
                'options': [{'choice': i, 'text': text} for i, text in enumerate(row['options'])],
                'grading': 'Objective starter checkpoint only; not a coding or mastery assessment.'}

    def plan(self, lesson_ids: list[str], start_date: str, minutes: int = 30):
        if not lesson_ids or len(lesson_ids) != len(set(lesson_ids)):
            raise ValueError('Choose a non-empty list of unique lesson IDs.')
        if type(minutes) is not int or not 10 <= minutes <= 120:
            raise ValueError('Daily study time must be an integer from 10 to 120 minutes.')
        start = date.fromisoformat(start_date)
        for key in lesson_ids:
            self.lesson(key)
        rows = [(key, (start + timedelta(days=i)).isoformat(), minutes) for i, key in enumerate(lesson_ids)]
        with self.connect() as db:
            for row in rows:
                db.execute('INSERT INTO mentor_plan VALUES (?, ?, ?) ON CONFLICT(lesson_id) DO UPDATE SET scheduled_date=excluded.scheduled_date, minutes=excluded.minutes', row)
        return {'sessions': [{'lesson_id': key, 'date': day, 'minutes': duration} for key, day, duration in rows],
                'notice': 'Local study plan only. No calendar events or notifications were created.'}

    def submit(self, lesson_id: str, choice: int):
        self.lesson(lesson_id)
        row = LESSONS[lesson_id]
        if type(choice) is not int or not 0 <= choice < len(row['options']):
            raise ValueError('Submit one of the integer choice numbers shown in mentor_quiz.')
        correct = choice == row['answer']
        with self.connect() as db:
            db.execute('INSERT INTO mentor_answers(lesson_id, choice, correct, attempts) VALUES (?, ?, ?, 1) ON CONFLICT(lesson_id) DO UPDATE SET choice=excluded.choice, correct=excluded.correct, attempts=attempts+1, updated_at=CURRENT_TIMESTAMP', (lesson_id, choice, int(correct)))
        return {'lesson_id': lesson_id, 'correct': correct, 'correct_choice': row['answer'],
                'feedback': row['explanation'], 'next': 'Try the practice task and explain your reasoning. A passed checkpoint is not mastery.'}

    def progress(self, as_of: str | None = None):
        today = date.fromisoformat(as_of) if as_of else date.today()
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            answers = [dict(row) for row in db.execute('SELECT * FROM mentor_answers ORDER BY lesson_id')]
            sessions = [dict(row) for row in db.execute('SELECT * FROM mentor_plan ORDER BY scheduled_date, lesson_id')]
        passed = {row['lesson_id'] for row in answers if row['correct']}
        return {'attempted_checkpoints': len(answers), 'passed_checkpoints': len(passed),
                'starter_topics': len(LESSONS), 'weak_areas': [row['lesson_id'] for row in answers if not row['correct']],
                'answers': answers, 'sessions': sessions,
                'overdue': [row for row in sessions if row['scheduled_date'] < today.isoformat() and row['lesson_id'] not in passed],
                'notice': 'Latest checkpoint result per topic, not course completion or skill certification.'}


def register_mentor_tools(registry):
    from jarvis.tools.registry import Risk, Tool

    def invoke(method, **kwargs):
        value = getattr(MentorStore(), method)(**kwargs)
        return {'success': True, 'data': value}

    definitions = [
        ('mentor_catalog', 'List twelve offline starter learning domains and lesson IDs.', {}, [], 'catalog', Risk.SAFE),
        ('mentor_lesson', 'Read starter lesson notes and a safe manual practice task; never executes commands.', {'lesson_id': {'type': 'string'}}, ['lesson_id'], 'lesson', Risk.SAFE),
        ('mentor_quiz', 'Show an objective multiple-choice starter checkpoint. Submit an integer choice with mentor_submit.', {'lesson_id': {'type': 'string'}}, ['lesson_id'], 'quiz', Risk.SAFE),
        ('mentor_submit', 'Record a checkpoint choice and receive rubric feedback. Does not grade code or certify mastery.', {'lesson_id': {'type': 'string'}, 'choice': {'type': 'integer'}}, ['lesson_id', 'choice'], 'submit', Risk.LOW),
        ('mentor_plan', 'Save or update a local study plan, one topic per day. Creates no calendar events or notifications.', {'lesson_ids': {'type': 'array', 'items': {'type': 'string'}}, 'start_date': {'type': 'string', 'description': 'User-chosen YYYY-MM-DD local start date'}, 'minutes': {'type': 'integer'}}, ['lesson_ids', 'start_date'], 'plan', Risk.LOW),
        ('mentor_progress', 'Review persisted checkpoints, weak areas and overdue study sessions.', {'as_of': {'type': 'string', 'description': 'Optional YYYY-MM-DD local review date'}}, [], 'progress', Risk.SAFE),
    ]
    def make_handler(method):
        def handler(**kwargs):
            return invoke(method, **kwargs)
        return handler

    for name, description, properties, required, method, risk in definitions:
        registry.register(Tool(name=name, description=description,
                               parameters={'type': 'object', 'properties': properties, 'required': required},
                               handler=make_handler(method), risk=risk, category='mentor'))
