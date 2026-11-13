"""Local execution safety: scoped approvals, emergency stop and redacted audit.

This module never grants an approval to a model. Decisions come only from the
existing trusted confirmation callback. Approval records contain hashes, not
argument values, and are single-use even under concurrent execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class SecurityStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get('JARVIS_SECURITY_DB') or Path.home() / '.jarvis' / 'security.db')
        if self.path == ':memory:':
            raise ValueError('Use a temporary file for isolated security stores.')
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # New databases should be private on POSIX; Windows inherits user ACLs.
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS execution_approvals (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    expires REAL NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_audit (
                    id INTEGER PRIMARY KEY, ts REAL NOT NULL,
                    tool TEXT NOT NULL, outcome TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_settings (
                    key TEXT PRIMARY KEY, value INTEGER NOT NULL
                );
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def scope(tool: str, args: dict[str, Any], task: str) -> str:
        value = json.dumps([tool, args, task], sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(value.encode()).hexdigest()

    def request(self, tool: str, args: dict[str, Any], task: str, ttl: float = 120) -> str:
        if not task or not tool or not 0 < ttl <= 3600:
            raise ValueError('Tool, task and TTL (0, 3600] are required.')
        scope = self.scope(tool, args, task)
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO execution_approvals VALUES (?, ?, ?, ?)',
                       (key, scope, time.time() + ttl, 'pending'))
        return key

    def decide(self, key: str, approved: bool):
        with self.connect() as db:
            changed = db.execute(
                'UPDATE execution_approvals SET state=? WHERE id=? AND state=? AND expires>?',
                ('approved' if approved else 'rejected', key, 'pending', time.time())).rowcount
        if changed != 1:
            raise ValueError('Approval is missing, expired or already decided.')

    def consume(self, key: str, tool: str, args: dict[str, Any], task: str):
        scope = self.scope(tool, args, task)
        with self.connect() as db:
            changed = db.execute(
                'UPDATE execution_approvals SET state=? WHERE id=? AND scope=? AND state=? AND expires>?',
                ('consumed', key, scope, 'approved', time.time())).rowcount
        if changed != 1:
            raise ValueError('Approval is expired, replayed, undecided or scope-mismatched.')

    def set_stop(self, enabled: bool):
        with self.connect() as db:
            db.execute('INSERT INTO execution_settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       ('emergency_stop', int(enabled)))
        self.audit('emergency_stop', 'enabled' if enabled else 'disabled')

    def stopped(self) -> bool:
        with self.connect() as db:
            row = db.execute('SELECT value FROM execution_settings WHERE key=?', ('emergency_stop',)).fetchone()
        return bool(row and row[0])

    def audit(self, tool: str, outcome: str):
        # Deliberately omit arguments, results, exception strings and credentials.
        with self.connect() as db:
            db.execute('INSERT INTO execution_audit(ts, tool, outcome) VALUES (?, ?, ?)',
                       (time.time(), tool, outcome))

    def events(self, limit: int = 50):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM execution_audit ORDER BY id DESC LIMIT ?',
                                                    (max(1, min(limit, 500)),))]


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Local JARVIS execution safety controls')
    parser.add_argument('action', choices=['status', 'stop', 'resume', 'audit'])
    args = parser.parse_args()
    store = SecurityStore()
    if args.action in ('stop', 'resume'):
        store.set_stop(args.action == 'stop')
    print(json.dumps(store.events() if args.action == 'audit' else {'emergency_stop': store.stopped()}))


if __name__ == '__main__':
    main()
