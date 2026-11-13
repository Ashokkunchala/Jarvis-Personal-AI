"""Adversarial tests for the shared execution boundary, without devices/cloud."""
import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from jarvis.security import SecurityStore
from jarvis.tools.registry import Risk, ToolRegistry


@pytest.fixture
def store(tmp_path):
    return SecurityStore(tmp_path / 'security.db')


def test_one_time_scope_and_task_binding(store):
    key = store.request('apply', {'workspace': 'dev'}, 'task1')
    store.decide(key, True)
    for tool, args, task in [('apply', {'workspace': 'prod'}, 'task1'), ('delete', {'workspace': 'dev'}, 'task1'), ('apply', {'workspace': 'dev'}, 'task2')]:
        with pytest.raises(ValueError):
            store.consume(key, tool, args, task)
    store.consume(key, 'apply', {'workspace': 'dev'}, 'task1')
    with pytest.raises(ValueError):
        store.consume(key, 'apply', {'workspace': 'dev'}, 'task1')


def test_expiry_after_approval(store):
    with patch('jarvis.security.time.time', return_value=1000):
        key = store.request('apply', {}, 'task', ttl=1)
        store.decide(key, True)
    with patch('jarvis.security.time.time', return_value=1002), pytest.raises(ValueError):
        store.consume(key, 'apply', {}, 'task')


def test_concurrent_consume_only_one_wins(store):
    key = store.request('apply', {}, 'task')
    store.decide(key, True)
    def consume(_):
        try:
            store.consume(key, 'apply', {}, 'task')
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(8))) == 1


def test_unknown_rejected_and_undecided(store):
    for decision in (None, False):
        key = store.request('apply', {}, 'task')
        if decision is False:
            store.decide(key, False)
        with pytest.raises(ValueError):
            store.consume(key, 'apply', {}, 'task')
    with pytest.raises(ValueError):
        store.decide('missing', True)


def registry_for(store, risk=Risk.HIGH):
    registry = ToolRegistry()
    registry.security_store = store
    calls = []
    registry.tool('operation', 'test operation', {}, risk=risk, requires_confirmation=risk >= Risk.MEDIUM)(lambda **args: calls.append(args) or {'success': True})
    return registry, calls


def test_global_auto_approval_cannot_bypass(store):
    registry, calls = registry_for(store)
    result = asyncio.run(registry.execute('operation', {}, auto_approve=True))
    assert not result.ok and not calls


def test_stop_blocks_mutation_but_allows_reads(store):
    store.set_stop(True)
    for risk in (Risk.SAFE, Risk.LOW):
        registry, calls = registry_for(store, risk)
        result = asyncio.run(registry.execute('operation', {}))
        assert result.ok == (risk == Risk.SAFE)
        assert bool(calls) == (risk == Risk.SAFE)


def test_stop_during_approval_blocks_write(store):
    registry, calls = registry_for(store)
    async def confirm(tool, args):
        store.set_stop(True)
        return True
    assert not asyncio.run(registry.execute('operation', {}, confirm=confirm)).ok
    assert not calls


def test_callback_cannot_replace_approved_args(store):
    registry, calls = registry_for(store)
    async def confirm(tool, args):
        args['nested']['workspace'] = 'prod'
        return True
    result = asyncio.run(registry.execute('operation', {'nested': {'workspace': 'dev'}}, confirm=confirm))
    assert result.ok and calls == [{'nested': {'workspace': 'dev'}}]


def test_reject_prevents_execution(store):
    registry, calls = registry_for(store)
    async def confirm(tool, args):
        return False
    assert not asyncio.run(registry.execute('operation', {}, confirm=confirm)).ok
    assert not calls


def test_audit_does_not_persist_arguments(store):
    registry, calls = registry_for(store, Risk.LOW)
    assert asyncio.run(registry.execute('operation', {'password': 'do-not-store-me'})).ok
    assert [event['outcome'] for event in store.events()][::-1] == ['started', 'succeeded']
    with sqlite3.connect(store.path) as db:
        assert 'do-not-store-me' not in str(list(db.iterdump()))


def test_store_failure_fails_closed(tmp_path):
    registry, calls = registry_for(SecurityStore(tmp_path / 'safety.db'), Risk.LOW)
    with patch.object(registry.security_store, 'stopped', side_effect=OSError('disk unavailable')):
        assert not asyncio.run(registry.execute('operation', {})).ok
    assert not calls


def test_medium_cannot_omit_confirmation_flag(store):
    registry, calls = registry_for(store, Risk.MEDIUM)
    registry.get('operation').requires_confirmation = False
    assert not asyncio.run(registry.execute('operation', {}, auto_approve=True)).ok
    assert not calls


def test_truthy_string_is_not_approval(store):
    registry, calls = registry_for(store)
    async def confirm(tool, args):
        return 'false'
    assert not asyncio.run(registry.execute('operation', {}, confirm=confirm)).ok
    assert not calls


def test_audit_failure_after_execution_does_not_report_retryable_failure(store):
    registry, calls = registry_for(store, Risk.LOW)
    original = store.audit
    def audit(tool, outcome):
        if outcome == 'succeeded':
            raise OSError('disk full')
        original(tool, outcome)
    with patch.object(store, 'audit', side_effect=audit):
        assert asyncio.run(registry.execute('operation', {})).ok
    assert calls == [{}]


def test_decision_cannot_be_overwritten(store):
    key = store.request('apply', {}, 'task')
    store.decide(key, False)
    with pytest.raises(ValueError):
        store.decide(key, True)
