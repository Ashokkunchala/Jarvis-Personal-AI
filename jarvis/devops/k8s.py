"""Offline Kubernetes manifest reviewer.

Reads local YAML text only. No cluster calls, no kubectl, no file changes.
It uses line patterns instead of a YAML parser so it works with no extra
dependency; findings are heuristics for a human review, not a security audit.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jarvis.devops.review import _files, _finding, _read, _summary

WORKLOADS = ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod", "ReplicaSet")


def _documents(text: str) -> list[tuple[int, str]]:
    """Split a multi-document YAML file into (first_line_number, text) pairs."""
    docs: list[tuple[int, str]] = []
    start, buf = 1, []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip() == "---":
            if buf:
                docs.append((start, "\n".join(buf)))
            start, buf = n + 1, []
        else:
            buf.append(line)
    if buf:
        docs.append((start, "\n".join(buf)))
    return docs


def _line_of(doc: str, start: int, pattern: str) -> int | None:
    for i, line in enumerate(doc.splitlines()):
        if re.search(pattern, line):
            return start + i
    return None


def review_k8s_text(text: str, where: str = "") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for start, doc in _documents(text):
        kind_m = re.search(r"^kind:\s*(\w+)", doc, re.M)
        if not kind_m:
            continue
        kind = kind_m.group(1)
        if kind == "Service" and re.search(r"^\s*type:\s*LoadBalancer", doc, re.M):
            if not re.search(r"loadBalancerSourceRanges|internal", doc):
                findings.append(_finding("medium", "k8s-public-loadbalancer", "LoadBalancer Service with no source ranges or internal annotation is open to the internet.", where, _line_of(doc, start, r"LoadBalancer")))
        if kind == "Secret" and re.search(r"^data:\s*$", doc, re.M):
            findings.append(_finding("medium", "k8s-secret-in-manifest", "Secret values committed in a manifest are only base64 encoded; use an external secret store or sealed secrets.", where, _line_of(doc, start, r"^kind:")))
        if kind in ("ClusterRoleBinding", "RoleBinding") and re.search(r"name:\s*cluster-admin", doc):
            findings.append(_finding("high", "k8s-cluster-admin-binding", "Binding grants cluster-admin.", where, _line_of(doc, start, r"cluster-admin")))
        if kind in ("ClusterRole", "Role") and re.search(r"verbs:\s*\[?\s*['\"]?\*", doc) and re.search(r"resources:\s*\[?\s*['\"]?\*", doc):
            findings.append(_finding("high", "k8s-wildcard-rbac", "Role allows every verb on every resource.", where, _line_of(doc, start, r"verbs:")))
        if kind not in WORKLOADS:
            continue
        checks = [
            (r"privileged:\s*true", "high", "k8s-privileged", "Privileged container has near-root access to the node."),
            (r"hostNetwork:\s*true", "high", "k8s-host-network", "hostNetwork shares the node network namespace."),
            (r"hostPID:\s*true", "high", "k8s-host-pid", "hostPID exposes node processes."),
            (r"allowPrivilegeEscalation:\s*true", "medium", "k8s-privilege-escalation", "allowPrivilegeEscalation is true."),
            (r"runAsUser:\s*0\b", "medium", "k8s-run-as-root", "Container runs as UID 0."),
            (r"hostPath:", "medium", "k8s-hostpath", "hostPath mounts expose node files."),
        ]
        for pattern, sev, rule, msg in checks:
            if re.search(pattern, doc):
                findings.append(_finding(sev, rule, msg, where, _line_of(doc, start, pattern)))
        for m in re.finditer(r"^\s*-?\s*image:\s*['\"]?([^\s'\"]+)", doc, re.M):
            image = m.group(1)
            if "@sha256:" in image:
                continue
            last = image.rsplit("/", 1)[-1]
            tag = last.split(":", 1)[1] if ":" in last else ""
            if not tag or tag == "latest":
                findings.append(_finding("medium", "k8s-unpinned-image", f"Image {image!r} has no pinned tag.", where, _line_of(doc, start, re.escape(image))))
        if "resources:" not in doc:
            findings.append(_finding("medium", "k8s-no-resources", "No resource requests/limits; one pod can starve a node.", where, _line_of(doc, start, r"^kind:")))
        elif "limits:" not in doc:
            findings.append(_finding("low", "k8s-no-limits", "Resource requests set but no limits.", where, _line_of(doc, start, r"resources:")))
        if kind != "Job" and kind != "CronJob" and kind != "Pod":
            if "readinessProbe" not in doc:
                findings.append(_finding("low", "k8s-no-readiness", "No readinessProbe; traffic may reach pods that are not ready.", where, _line_of(doc, start, r"^kind:")))
            if "livenessProbe" not in doc:
                findings.append(_finding("low", "k8s-no-liveness", "No livenessProbe; hung containers are not restarted.", where, _line_of(doc, start, r"^kind:")))
        if kind == "Deployment" and re.search(r"replicas:\s*1\s*$", doc, re.M):
            findings.append(_finding("low", "k8s-single-replica", "Single replica has no redundancy during node drains.", where, _line_of(doc, start, r"replicas:")))
        if "runAsNonRoot" not in doc and "runAsUser" not in doc:
            findings.append(_finding("low", "k8s-no-security-context", "No runAsNonRoot or runAsUser set.", where, _line_of(doc, start, r"^kind:")))
    return findings


def review_k8s(path: str) -> dict[str, Any]:
    """Review Kubernetes YAML manifests under a local path."""
    try:
        files = _files(path, ("*.yml", "*.yaml"))
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}
    findings: list[dict[str, Any]] = []
    scanned = 0
    for f in files:
        if ".github" in Path(f).parts:
            continue
        try:
            text = _read(f)
        except ValueError as exc:
            findings.append(_finding("low", "k8s-file-too-large", str(exc), str(f)))
            continue
        if not re.search(r"^apiVersion:", text, re.M) or not re.search(r"^kind:", text, re.M):
            continue
        scanned += 1
        findings.extend(review_k8s_text(text, str(f)))
    return _summary(findings, scanned)
