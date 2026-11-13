import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from jarvis.proactive import ProactiveRunner, ProactiveStore


@pytest.fixture
def store(tmp_path):
    return ProactiveStore(tmp_path / 'proactive.db')


def test_disabled_by_default_and_no_sampling_before_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_PROACTIVE_DB', str(tmp_path / 'proactive.db'))
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    runner = ProactiveRunner(sample_fn=lambda _: pytest.fail('Not opted in'))
    runner.tick()
    assert not (tmp_path / 'proactive.db').exists()
    store = ProactiveStore(tmp_path / 'proactive.db')
    assert not store.configure('cpu', 90)['enabled']
    assert store.evaluate({'cpu': 99}) == []


def test_crossings_hysteresis_recovery_and_rearm(store):
    store.configure('cpu', 90, True)
    assert store.evaluate({'cpu': 95})[0]['state'] == 'triggered'
    assert store.evaluate({'cpu': 94}) == []
    assert store.evaluate({'cpu': 89}) == []
    assert store.evaluate({'cpu': 88})[0]['state'] == 'recovered'
    assert store.evaluate({'cpu': 91})[0]['state'] == 'triggered'
    assert len(store.alerts()) == 3
    store.acknowledge(store.alerts()[0]['id'])
    assert len(store.alerts(True)) == 2
    assert len(ProactiveStore(store.path).alerts()) == 3


def test_battery_low_and_unknown_sensor(store):
    store.configure('battery', 20, True)
    assert store.evaluate({'battery': 20}) == []
    assert store.evaluate({'battery': 19})[0]['state'] == 'triggered'
    assert store.evaluate({}) == []
    assert store.evaluate({'battery': 21}) == []
    assert store.evaluate({'battery': 22})[0]['state'] == 'recovered'


@pytest.mark.parametrize('value', [-1, 101, float('nan'), float('inf'), True, '99', None])
def test_invalid_sensor_does_not_trigger_or_recover(store, value):
    store.configure('memory', 90, True)
    assert store.evaluate({'memory': value}) == []
    assert not store.alerts()


def test_concurrent_checks_deduplicate_crossing(store):
    store.configure('disk', 95, True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda _: store.evaluate({'disk': 99}), range(6)))
    assert sum(len(items) for items in outcomes) == 1


@pytest.mark.parametrize('metric,threshold,enabled', [('bad', 80, True), ('cpu', 0, True), ('cpu', float('nan'), True), ('cpu', True, True), ('cpu', 90, 'false')])
def test_invalid_rules_rejected(store, metric, threshold, enabled):
    with pytest.raises(ValueError):
        store.configure(metric, threshold, enabled)


def test_disable_and_history_bound(store):
    store.configure('cpu', 90, True)
    for _ in range(260):
        store.evaluate({'cpu': 99})
        store.evaluate({'cpu': 10})
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM resource_alerts').fetchone()[0] == 500
    store.configure('cpu', 90, False)
    assert store.evaluate({'cpu': 99}) == []
    with pytest.raises(ValueError):
        store.acknowledge(9999)


def test_runner_cadence_and_real_saved_briefing(tmp_path, monkeypatch):
    from jarvis.briefing_schedule import BriefingScheduler
    from jarvis.personal import PersonalStore
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    monkeypatch.setenv('JARVIS_PROACTIVE_DB', str(tmp_path / 'proactive.db'))
    store = ProactiveStore(tmp_path / 'proactive.db')
    store.configure('memory', 90, True)
    personal = PersonalStore()
    briefing = BriefingScheduler(store=personal)
    morning = datetime(2026, 11, 13, 0, tzinfo=UTC)
    monkeypatch.setattr('jarvis.briefing_schedule._utcnow', lambda: morning)
    briefing.set_daily('test', '07:00', 'UTC')
    monkeypatch.setattr('jarvis.briefing_schedule._utcnow', lambda: morning.replace(hour=8))
    clock, calls = [0], []
    runner = ProactiveRunner(sample_fn=lambda metrics: calls.append(metrics) or {'memory': 99}, clock=lambda: clock[0])
    runner.tick()
    assert len(briefing.history()) == 1
    assert len(store.alerts()) == 1
    runner.tick()
    assert len(calls) == 1
    clock[0] = 60
    runner.tick()
    assert len(calls) == 2 and len(briefing.history()) == 1


@pytest.mark.asyncio
async def test_existing_scheduler_invokes_proactive_tick_and_survives_failure(tmp_path, monkeypatch):
    from app.scheduler import ScheduleRunner
    monkeypatch.setenv('JARVIS_DB_PATH', str(tmp_path / 'backend.db'))
    runner = ScheduleRunner(poll_seconds=0.25)
    called = []
    def tick():
        called.append(True)
        raise OSError('unavailable sensor')
    monkeypatch.setattr(runner.proactive, 'tick', tick)
    await runner.start()
    await asyncio.sleep(0.55)
    await runner.stop()
    assert len(called) >= 2


def test_tools_are_executable_and_stop_blocks_config(tmp_path, monkeypatch):
    from jarvis.security import SecurityStore
    from jarvis.tools.builtin_tools import build_registry
    monkeypatch.setenv('JARVIS_PROACTIVE_DB', str(tmp_path / 'proactive.db'))
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    registry = build_registry(force=True)
    assert len(registry.names('proactive')) == 4
    assert asyncio.run(registry.execute('proactive_configure', {'metric': 'cpu', 'threshold': 90})).ok
    assert asyncio.run(registry.execute('proactive_rules')).data['data'][0]['enabled'] == 0
    SecurityStore().set_stop(True)
    assert not asyncio.run(registry.execute('proactive_configure', {'metric': 'cpu', 'threshold': 90, 'enabled': True})).ok
    assert asyncio.run(registry.execute('proactive_alerts')).ok
