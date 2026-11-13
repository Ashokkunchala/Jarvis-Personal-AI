import asyncio
import json

import pytest

from jarvis.devops.kubernetes_snapshot import review_pods, review_pods_export
from jarvis.tools.builtin_tools import build_registry


def pod(phase='Running', **status):
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': 'api-1', 'namespace': 'apps'},
            'status': {'phase': phase, **status}}


def container(**kwargs):
    return dict(name='api', ready=False, restartCount=0, **kwargs)


def codes(result):
    return [f['code'] for p in result['pods'] for f in p['findings']]


def test_running_is_not_ready_without_evidence():
    result = review_pods(pod())
    assert result['pods'][0]['readiness'] == 'Unreported'
    result = review_pods(pod(conditions=[{'type': 'Ready', 'status': 'False'}]))
    assert 'condition_Ready' in codes(result)


def test_explicit_ready_and_no_false_healthy_claim():
    result = review_pods(pod(conditions=[{'type': 'Ready', 'status': 'True'}]))
    assert result['pods'][0]['readiness'] == 'True'
    assert 'healthy' not in result and 'freshness' in result['limits']


def test_current_crashloop_and_previous_oom_distinct():
    status = container(state={'waiting': {'reason': 'CrashLoopBackOff'}},
                       lastState={'terminated': {'reason': 'OOMKilled', 'exitCode': 137}})
    status['restartCount'] = 5
    result = review_pods(pod(containerStatuses=[status]))
    assert {'CrashLoopBackOff', 'OOMKilled', 'restart_count', 'nonzero_exit'} <= set(codes(result))
    findings = result['pods'][0]['findings']
    assert next(f for f in findings if f['code'] == 'OOMKilled')['evidence'] == 'previous_termination'
    assert 'not a root cause' in next(f for f in findings if f['code'] == 'CrashLoopBackOff')['detail']


def test_exit_137_is_not_automatically_oom():
    result = review_pods(pod(containerStatuses=[container(state={'terminated': {'exitCode': 137}})]))
    assert 'nonzero_exit' in codes(result) and 'OOMKilled' not in codes(result)


@pytest.mark.parametrize('reason', ['ImagePullBackOff', 'ErrImagePull', 'CreateContainerConfigError'])
def test_known_waiting_signals(reason):
    result = review_pods(pod(containerStatuses=[container(state={'waiting': {'reason': reason}})]))
    assert reason in codes(result)


def test_init_and_ephemeral_statuses_are_reviewed():
    status = container(state={'waiting': {'reason': 'CrashLoopBackOff'}})
    result = review_pods(pod(initContainerStatuses=[status], ephemeralContainerStatuses=[status]))
    assert {c['role'] for c in result['pods'][0]['containers']} == {'init', 'ephemeral'}
    assert 'container_not_ready' not in codes(result)


def test_completed_pod_and_init_are_not_readiness_failures():
    result = review_pods(pod('Succeeded', conditions=[{'type': 'Ready', 'status': 'False'}],
                            containerStatuses=[container(state={'terminated': {'reason': 'Completed', 'exitCode': 0}})]))
    assert not codes(result)
    result = review_pods(pod(initContainerStatuses=[container(state={'terminated': {'reason': 'Completed', 'exitCode': 0}})]))
    assert 'container_not_ready' not in codes(result)


def test_terminating_is_not_failure():
    doc = pod(conditions=[{'type': 'Ready', 'status': 'False'}], containerStatuses=[container()])
    doc['metadata']['deletionTimestamp'] = '2026-11-13T12:00:00Z'
    assert codes(review_pods(doc)) == ['terminating']


def test_pending_failed_evicted_and_unschedulable():
    result = review_pods(pod('Pending', conditions=[{'type': 'PodScheduled', 'status': 'False', 'reason': 'Unschedulable'}]))
    assert {'phase_pending', 'Unschedulable'} <= set(codes(result))
    assert {'phase_failed', 'Evicted'} <= set(codes(review_pods(pod('Failed', reason='Evicted'))))


def test_list_empty_and_paginated():
    result = review_pods({'apiVersion': 'v1', 'kind': 'PodList', 'metadata': {'continue': 'TOKEN'}, 'items': [pod(), pod('Pending')]})
    assert result['partial_list'] and result['phase_counts'] == {'Running': 1, 'Pending': 1}
    assert 'TOKEN' not in json.dumps(result)
    assert review_pods({'apiVersion': 'v1', 'kind': 'List', 'items': []})['pods_reviewed'] == 0


def test_does_not_echo_arbitrary_messages_specs_or_reasons():
    doc = pod(reason='SECRET', containerStatuses=[container(state={'waiting': {'reason': 'SECRET', 'message': 'SECRET'}})])
    doc['spec'] = {'env': [{'value': 'SECRET'}], 'image': 'SECRET'}
    doc['metadata'].update(annotations={'x': 'SECRET'}, name='SECRET; echo password')
    doc['status']['message'] = 'SECRET'
    assert 'SECRET' not in json.dumps(review_pods(doc))


@pytest.mark.parametrize('doc', [{}, {'apiVersion': 'v1', 'kind': 'Secret'}, {'apiVersion': 'v2', 'kind': 'Pod'},
                                {'apiVersion': 'v1', 'kind': 'List', 'items': [{'apiVersion': 'v1', 'kind': 'Node'}]},
                                {'apiVersion': 'v1', 'kind': 'PodList', 'items': [pod()] * 501}])
def test_wrong_export_and_scope_rejected(doc):
    with pytest.raises(ValueError):
        review_pods(doc)


@pytest.mark.parametrize('kwargs', [dict(restartCount=-1), dict(restartCount=True), dict(ready='false'),
                                  dict(state={'running': {}, 'waiting': {}}), dict(state={'terminated': {'exitCode': '137'}})])
def test_malformed_container_rejected(kwargs):
    status = container()
    status.update(kwargs)
    with pytest.raises(ValueError):
        review_pods(pod(containerStatuses=[status]))


@pytest.mark.parametrize('threshold', [0, -1, True, 1.5, 10001])
def test_bad_threshold_rejected(threshold):
    with pytest.raises(ValueError):
        review_pods(pod(), threshold)


def test_restart_threshold_is_cumulative_and_configurable():
    status = container()
    status['restartCount'] = 2
    assert 'restart_count' not in codes(review_pods(pod(containerStatuses=[status])))
    assert 'restart_count' in codes(review_pods(pod(containerStatuses=[status]), 2))


def test_ambiguous_duplicates_rejected():
    with pytest.raises(ValueError):
        review_pods(pod(containerStatuses=[container(), container()]))
    with pytest.raises(ValueError):
        review_pods(pod(conditions=[{'type': 'Ready', 'status': 'True'}] * 2))


def test_registry_reads_only_the_supplied_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    export = tmp_path / 'pods.json'
    export.write_text(json.dumps(pod()))
    result = asyncio.run(build_registry(force=True).execute('review_kubernetes_pods', {'path': str(export)}))
    assert result.ok and result.data['pods_reviewed'] == 1
    assert review_pods_export(str(export))['pods_reviewed'] == 1
    export.write_text('invalid')
    with pytest.raises(ValueError):
        review_pods_export(str(export))


@pytest.mark.parametrize('status', [{'phase': []}, {'conditions': [{'type': []}]}, {'conditions': [{'type': 'Ready', 'status': True}]}])
def test_wrong_status_types_rejected(status):
    with pytest.raises(ValueError):
        review_pods(pod(**status))
