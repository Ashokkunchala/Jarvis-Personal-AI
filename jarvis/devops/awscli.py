"""Guarded AWS CLI access.

Only exact reviewed operations and arguments run on the read path. Anything that could change state,
cost money or touch secrets is classified ``confirm`` or ``blocked``. The
wrapper never uses a shell and never reads or stores credentials: the AWS CLI
uses whatever profile the user already configured.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

# Exact operation and flag contracts, not a guess from verb spelling. New reads
# require an explicit review; unlisted operations stay on the approval path.
PAGINATION = {"--starting-token": "one", "--page-size": "positive", "--max-items": "positive"}
READ_OPERATIONS = {
    ("ec2", "describe-instances"): {**PAGINATION, "--instance-ids": "many", "--filters": "many"},
    ("ecs", "list-clusters"): dict(PAGINATION),
    ("ecs", "describe-clusters"): {"--clusters": "many", "--include": "many"},
    ("sts", "get-caller-identity"): {},
    ("s3", "ls"): {"--recursive": "switch", "--human-readable": "switch", "--summarize": "switch", "--page-size": "positive"},
}
COMMON_READ_FLAGS = {"--query": "one", "--output": "json", "--no-paginate": "switch",
                     "--no-cli-pager": "switch", "--no-cli-auto-prompt": "switch"}
# Reads that return secret material even though the verb looks harmless.
SECRET_READS = {
    ("secretsmanager", "get-secret-value"),
    ("ssm", "get-parameter"),
    ("ssm", "get-parameters"),
    ("ssm", "get-parameters-by-path"),
    ("kms", "decrypt"),
    ("sts", "get-session-token"),
    ("sts", "assume-role"),
    ("iam", "get-credential-report"),
    ("ecr", "get-login-password"),
    ("ecr", "get-authorization-token"),
    ("eks", "get-token"),
    ("lambda", "get-function"),
    ("rds", "generate-db-auth-token"),
}
BLOCKED = {
    ("iam", "delete-account-alias"),
    ("organizations", "leave-organization"),
    ("organizations", "close-account"),
    ("iam", "create-access-key"),
    ("iam", "delete-account-password-policy"),
}
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PROFILE = re.compile(r"^[\w.@-]{1,64}$")
_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
MAX_OUTPUT = 20_000


# Services whose "read" calls are billed per request, so they are never auto-run.
BILLED_READ_SERVICES = {"ce", "pricing", "bedrock-runtime"}


def classify(service: str, operation: str) -> str:
    """Return 'read', 'confirm' or 'blocked' for an AWS CLI service/operation."""
    service, operation = service.lower(), operation.lower()
    if service in BILLED_READ_SERVICES:
        return "confirm"
    if (service, operation) == ("s3", "ls"):
        return "read"
    if (service, operation) in BLOCKED:
        return "blocked"
    if (service, operation) in SECRET_READS:
        return "confirm"
    if (service, operation) in READ_OPERATIONS:
        return "read"
    return "confirm"


def build_command(service: str, operation: str, args: list[str] | None = None,
                  profile: str | None = None, region: str | None = None) -> list[str]:
    if not _NAME.fullmatch(service or "") or not _NAME.fullmatch(operation or ""):
        raise ValueError("service and operation must be lowercase AWS CLI names like 'ec2' and 'describe-instances'")
    cmd = ["aws", service, operation]
    for a in args or []:
        if not isinstance(a, str) or "\x00" in a or "\n" in a:
            raise ValueError("invalid argument")
        cmd.append(a)
    if profile:
        if not _PROFILE.fullmatch(profile):
            raise ValueError("invalid profile name")
        cmd += ["--profile", profile]
    if region:
        if not _REGION.fullmatch(region):
            raise ValueError("invalid region")
        cmd += ["--region", region]
    if not any(a == "--output" for a in cmd):
        cmd += ["--output", "json"]
    return cmd


def run(service: str, operation: str, args: list[str] | None = None, profile: str | None = None,
        region: str | None = None, timeout: int = 60, dry_run: bool = False) -> dict[str, Any]:
    """Run an AWS CLI command. The caller's confirmation policy decides approval."""
    try:
        cmd = build_command(service, operation, args, profile, region)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    level = classify(service, operation)
    if level == "blocked":
        return {"success": False, "error": "Operation blocked by safety policy", "classification": level}
    if dry_run:
        return {"success": True, "dry_run": True, "classification": level, "command": cmd}
    if shutil.which("aws") is None:
        return {"success": False, "error": "AWS CLI is not installed or not on PATH.", "classification": level}
    try:
        env = {**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"}
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace", env=env)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"AWS CLI timed out after {timeout}s", "classification": level}
    out = (proc.stdout or "")[:MAX_OUTPUT]
    parsed: Any = None
    try:
        parsed = json.loads(out) if out.strip() else None
    except json.JSONDecodeError:
        pass
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "classification": level,
        "command": cmd,
        "output": parsed if parsed is not None else out.strip(),
        "stderr": (proc.stderr or "")[:2000].strip(),
    }


def _validate_read_args(service, operation, args):
    if not isinstance(args, list) or len(args) > 100:
        raise ValueError('Read args must be a list of at most 100 strings.')
    for value in args:
        if not isinstance(value, str) or not value or len(value) > 2000 or any(ord(c) < 32 for c in value):
            raise ValueError('Read arguments must be nonempty bounded strings without control characters.')
        if 'file://' in value.lower() or 'fileb://' in value.lower():
            raise ValueError('Local-file argument loading is not allowed for read-only calls.')
    flags = {**COMMON_READ_FLAGS, **READ_OPERATIONS[(service, operation)]}
    seen, index, positional = set(), 0, False
    while index < len(args):
        token = args[index]
        if not token.startswith('--'):
            if (service, operation) != ('s3', 'ls') or positional or not token.startswith('s3://'):
                raise ValueError('Unexpected positional argument in read-only call.')
            if len(token) <= 5:
                raise ValueError('Specify a nonempty S3 bucket path or omit it to list buckets.')
            positional = True
            index += 1
            continue
        # Exact flags only. Abbreviations, --flag=value and unknown globals fail closed.
        if token not in flags or token in seen:
            raise ValueError('Argument is not allowed or repeated for this read-only operation.')
        seen.add(token)
        kind = flags[token]
        index += 1
        if kind == 'switch':
            continue
        values = []
        while index < len(args) and not args[index].startswith('--'):
            values.append(args[index])
            index += 1
            if kind != 'many':
                break
        if not values:
            raise ValueError('A read argument is missing its value.')
        if kind == 'positive' and (not values[0].isascii() or not values[0].isdigit() or not 1 <= int(values[0]) <= 10000):
            raise ValueError('Pagination sizes must be integers from 1 to 10000.')
        if kind == 'json' and values != ['json']:
            raise ValueError('Read output must be json.')


def run_read(service: str, operation: str, args: list[str] | None = None, profile: str | None = None,
             region: str | None = None, timeout: int = 60, dry_run: bool = False) -> dict[str, Any]:
    """Run only exact reviewed reads and flags; everything else needs approval."""
    if not isinstance(service, str) or not isinstance(operation, str):
        return {'success': False, 'error': 'Service and operation must be strings.'}
    level = classify(service, operation)
    if level != 'read':
        return {'success': False, 'classification': level,
                'error': 'Operation is not on the reviewed read allowlist; use aws_change for approval.'}
    try:
        # Preserve exact lowercase command names, rather than classify one command
        # and execute another spelling. Build also validates profile and region.
        if (service, operation) not in READ_OPERATIONS:
            raise ValueError('Use exact lowercase service and operation names.')
        _validate_read_args(service, operation, [] if args is None else args)
        build_command(service, operation, args, profile, region)
    except (ValueError, TypeError) as exc:
        return {'success': False, 'error': str(exc)}
    return run(service, operation, args, profile, region, timeout, dry_run)
