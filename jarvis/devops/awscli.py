"""Guarded AWS CLI access.

Only read-only verbs run without approval. Anything that could change state,
cost money or touch secrets is classified ``confirm`` or ``blocked``. The
wrapper never uses a shell and never reads or stores credentials: the AWS CLI
uses whatever profile the user already configured.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

READ_VERBS = ("describe-", "list-", "get-", "lookup-", "batch-get-", "search-", "head-", "filter-log-events", "tail")
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
SAFE_SERVICES_NO_SUBCOMMAND = {"help", "--version", "version"}
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PROFILE = re.compile(r"^[\w.@-]{1,64}$")
_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
MAX_OUTPUT = 20_000


# Services whose "read" calls are billed per request, so they are never auto-run.
BILLED_READ_SERVICES = {"ce", "pricing", "bedrock-runtime"}
# Arguments that redirect the CLI or reach outside the user's configured account.
FORBIDDEN_READ_ARGS = ("--endpoint-url", "--profile", "--region", "--no-verify-ssl", "--ca-bundle",
                       "--cli-input-json", "--cli-input-yaml", "--debug", "file://", "fileb://")


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
    if operation.startswith(READ_VERBS):
        return "read"
    return "confirm"


def build_command(service: str, operation: str, args: list[str] | None = None,
                  profile: str | None = None, region: str | None = None) -> list[str]:
    if not _NAME.match(service or "") or not _NAME.match(operation or ""):
        raise ValueError("service and operation must be lowercase AWS CLI names like 'ec2' and 'describe-instances'")
    cmd = ["aws", service, operation]
    for a in args or []:
        if not isinstance(a, str) or "\x00" in a or "\n" in a:
            raise ValueError("invalid argument")
        cmd.append(a)
    if profile:
        if not _PROFILE.match(profile):
            raise ValueError("invalid profile name")
        cmd += ["--profile", profile]
    if region:
        if not _REGION.match(region):
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
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
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


def run_read(service: str, operation: str, args: list[str] | None = None, profile: str | None = None,
             region: str | None = None, timeout: int = 60, dry_run: bool = False) -> dict[str, Any]:
    """Run only operations classified 'read'; refuse everything else."""
    level = classify(service, operation)
    if level != "read":
        return {"success": False, "classification": level,
                "error": f"{service} {operation} is not a plain read operation ({level}); use aws_change for approval."}
    for a in args or []:
        if any(str(a).lower().startswith(f) for f in FORBIDDEN_READ_ARGS):
            return {"success": False, "error": f"Argument {a!r} is not allowed for read-only calls."}
    return run(service, operation, args, profile, region, timeout, dry_run)
