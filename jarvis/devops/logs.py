"""Offline log triage for incident work.

Reads a local log file (or pasted text), counts known failure signatures,
finds the time window with the most errors and points at the matching runbook.
Nothing is sent anywhere.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

MAX_BYTES = 5_000_000
MAX_LINES = 50_000

# (rule, regex, meaning, runbook topic or "")
SIGNATURES: list[tuple[str, str, str, str]] = [
    ("oom", r"OOMKilled|Out of memory|exit code 137|Killed process", "Process was killed for memory.", "eks-pod-crashloop"),
    ("image-pull", r"ImagePullBackOff|ErrImagePull|CannotPullContainerError", "Image could not be pulled.", "ecs-task-stopped"),
    ("crashloop", r"CrashLoopBackOff|Back-off restarting", "Container keeps crashing.", "eks-pod-crashloop"),
    ("access-denied", r"AccessDenied|UnauthorizedOperation|is not authorized to perform|403 Forbidden", "Permission was refused.", "iam-access-denied"),
    ("expired-token", r"ExpiredToken|token has expired|security token.*expired", "Credentials expired.", "jenkins-aws-pipeline"),
    ("state-lock", r"Error acquiring the state lock|state lock", "Terraform state is locked.", "terraform-state-lock"),
    ("gateway", r"\b50[234]\b.*(Bad Gateway|Service Unavailable|Gateway Time-?out)|upstream (timed out|prematurely closed)", "Gateway or upstream error.", "alb-5xx"),
    ("timeout", r"timed? ?out|deadline exceeded|ETIMEDOUT", "Something timed out.", ""),
    ("conn-refused", r"connection refused|ECONNREFUSED|no route to host", "Target not listening or unreachable.", ""),
    ("dns", r"could not resolve host|Name or service not known|NXDOMAIN|no such host", "DNS lookup failed.", ""),
    ("disk-full", r"No space left on device|disk (is )?full", "Disk is full.", ""),
    ("throttle", r"ThrottlingException|Rate exceeded|Too Many Requests|429", "Requests are being throttled.", ""),
    ("tls", r"x509|certificate (has )?(expired|verify failed)|SSL(_| )ERROR", "TLS or certificate problem.", ""),
    ("db", r"too many connections|deadlock detected|could not connect to server", "Database connection problem.", ""),
]

_TS = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")
_ERR = re.compile(r"\b(ERROR|FATAL|CRITICAL|Exception|Traceback|panic)\b", re.I)


def _normalise(line: str) -> str:
    line = _TS.sub("", line)
    line = re.sub(r"\b[0-9a-f]{8,}\b", "<id>", line)
    line = re.sub(r"\d+", "N", line)
    return line.strip()[:160]


def triage_text(text: str, top: int = 5) -> dict[str, Any]:
    lines = text.splitlines()[:MAX_LINES]
    sig_counts: Counter[str] = Counter()
    first_seen: dict[str, str] = {}
    minutes: Counter[str] = Counter()
    repeated: Counter[str] = Counter()
    errors = 0
    for line in lines:
        is_err = bool(_ERR.search(line))
        matched = False
        for rule, pattern, _meaning, _rb in SIGNATURES:
            if re.search(pattern, line, re.I):
                sig_counts[rule] += 1
                first_seen.setdefault(rule, line.strip()[:200])
                matched = True
        if is_err or matched:
            errors += 1
            repeated[_normalise(line)] += 1
            m = _TS.search(line)
            if m:
                minutes[f"{m.group(1)} {m.group(2)}:{m.group(3)}"] += 1
    signals = []
    for rule, count in sig_counts.most_common():
        meaning, runbook = next((s[2], s[3]) for s in SIGNATURES if s[0] == rule)
        item = {"signature": rule, "count": count, "meaning": meaning, "example": first_seen[rule]}
        if runbook:
            item["runbook"] = runbook
        signals.append(item)
    peak = minutes.most_common(1)
    return {
        "success": True,
        "lines_read": len(lines),
        "error_lines": errors,
        "signals": signals,
        "top_repeated": [{"count": c, "pattern": p} for p, c in repeated.most_common(top)],
        "peak_minute": {"minute": peak[0][0], "error_lines": peak[0][1]} if peak else None,
        "first_error_minute": min(minutes) if minutes else None,
        "last_error_minute": max(minutes) if minutes else None,
    }


def triage_log(path: str, top: int = 5) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file():
        return {"success": False, "error": f"File not found: {path}"}
    if p.stat().st_size > MAX_BYTES:
        return {"success": False, "error": f"{p.name} is larger than {MAX_BYTES} bytes; trim it or pass the relevant window."}
    result = triage_text(p.read_text(encoding="utf-8", errors="replace"), top)
    result["file"] = str(p)
    return result
