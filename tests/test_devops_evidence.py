import asyncio
import json

import pytest

from jarvis.devops.evidence import (
    analyze_daily_costs,
    review_security_groups,
    review_terraform_plan,
)
from jarvis.tools.builtin_tools import build_registry


def sg(rule):
    return {'SecurityGroups': [{'GroupId': 'sg-example', 'IpPermissions': [rule]}]}


@pytest.mark.parametrize('source', [{'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}, {'Ipv6Ranges': [{'CidrIpv6': '::/0'}]}])
def test_public_ssh_ipv4_ipv6(source):
    result = review_security_groups(sg(dict(IpProtocol='tcp', FromPort=22, ToPort=22, **source)))
    assert result['findings'][0]['severity'] == 'high'


def test_numeric_protocol_and_port_ranges():
    rule = {'IpProtocol': '6', 'FromPort': 20, 'ToPort': 24, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
    assert review_security_groups(sg(rule))['findings'][0]['severity'] == 'high'
    rule['IpProtocol'] = '-1'
    assert 'all protocols' in review_security_groups(sg(rule))['findings'][0]['issue']


def test_private_ingress_not_reported_as_world_access():
    rule = {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '10.0.0.0/8'}]}
    assert not review_security_groups(sg(rule))['findings']


@pytest.mark.parametrize('rule', [{'IpProtocol': 'tcp', 'FromPort': 23, 'ToPort': 22}, {'IpProtocol': 'tcp'}, {'IpProtocol': '-1', 'IpRanges': [{'CidrIp': 'bad'}]}, {'IpProtocol': '-1', 'IpRanges': [{'CidrIp': '::/0'}]}])
def test_malformed_ingress_rejected(rule):
    with pytest.raises(ValueError):
        review_security_groups(sg(rule))


def test_terraform_replacements_deletions_and_no_sensitive_values():
    actions = [['delete', 'create'], ['create', 'delete'], ['delete'], ['no-op'], ['forget']]
    doc = {'format_version': '1.2', 'resource_changes': [
        {'address': f'aws_instance.example_{i}', 'change': {'actions': action, 'before': {'password': 'SECRET'}, 'after': {'token': 'SECRET'}, 'after_sensitive': {'token': True}}}
        for i, action in enumerate(actions)]}
    result = review_terraform_plan(doc)
    assert result['deletions'] == 3 and result['replacements'] == 2
    assert 'SECRET' not in json.dumps(result)
    assert result['action_counts']['forget'] == 1


def test_terraform_unknown_and_incomplete_plan_warns():
    result = review_terraform_plan({'format_version': '1.2', 'errored': True, 'complete': False, 'resource_changes': [{'change': {'actions': ['future-action']}}]})
    assert len(result['warnings']) == 3
    with pytest.raises(ValueError):
        review_terraform_plan({'format_version': '2.0', 'resource_changes': []})
    with pytest.raises(ValueError):
        review_terraform_plan({'format_version': '1.2', 'values': {}})


def rows(amounts):
    return [{'date': f'2026-11-{i + 1:02}', 'amount': amount} for i, amount in enumerate(amounts)]


def test_threshold_cost_analysis_and_zero_baseline():
    result = analyze_daily_costs(rows(['10', '10', '10', '25']), 'USD', True)
    assert result['threshold_flag'] and result['increase_percent'] == '150.0'
    assert result['increase_amount'] == '15'
    assert not analyze_daily_costs(rows([10, 10, 10, 9]), 'USD', True)['threshold_flag']
    zero = analyze_daily_costs(rows([0, 0, 0, 6]), 'USD', True)
    assert zero['threshold_flag'] and zero['increase_percent'] is None
    assert not analyze_daily_costs(rows([0, 0, 0, 0]), 'USD', True)['threshold_flag']


@pytest.mark.parametrize('amount', ['NaN', 'Infinity', '-1', True, 'invalid'])
def test_costs_reject_invalid_values(amount):
    with pytest.raises(ValueError):
        analyze_daily_costs(rows([10, 10, 10, amount]), 'USD', True)


def test_costs_require_complete_consecutive_days_and_one_currency():
    for data, currency, complete in [(rows([1, 2, 3]), 'USD', True), (rows([1, 2, 3, 4]), 'USD', False), (rows([1, 2, 3, 4]), 'usd', True)]:
        with pytest.raises(ValueError):
            analyze_daily_costs(data, currency, complete)
    data = rows([1, 2, 3, 4])
    data[-1]['date'] = data[0]['date']
    with pytest.raises(ValueError):
        analyze_daily_costs(data, 'USD', True)


def test_new_reviews_are_available_through_registry(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'security.db'))
    registry = build_registry(force=True)
    result = asyncio.run(registry.execute('analyze_daily_costs', {'daily': rows([10, 10, 10, 30]), 'currency': 'USD', 'complete_days': True}))
    assert result.ok and result.data['threshold_flag']
    export = tmp_path / 'plan.json'
    export.write_text(json.dumps({'format_version': '1.2', 'resource_changes': []}))
    events = []
    result = asyncio.run(registry.execute('review_terraform_plan', {'path': str(export)}, on_event=events.append))
    assert events[0]['args'] == {'path': str(export)}
    assert result.ok and result.data['resources_reviewed'] == 0


@pytest.mark.parametrize('payload', [b'{broken', b'[]', b'\xff'])
def test_invalid_exports_fail_without_echoing_payload(tmp_path, payload):
    from jarvis.devops.evidence import review_terraform_plan_export
    export = tmp_path / 'plan.json'
    export.write_bytes(payload)
    with pytest.raises(ValueError):
        review_terraform_plan_export(str(export))


def test_file_export_limits(tmp_path):
    from jarvis.devops.evidence import review_terraform_plan_export
    export = tmp_path / 'large.json'
    export.write_bytes(b' ' * 2_000_001)
    with pytest.raises(ValueError, match='2 MB'):
        review_terraform_plan_export(str(export))
    with pytest.raises(ValueError, match='.json'):
        review_terraform_plan_export(str(tmp_path / 'missing.txt'))
