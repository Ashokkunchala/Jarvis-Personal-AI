"""Offline reviews of supplied cloud evidence. No SDK, subprocess or network calls."""
from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object.')
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise ValueError(f'{label} must be an array.')
    return value


def review_security_groups(document: dict[str, Any]):
    groups = _list(_object(document, 'Document').get('SecurityGroups'), 'SecurityGroups')
    findings = []
    reviewed = 0
    for gi, group in enumerate(groups):
        _object(group, 'Security group')
        identity = str(group.get('GroupId', f'group[{gi}]'))
        for ri, rule in enumerate(_list(group.get('IpPermissions', []), 'IpPermissions')):
            _object(rule, 'Ingress rule')
            reviewed += 1
            protocol = str(rule.get('IpProtocol', '')).lower()
            if not protocol:
                raise ValueError('Ingress rule requires IpProtocol.')
            public = []
            for field, key, version in [('IpRanges', 'CidrIp', 4), ('Ipv6Ranges', 'CidrIpv6', 6)]:
                for entry in _list(rule.get(field, []), field):
                    _object(entry, 'IP range')
                    try:
                        network = ipaddress.ip_network(entry[key], strict=False)
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError('Invalid ingress CIDR.') from exc
                    if network.version != version:
                        raise ValueError('CIDR family does not match its range field.')
                    if network.prefixlen == 0:
                        public.append(str(network))
            if protocol in ('tcp', 'udp', '6', '17'):
                start, end = rule.get('FromPort'), rule.get('ToPort')
                if type(start) is not int or type(end) is not int or not 0 <= start <= end <= 65535:
                    raise ValueError('TCP/UDP rules require an ordered port range from 0 to 65535.')
            else:
                start, end = None, None
            if not public:
                continue
            if protocol == '-1':
                severity, issue = 'high', 'Explicit world ingress permits all protocols.'
            elif protocol in ('tcp', '6') and any(start <= p <= end for p in (22, 3389)):
                severity, issue = 'high', 'Explicit world TCP ingress includes SSH or RDP.'
            elif protocol in ('tcp', 'udp', '6', '17') and end - start >= 1000:
                severity, issue = 'medium', 'Explicit world ingress includes a broad port range.'
            else:
                severity, issue = 'review', 'Explicit world ingress; confirm that public access is intended.'
            findings.append({'group': identity, 'rule_index': ri, 'severity': severity,
                             'issue': issue, 'protocol': protocol, 'from_port': start,
                             'to_port': end, 'sources': public})
    return {'groups_reviewed': len(groups), 'ingress_rules_reviewed': reviewed, 'findings': findings,
            'limits': 'Checks explicit /0 ingress only, not equivalent combinations of ranges, prefix lists, referenced groups, routing, NACLs or actual reachability. No changes made.'}


def review_terraform_plan(document: dict[str, Any]):
    doc = _object(document, 'Plan')
    if not str(doc.get('format_version', '')).startswith('1.'):
        raise ValueError('Expected Terraform plan JSON format_version 1.x, not state or raw HCL.')
    if 'resource_changes' not in doc and 'planned_values' not in doc:
        raise ValueError('No plan fields found. Supply a terraform show -json plan document.')
    known = {'no-op', 'create', 'read', 'update', 'delete', 'forget'}
    counts: Counter[str] = Counter()
    changes, warnings = [], []
    for resource in _list(doc.get('resource_changes', []), 'resource_changes'):
        _object(resource, 'Resource change')
        change = _object(resource.get('change'), 'change')
        actions = _list(change.get('actions'), 'actions')
        if not actions or any(not isinstance(action, str) for action in actions):
            raise ValueError('Each change requires a non-empty list of action names.')
        counts.update(actions)
        unknown = sorted(set(actions) - known)
        if unknown:
            warnings.append('Unknown action types: ' + ', '.join(unknown))
        address = str(resource.get('address', '(address missing)'))
        changes.append({'address': address, 'actions': actions,
                        'replacement': 'create' in actions and ('delete' in actions or 'forget' in actions),
                        'destructive': 'delete' in actions,
                        'state_removal': 'forget' in actions})
    if doc.get('errored') is True:
        warnings.append('Terraform marked this plan errored.')
    if doc.get('complete') is False:
        warnings.append('Terraform marked this plan incomplete; further planning may be required.')
    return {'resources_reviewed': len(changes), 'action_counts': dict(counts), 'changes': changes,
            'deletions': sum(row['destructive'] for row in changes),
            'replacements': sum(row['replacement'] for row in changes), 'warnings': warnings,
            'limits': 'Summary of supplied plan only, not an apply approval or security audit. Before/after values, outputs, variables and imports are omitted to avoid exposing sensitive payloads. No Terraform command executed.'}


def _decimal(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite non-negative number.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label} must be numeric.') from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f'{label} must be a finite non-negative number.')
    return result


def analyze_daily_costs(daily: list[dict], currency: str, complete_days: bool,
                        increase_percent: float = 50, minimum_increase: float = 5):
    if complete_days is not True:
        raise ValueError('Use complete daily totals only; partial-day comparisons are misleading.')
    if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
        raise ValueError('Specify one uppercase three-letter currency for every row.')
    series = []
    for row in _list(daily, 'daily'):
        _object(row, 'Daily cost')
        series.append((date.fromisoformat(row['date']), _decimal(row['amount'], 'Daily amount')))
    series.sort()
    if not 4 <= len(series) <= 367:
        raise ValueError('Supply 4-367 consecutive daily totals, at least 3 baseline days.')
    if any(b[0] != a[0] + timedelta(days=1) for a, b in zip(series, series[1:])):
        raise ValueError('Daily totals must have unique consecutive dates; include explicit zero-cost days.')
    threshold = _decimal(increase_percent, 'Percentage threshold')
    minimum = _decimal(minimum_increase, 'Minimum increase')
    baseline_rows = series[:-1][-7:]
    baseline = sum((amount for _, amount in baseline_rows), Decimal(0)) / len(baseline_rows)
    latest_day, latest = series[-1]
    delta = latest - baseline
    percent = (delta / baseline * 100) if baseline else None
    flagged = delta > 0 and delta >= minimum and (baseline == 0 or percent >= threshold)
    return {'currency': currency, 'latest_date': latest_day.isoformat(), 'latest_amount': str(latest),
            'baseline_days': len(baseline_rows), 'baseline_daily_average': str(baseline),
            'increase_amount': str(delta), 'increase_percent': str(percent) if percent is not None else None,
            'threshold_flag': bool(flagged),
            'limits': 'Simple user-threshold comparison with up to 7 prior days, not AWS machine-learning anomaly detection, a forecast, root-cause analysis or a final bill. Supplied totals only; no AWS access or alerts.'}


def _read_export(path: str):
    source = Path(path)
    if source.suffix.lower() != '.json' or not source.is_file():
        raise ValueError('Choose an existing local .json export file.')
    with source.open('rb') as stream:
        payload = stream.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError('Export exceeds the 2 MB review limit. Supply a smaller scoped export.')
    try:
        return _object(json.loads(payload.decode('utf-8-sig')), 'Export')
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Export must be valid UTF-8 JSON.') from exc


def review_security_groups_export(path: str):
    return review_security_groups(_read_export(path))


def review_terraform_plan_export(path: str):
    return review_terraform_plan(_read_export(path))


def register_evidence_tools(registry):
    from jarvis.devops.dependency_audit import register_audit_tools
    from jarvis.devops.kubernetes_snapshot import review_pods_export
    from jarvis.devops.slo import register_slo_tools

    register_slo_tools(registry)
    register_audit_tools(registry)
    from jarvis.tools.registry import Risk, Tool

    definitions = [
        ('review_kubernetes_pods', 'Review a local Kubernetes Pod/PodList JSON snapshot for readiness, restart, image-pull and termination signals. Offline triage only; no cluster access or changes.', review_pods_export,
         {'path': {'type': 'string', 'description': 'Local core v1 Pod/PodList JSON, max 2 MB and 500 Pods. Do not paste spec, credentials or logs into chat.'}, 'restart_threshold': {'type': 'integer', 'minimum': 1, 'maximum': 10000}}, ['path']),
        ('review_security_groups', 'Review supplied AWS describe-security-groups JSON for explicit public ingress. Offline; no account access or changes.', review_security_groups_export,
         {'path': {'type': 'string', 'description': 'Local .json export containing a SecurityGroups list, max 2 MB'}}, ['path']),
        ('review_terraform_plan', 'Summarize supplied Terraform plan JSON deletions and replacements without returning sensitive attribute values. Does not execute Terraform.', review_terraform_plan_export,
         {'path': {'type': 'string', 'description': 'Local terraform show -json plan export with format_version 1.x, max 2 MB. Do not paste raw sensitive attributes into chat.'}}, ['path']),
        ('analyze_daily_costs', 'Compare complete same-currency daily totals to up to seven prior days. Simple threshold check, not live billing or ML anomaly detection.', analyze_daily_costs,
         {'daily': {'type': 'array', 'items': {'type': 'object', 'properties': {'date': {'type': 'string'}, 'amount': {'type': 'string'}}, 'required': ['date', 'amount']}}, 'currency': {'type': 'string'}, 'complete_days': {'type': 'boolean'}, 'increase_percent': {'type': 'number'}, 'minimum_increase': {'type': 'number'}}, ['daily', 'currency', 'complete_days']),
    ]
    for name, description, handler, properties, required in definitions:
        registry.register(Tool(name=name, description=description,
                               parameters={'type': 'object', 'properties': properties, 'required': required},
                               handler=handler, risk=Risk.SAFE, category='devops'))
