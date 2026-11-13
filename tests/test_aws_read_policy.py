import subprocess

import pytest

from jarvis.devops import awscli


@pytest.mark.parametrize('service,operation', [('ec2', 'describe-instances'), ('ecs', 'list-clusters'),
                                              ('ecs', 'describe-clusters'), ('sts', 'get-caller-identity'), ('s3', 'ls')])
def test_exact_reviewed_operations_preview_without_execution(service, operation, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('No AWS calls allowed in tests'))
    assert awscli.run_read(service, operation, dry_run=True)['success']


@pytest.mark.parametrize('service,operation', [('fictional', 'get-anything'), ('ec2', 'get-password-data'),
                                              ('ssm', 'get-parameter-history'), ('s3api', 'get-object'),
                                              ('s3api', 'select-object-content'), ('ec2', 'describe-future-api'),
                                              ('logs', 'tail'), ('lambda', 'get-function'), ('ce', 'get-cost-and-usage')])
def test_unreviewed_and_secret_or_billed_reads_require_confirmation(service, operation):
    assert awscli.classify(service, operation) == 'confirm'
    assert not awscli.run_read(service, operation, dry_run=True)['success']


@pytest.mark.parametrize('args', [['--endpoint-url', 'https://example.invalid'], ['--endpoint', 'https://example.invalid'],
                                 ['--endpoint-url=https://example.invalid'], ['--profile', 'other'], ['--region', 'us-east-1'],
                                 ['--debug'], ['--cli-auto-prompt'], ['--cli-input-json', '{}'], ['--output', 'text'],
                                 ['--query', 'file:///etc/passwd'], ['--query', 'fileb://x'], ['--instance-ids', 'i-1', '/tmp/out'],
                                 ['outfile'], ['--max-items', '0'], ['--page-size', '10001'], ['--page-size', 'nan'],
                                 ['--query'], ['--max-items', '2', '--max-items', '3'], ['--query', 'x\n'], [True], 'not a list'])
def test_unsafe_and_unknown_args_fail_closed(args, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('Rejected call executed'))
    result = awscli.run_read('ecs', 'list-clusters', args, dry_run=True)
    assert not result['success']


def test_ec2_filters_ids_and_common_query():
    result = awscli.run_read('ec2', 'describe-instances', ['--instance-ids', 'i-1', 'i-2', '--filters', 'Name=instance-state-name,Values=running', '--query', 'Reservations[].Instances[].InstanceId', '--max-items', '5'], dry_run=True)
    assert result['success'] and result['command'][-2:] == ['--output', 'json']


def test_s3_listing_only_accepts_one_bucket_position():
    assert awscli.run_read('s3', 'ls', ['s3://example-bucket/path', '--recursive'], dry_run=True)['success']
    for args in [['/tmp/out'], ['s3://'], ['s3://bucket', '/tmp/out'], ['s3://bucket', '--request-payer', 'requester']]:
        assert not awscli.run_read('s3', 'ls', args, dry_run=True)['success']


def test_exact_names_and_no_control_characters_in_profile_region():
    assert not awscli.run_read('ECS', 'list-clusters', dry_run=True)['success']
    for kwargs in [dict(profile='dev\n'), dict(region='us-east-1\n')]:
        assert not awscli.run_read('ecs', 'list-clusters', dry_run=True, **kwargs)['success']


def test_noninteractive_subprocess_environment_without_real_execution(monkeypatch):
    captured = {}
    monkeypatch.setattr(awscli.shutil, 'which', lambda _: '/mock/aws')

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, '{}', '')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    result = awscli.run_read('ecs', 'list-clusters')
    assert result['success']
    assert captured['env']['AWS_PAGER'] == '' and captured['env']['AWS_CLI_AUTO_PROMPT'] == 'off'
    assert 'shell' not in captured
