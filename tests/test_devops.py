"""Tests for the offline DevOps reviewers, runbooks and guarded AWS CLI wrapper."""

from __future__ import annotations

import asyncio
import json

import pytest

from jarvis.devops import awscli, review, runbooks
from jarvis.tools.builtin_tools import build_registry, reset_controllers


def _rules(result):
    return {f["rule"] for f in result["findings"]}


def test_iam_policy_flags_admin_and_passrole():
    policy = {"Version": "2012-10-17", "Statement": [
        {"Sid": "all", "Effect": "Allow", "Action": "*", "Resource": "*"},
        {"Effect": "Allow", "Action": ["iam:PassRole", "s3:*"], "Resource": "*"},
        {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::b/*"},
    ]}
    result = review.review_iam_policy(json.dumps(policy))
    assert {"iam-admin-action", "iam-passrole-any", "iam-service-wildcard"} <= _rules(result)
    assert result["counts"]["high"] >= 2


def test_iam_policy_rejects_bad_json():
    assert review.review_iam_policy("{nope")["success"] is False
    assert review.review_iam_policy("{}")["success"] is False


def test_terraform_review_finds_risks(tmp_path):
    (tmp_path / "main.tf").write_text(
        'resource "aws_security_group_rule" "x" {\n  cidr_blocks = ["0.0.0.0/0"]\n}\n'
        'resource "aws_s3_bucket" "b" {\n  acl = "public-read"\n}\n'
        'resource "aws_db_instance" "d" {\n  publicly_accessible = true\n  password = "hunter22222"\n}\n'
    )
    result = review.review_terraform(str(tmp_path))
    assert {"tf-open-ingress", "tf-public-s3-acl", "tf-rds-public", "tf-hardcoded-secret", "tf-no-remote-backend"} <= _rules(result)
    assert result["files_scanned"] == 1


def test_terraform_review_missing_path():
    assert review.review_terraform("/definitely/not/here")["success"] is False


def test_dockerfile_review(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:latest\nENV AWS_SECRET_ACCESS_KEY=abc123\nADD . /app\nRUN curl http://x | sh\n")
    rules = _rules(review.review_dockerfile(str(tmp_path)))
    assert {"docker-unpinned-base", "docker-secret-in-image", "docker-add-vs-copy", "docker-curl-pipe-shell", "docker-runs-as-root"} <= rules


def test_dockerfile_clean_has_no_high_findings(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\nCOPY . /app\nUSER app\nHEALTHCHECK CMD true\n")
    assert review.review_dockerfile(str(tmp_path))["counts"] == {"high": 0, "medium": 0, "low": 0}


def test_cicd_review(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(
        "on:\n  pull_request_target:\njobs:\n  a:\n    steps:\n"
        "      - uses: some/thing@v1\n      - uses: aws-actions/configure-aws-credentials@v4\n"
        "      - run: terraform apply -auto-approve\n"
    )
    rules = _rules(review.review_cicd(str(tmp_path)))
    assert {"gha-pull-request-target", "gha-unpinned-action", "gha-auto-apply", "gha-no-permissions", "gha-static-aws-keys"} <= rules


def test_runbooks():
    assert "ecs-task-stopped" in runbooks.list_runbooks()["runbooks"]
    assert runbooks.get_runbook("ecs task stopped")["success"] is True
    assert runbooks.get_runbook("nonsense")["success"] is False


@pytest.mark.parametrize("service,op,expected", [
    ("ecs", "describe-clusters", "read"),
    ("sts", "get-caller-identity", "read"),
    ("s3", "ls", "read"),
    ("ec2", "terminate-instances", "confirm"),
    ("secretsmanager", "get-secret-value", "confirm"),
    ("ssm", "get-parameter", "confirm"),
    ("ce", "get-cost-and-usage", "confirm"),
    ("iam", "create-access-key", "blocked"),
])
def test_aws_classification(service, op, expected):
    assert awscli.classify(service, op) == expected


def test_aws_read_refuses_non_reads_and_redirect_args():
    assert awscli.run_read("ec2", "terminate-instances", ["--instance-ids", "i-1"])["success"] is False
    bad = awscli.run_read("ec2", "describe-instances", ["--endpoint-url", "http://evil"])
    assert bad["success"] is False and "not allowed" in bad["error"]


def test_aws_build_command_validates_input():
    assert awscli.build_command("ecs", "list-clusters", profile="dev", region="ap-south-1")[:3] == ["aws", "ecs", "list-clusters"]
    for args in [("ecs; rm", "list"), ("ecs", "list clusters")]:
        with pytest.raises(ValueError):
            awscli.build_command(*args)
    with pytest.raises(ValueError):
        awscli.build_command("ecs", "list-clusters", region="not a region")


def test_aws_dry_run_does_not_execute():
    result = awscli.run_read("ecs", "list-clusters", dry_run=True)
    assert result["success"] and result["dry_run"] and result["command"][0] == "aws"


def test_devops_tools_registered_with_correct_gates():
    reset_controllers()
    reg = build_registry(force=True)
    assert not reg.get("aws_read").confirm_required
    assert reg.get("aws_change").confirm_required
    for name in ("review_terraform", "review_dockerfile", "review_cicd", "review_iam_policy", "devops_runbook"):
        assert reg.get(name) is not None and not reg.get(name).confirm_required


def test_aws_change_needs_approval_through_registry():
    reset_controllers()
    reg = build_registry(force=True)
    denied = asyncio.run(reg.execute("aws_change", {"service": "ec2", "operation": "stop-instances", "dry_run": True}))
    assert denied.cancelled is True

    async def approve(tool, args):
        return True

    ok = asyncio.run(reg.execute("aws_change", {"service": "ec2", "operation": "stop-instances", "args": ["--instance-ids", "i-1"], "dry_run": True}, confirm=approve))
    assert ok.ok is True


def test_aws_change_ignores_auto_approve_and_dry_run_makes_no_live_call(monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    reset_controllers()
    reg = build_registry(force=True)
    args = {"service": "ec2", "operation": "stop-instances", "args": ["--instance-ids", "i-1"], "dry_run": True}
    # auto_approve=True must not bypass approval, and no confirm callback means no run.
    res = asyncio.run(reg.execute("aws_change", args, auto_approve=True))
    assert res.cancelled is True

    async def deny(tool, a):
        return False

    assert asyncio.run(reg.execute("aws_change", args, confirm=deny, auto_approve=True)).cancelled is True

    async def approve(tool, a):
        return True

    ok = asyncio.run(reg.execute("aws_change", args, confirm=approve, auto_approve=True))
    assert ok.ok and calls == []
