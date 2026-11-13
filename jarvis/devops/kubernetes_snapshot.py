"""Read-only triage of Kubernetes Pod JSON snapshots, with no cluster access."""
from __future__ import annotations

import re
from collections import Counter

from jarvis.devops.evidence import _list, _object, _read_export

SOURCE = 'https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/'
PHASES = {'Pending', 'Running', 'Succeeded', 'Failed', 'Unknown'}
CONDITIONS = {'Ready', 'ContainersReady', 'PodScheduled', 'Initialized', 'PodReadyToStartContainers'}
REASONS = {
    'CrashLoopBackOff': ('warning', 'Container restart backoff is active. This is not a root cause.',
                         'Review previous-container logs, termination details, probes and recent changes locally. Redact secrets before sharing.'),
    'ImagePullBackOff': ('warning', 'Container image pull is backing off.',
                         'Check image reference, registry reachability and image-pull credential configuration. Do not share credentials.'),
    'ErrImagePull': ('warning', 'Container image pull failed.',
                    'Check image reference, registry reachability and image-pull credential configuration. Do not share credentials.'),
    'CreateContainerConfigError': ('warning', 'Container configuration could not be prepared.',
                                  'Check referenced ConfigMaps, Secrets and volume configuration locally, without exposing their values.'),
    'OOMKilled': ('warning', 'Kubernetes reports an out-of-memory termination.',
                  'Check memory limits and usage history; exit code 137 alone does not prove an OOM kill.'),
    'Error': ('warning', 'Container termination reports Error.',
              'Review application logs and termination details locally; the snapshot does not establish root cause.'),
    'Completed': ('info', 'Container completed.', 'Check whether completion is expected for this workload.'),
    'ContainerCreating': ('info', 'Container is still being created.',
                          'Check age and events locally before treating startup as an incident.'),
    'PodInitializing': ('info', 'Pod initialization is in progress.',
                        'Check init-container progress and events locally.'),
    'Evicted': ('warning', 'Pod reports eviction.', 'Review node pressure and eviction events locally.'),
    'Unschedulable': ('warning', 'Pod reports an unschedulable condition.',
                      'Review scheduling events, resource requests, placement constraints and node capacity locally.'),
}


def _name(value, fallback):
    # Never turn arbitrary messages, shell fragments or terminal controls into identifiers.
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,253}', value):
        return value
    return fallback


def _reason(value):
    # Reason fields are provider data too. Unknown values are not copied verbatim.
    return value if isinstance(value, str) and value in REASONS else None


def _integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f'{label} must be a non-negative integer.')
    return value


def review_pods(document, restart_threshold=3):
    """Summarize selected signals; never infer readiness merely from phase=Running."""
    if type(restart_threshold) is not int or not 1 <= restart_threshold <= 10000:
        raise ValueError('restart_threshold must be an integer from 1 to 10000.')
    doc = _object(document, 'Document')
    if doc.get('apiVersion') != 'v1':
        raise ValueError('Expected core Kubernetes apiVersion v1 Pod or PodList JSON.')
    if doc.get('kind') == 'Pod':
        items, partial = [doc], False
    elif doc.get('kind') in ('PodList', 'List'):
        items = _list(doc.get('items'), 'items')
        partial = bool(_object(doc.get('metadata', {}), 'List metadata').get('continue'))
    else:
        raise ValueError('Expected Pod, PodList or a List containing only Pods.')
    if len(items) > 500:
        raise ValueError('Review at most 500 Pods in one snapshot.')
    pods, counts = [], Counter()
    for pi, item in enumerate(items):
        pod = _object(item, 'Pod')
        if pod.get('kind') != 'Pod' or pod.get('apiVersion') != 'v1':
            raise ValueError('Every list item must be a core v1 Pod.')
        meta = _object(pod.get('metadata', {}), 'Pod metadata')
        status = _object(pod.get('status', {}), 'Pod status')
        raw_phase = status.get('phase')
        if raw_phase is not None and not isinstance(raw_phase, str):
            raise ValueError('Pod phase must be a string when present.')
        phase = raw_phase if raw_phase in PHASES else 'Unreported'
        counts[phase] += 1
        findings, containers = [], []
        terminating = bool(meta.get('deletionTimestamp'))
        terminal = phase in ('Succeeded', 'Failed')

        def add(code, severity, detail, check, **extra):
            findings.append(dict(code=code, severity=severity, detail=detail, next_check=check, **extra))

        if terminating:
            add('terminating', 'info', 'A deletion timestamp is present.',
                'Check deletion age and finalizers locally if termination is unexpectedly slow.')
        if phase in ('Pending', 'Unknown', 'Failed', 'Unreported'):
            add('phase_' + phase.lower(), 'warning' if phase == 'Failed' else 'review',
                f'Pod phase is {phase}.', 'Review lifecycle age and events locally; phase alone is not a diagnosis.')
        reason = _reason(status.get('reason'))
        if reason and reason != 'Completed':
            severity, detail, check = REASONS[reason]
            add(reason, severity, detail, check)
        conditions = {}
        for cond in _list(status.get('conditions', []), 'conditions'):
            _object(cond, 'Condition')
            key = cond.get('type')
            if not isinstance(key, str):
                raise ValueError('Condition type must be a string.')
            if key not in CONDITIONS:
                continue
            if key in conditions:
                raise ValueError('Duplicate Pod condition types are ambiguous.')
            value = cond.get('status')
            if value not in ('True', 'False', 'Unknown'):
                raise ValueError('Condition status must be True, False or Unknown strings.')
            conditions[key] = value
            if value != 'True' and not terminal and not terminating:
                add('condition_' + key, 'review', f'{key} is {value}.',
                    'Check condition transitions and related events locally. A startup transition may be normal.')
            reason = _reason(cond.get('reason'))
            if reason and value != 'True':
                severity, detail, check = REASONS[reason]
                add(reason, severity, detail, check)
        for field, role in [('initContainerStatuses', 'init'), ('containerStatuses', 'app'),
                            ('ephemeralContainerStatuses', 'ephemeral')]:
            names = set()
            for ci, container in enumerate(_list(status.get(field, []), field)):
                _object(container, 'Container status')
                name = _name(container.get('name'), f'{role}-{ci}')
                if name in names:
                    raise ValueError('Duplicate container status names are ambiguous.')
                names.add(name)
                restarts = _integer(container.get('restartCount', 0), 'restartCount')
                ready = container.get('ready')
                if ready is not None and type(ready) is not bool:
                    raise ValueError('Container ready must be a boolean when present.')
                states = {}
                for key in ('state', 'lastState'):
                    state = _object(container.get(key, {}), key)
                    present = [kind for kind in ('running', 'waiting', 'terminated') if kind in state]
                    if len(present) > 1:
                        raise ValueError('Container state must not contain multiple current states.')
                    states[key] = present[0] if present else 'unreported'
                    if not present:
                        continue
                    details = _object(state[present[0]], 'State details')
                    reason = _reason(details.get('reason'))
                    if reason and reason != 'Completed':
                        severity, detail, check = REASONS[reason]
                        add(reason, severity, detail, check, container=name, role=role,
                            evidence='current' if key == 'state' else 'previous_termination')
                    if present[0] == 'terminated' and 'exitCode' in details:
                        code = details['exitCode']
                        if type(code) is not int:
                            raise ValueError('exitCode must be an integer.')
                        if code != 0:
                            add('nonzero_exit', 'review', f'Container exit code is {code}.',
                                'Review termination reason and application logs locally. An exit code alone is not a root cause.',
                                container=name, role=role, evidence=key)
                if restarts >= restart_threshold:
                    add('restart_count', 'review', f'Cumulative restart count is {restarts}.',
                        'Compare timestamped snapshots to learn whether restarts are recent; this count is not a rate.',
                        container=name, role=role)
                if role == 'app' and ready is False and not terminal and not terminating:
                    add('container_not_ready', 'review', 'Application container reports ready=false.',
                        'Review readiness probe results and startup progress locally.', container=name, role=role)
                containers.append(dict(name=name, role=role, ready=ready, restarts=restarts,
                                       state=states['state'], previous_state=states['lastState']))
        pods.append(dict(namespace=_name(meta.get('namespace'), '(unreported)'),
                         name=_name(meta.get('name'), f'pod-{pi}'), phase=phase,
                         readiness=conditions.get('Ready', 'Unreported'), terminating=terminating,
                         conditions=conditions, containers=containers, findings=findings))
    return dict(pods_reviewed=len(pods), phase_counts=dict(counts), pods=pods,
                partial_list=partial, restart_threshold=restart_threshold, source=SOURCE,
                limits='Supplied snapshot only; freshness and completeness are not verified. Not live cluster health or root-cause analysis. Missing status remains unknown. No logs, messages, spec, environment, images, annotations or secret values returned. No commands, network calls, changes or remediation performed.')


def review_pods_export(path, restart_threshold=3):
    return review_pods(_read_export(path), restart_threshold)
