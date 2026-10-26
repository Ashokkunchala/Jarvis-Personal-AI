"""Guarded shell execution.

Arbitrary shell execution is intentionally constrained: commands must either
match a safe allow-list pattern or be explicitly confirmed by the operator.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger("jarvis.control.shell")

DEFAULT_TIMEOUT = 60
MAX_OUTPUT = 200_000

# Command heads that are always considered dangerous -> require confirmation.
DANGEROUS_HEADS = {
    "rm", "rmdir", "del", "rd", "format", "diskpart", "shutdown", "restart",
    "reg", "regedit", "bcdedit", "icacls", "takeown", "cipher", "mkfs",
    "dd", "mkfs", "mount", "diskpart", "net", "sc", "schtasks", "wevtutil",
    "taskkill", "Stop-Process", "Remove-Item", "Remove-ItemProperty",
    "Set-ExecutionPolicy", "Invoke-Expression", "iex", "curl", "wget", "bitsadmin",
}

# Command heads that are read-only and safe to run without confirmation.
SAFE_HEADS = {
    "ls", "dir", "cat", "type", "echo", "pwd", "cd", "whoami", "hostname",
    "date", "time", "uptime", "ver", "systeminfo", "ipconfig", "ifconfig",
    "ping", "tracert", "traceroute", "nslookup", "netstat", "tasklist",
    "ps", "top", "df", "du", "free", "uname", "which", "where", "Get-Process",
    "Get-Service", "Get-ChildItem", "Get-Content", "Get-Date", "Get-ComputerInfo",
    "Get-NetIPAddress", "Get-Volume", "Test-NetConnection", "Select-String",
    "git status", "git log", "git diff", "git branch", "git remote -v",
}


def _head(command: str) -> str:
    stripped = command.strip()
    if stripped.lower().startswith(("powershell", "pwsh", "cmd", "bash", "sh ", "zsh")):
        parts = stripped.split(None, 2)
        return parts[1] if len(parts) > 1 else parts[0]
    return stripped.split()[0] if stripped.split() else ""


def classify(command: str) -> str:
    """Return 'safe', 'confirm', or 'blocked' for a shell command."""
    command = command.strip()
    if not command:
        return "blocked"
    # Explicit block list for destructive pattern combos
    blocked_patterns = [
        r"rm\s+-rf\s+(/|C:|~|\*)",
        r"format\s+[A-Za-z]:",
        r"diskpart",
        r"bcdedit",
        r"Remove-Item\s+.*(-Recurse\s+)?(C:\\Windows|C:\\Program Files)",
        r":\(\)\s*\{.*\|.*&\s*\}",  # fork bomb
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return "blocked"

    head = _head(command)
    lowered = command.lower()
    if head in DANGEROUS_HEADS or head.lower() in {h.lower() for h in DANGEROUS_HEADS}:
        return "confirm"
    for token in DANGEROUS_HEADS:
        if lowered.startswith(token.lower() + " ") or lowered.startswith(token.lower() + ";"):
            return "confirm"
    if head in SAFE_HEADS or command.lower().startswith(tuple(h.lower() + " " for h in SAFE_HEADS)):
        return "safe"
    return "confirm"


def run(
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
    shell: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a shell command and return captured output."""
    classification = classify(command)
    if classification == "blocked":
        return {"success": False, "error": "Command blocked by safety policy", "classification": classification}
    if dry_run:
        return {"success": True, "classification": classification, "dry_run": True, "command": command}

    logger.info("Shell (%s): %s", classification, command)
    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            errors="replace",
        )
        stdout = (result.stdout or "")[:MAX_OUTPUT]
        stderr = (result.stderr or "")[:MAX_OUTPUT]
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "classification": classification,
            "command": command,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s", "command": command}
    except Exception as exc:
        return {"success": False, "error": str(exc), "command": command}


def run_many(commands: list[str], timeout: int = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    return [run(cmd, timeout=timeout) for cmd in commands]
