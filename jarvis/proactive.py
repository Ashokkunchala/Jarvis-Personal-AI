"""Opt-in local resource alerts and backend-driven daily briefings.

No remote messages, push notifications, cleanup or other remediation actions.
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
from pathlib import Path


class ProactiveStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get('JARVIS_PROACTIVE_DB') or Path.home() / '.jarvis' / 'proactive.db')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS alert_rules (
                    metric TEXT PRIMARY KEY, threshold REAL NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS resource_alerts (
                    id INTEGER PRIMARY KEY, created REAL NOT NULL, metric TEXT NOT NULL,
                    value REAL NOT NULL, threshold REAL NOT NULL, state TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def configure(self, metric: str, threshold: float, enabled: bool = False):
        if metric not in ('cpu', 'memory', 'disk', 'battery'):
            raise ValueError('Metric must be cpu, memory, disk or battery.')
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 1 <= threshold <= 100:
            raise ValueError('Threshold must be a finite percentage from 1 to 100.')
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean.')
        with self.connect() as db:
            db.execute('INSERT INTO alert_rules(metric,threshold,enabled) VALUES (?,?,?) ON CONFLICT(metric) DO UPDATE SET threshold=excluded.threshold,enabled=excluded.enabled,active=0', (metric, threshold, int(enabled)))
        return {'metric': metric, 'threshold': threshold, 'enabled': enabled,
                'notice': 'Local alerts while the backend is running, roughly once a minute. Battery alerts below threshold; other metrics at or above. No desktop or phone notification delivery.'}

    def rules(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM alert_rules ORDER BY metric')]

    def evaluate(self, samples: dict[str, float], now: float | None = None):
        """Atomically record crossings, not repeats. Missing metrics stay unknown."""
        now = time.time() if now is None else now
        events = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for rule in db.execute('SELECT * FROM alert_rules WHERE enabled=1').fetchall():
                value = samples.get(rule['metric'])
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 100:
                    continue
                threshold = rule['threshold']
                triggered = value < threshold if rule['metric'] == 'battery' else value >= threshold
                # Two percentage points of hysteresis reduce repeated boundary noise.
                recovered = value >= min(100, threshold + 2) if rule['metric'] == 'battery' else value <= max(0, threshold - 2)
                if not rule['active'] and triggered:
                    state, active = 'triggered', 1
                elif rule['active'] and recovered:
                    state, active = 'recovered', 0
                else:
                    continue
                db.execute('UPDATE alert_rules SET active=? WHERE metric=?', (active, rule['metric']))
                db.execute('INSERT INTO resource_alerts(created,metric,value,threshold,state) VALUES (?,?,?,?,?)', (now, rule['metric'], value, threshold, state))
                events.append({'metric': rule['metric'], 'value': value, 'threshold': threshold, 'state': state})
            db.execute('DELETE FROM resource_alerts WHERE id NOT IN (SELECT id FROM resource_alerts ORDER BY id DESC LIMIT 500)')
        return events

    def alerts(self, unacknowledged_only: bool = False):
        if type(unacknowledged_only) is not bool:
            raise ValueError('unacknowledged_only must be a boolean.')
        with self.connect() as db:
            query = 'SELECT * FROM resource_alerts'
            if unacknowledged_only:
                query += ' WHERE acknowledged=0'
            return [dict(row) for row in db.execute(query + ' ORDER BY id DESC LIMIT 100')]

    def acknowledge(self, alert_id: int):
        if type(alert_id) is not int or alert_id < 1:
            raise ValueError('Choose an integer alert ID from proactive_alerts.')
        with self.connect() as db:
            changed = db.execute('UPDATE resource_alerts SET acknowledged=1 WHERE id=?', (alert_id,)).rowcount
        if not changed:
            raise ValueError('No alert with that ID.')
        return {'acknowledged': alert_id}


def _sample_metrics(metrics):
    import psutil
    values = {}
    for metric in metrics:
        try:
            if metric == 'cpu':
                values[metric] = psutil.cpu_percent(interval=0.1)
            elif metric == 'memory':
                values[metric] = psutil.virtual_memory().percent
            elif metric == 'disk':
                values[metric] = psutil.disk_usage(Path.home().anchor or '/').percent
            elif metric == 'battery':
                battery = psutil.sensors_battery()
                if battery is not None and not battery.power_plugged:
                    values[metric] = battery.percent
        except (OSError, AttributeError, RuntimeError):
            continue
    return values


class ProactiveRunner:
    """A tick invoked by the existing backend scheduler, at most once a minute."""
    def __init__(self, sample_fn=_sample_metrics, clock=time.monotonic):
        self.sample_fn, self.clock = sample_fn, clock
        self.next_check = 0.0

    def tick(self):
        now = self.clock()
        if now < self.next_check:
            return
        self.next_check = now + 60
        # Do not create a resource database or inspect metrics until configured.
        path = Path(os.environ.get('JARVIS_PROACTIVE_DB') or Path.home() / '.jarvis' / 'proactive.db')
        if path.is_file():
            store = ProactiveStore(path)
            enabled = [row['metric'] for row in store.rules() if row['enabled']]
            if enabled:
                store.evaluate(self.sample_fn(enabled))
        # Existing saved briefing schedules are explicit opt-in. No job is added.
        from jarvis.briefing_schedule import BriefingScheduler
        from jarvis.personal import PersonalStore
        personal_path = Path.home() / '.jarvis' / 'personal.db'
        if personal_path.is_file():
            BriefingScheduler(store=PersonalStore(personal_path)).run_due()


def register_proactive_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    def handler_for(method):
        def handler(**kwargs):
            return {'success': True, 'data': getattr(ProactiveStore(), method)(**kwargs)}
        return handler
    definitions = [
        ('proactive_configure', 'Create or update a local resource alert rule. Disabled unless enabled=true. Checks roughly once a minute while backend runs. No message or OS notifications.', 'configure', Risk.LOW,
         {'metric': {'type': 'string', 'enum': ['cpu', 'memory', 'disk', 'battery']}, 'threshold': {'type': 'number'}, 'enabled': {'type': 'boolean'}}, ['metric', 'threshold']),
        ('proactive_rules', 'List saved resource alert rules and whether they are enabled.', 'rules', Risk.SAFE, {}, []),
        ('proactive_alerts', 'Read the local resource alert inbox, including recovery events. No push notification delivery.', 'alerts', Risk.SAFE, {'unacknowledged_only': {'type': 'boolean'}}, []),
        ('proactive_acknowledge', 'Mark a local resource alert reviewed by integer alert ID.', 'acknowledge', Risk.LOW, {'alert_id': {'type': 'integer'}}, ['alert_id']),
    ]
    for name, description, method, risk, properties, required in definitions:
        registry.register(Tool(name=name, description=description, parameters={'type': 'object', 'properties': properties, 'required': required}, handler=handler_for(method), risk=risk, category='proactive'))
