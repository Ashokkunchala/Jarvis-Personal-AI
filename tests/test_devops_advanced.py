"""Tests for the Kubernetes reviewer, log triage and post-mortem drafter."""

from __future__ import annotations

from jarvis.devops import k8s, logs, postmortem
from jarvis.tools.builtin_tools import build_registry, reset_controllers

BAD = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 1
  template:
    spec:
      hostNetwork: true
      containers:
        - name: web
          image: nginx:latest
          securityContext:
            privileged: true
---
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  type: LoadBalancer
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
roleRef:
  name: cluster-admin
"""

GOOD = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  template:
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: api
          image: registry.example.com/api:1.4.2
          resources:
            requests: {cpu: 100m}
            limits: {memory: 256Mi}
          readinessProbe: {httpGet: {path: /, port: 80}}
          livenessProbe: {httpGet: {path: /, port: 80}}
"""


def _rules(findings):
    return {f["rule"] for f in findings}


def test_k8s_flags_risky_manifest(tmp_path):
    (tmp_path / "bad.yaml").write_text(BAD)
    result = k8s.review_k8s(str(tmp_path))
    assert {"k8s-privileged", "k8s-host-network", "k8s-unpinned-image", "k8s-no-resources",
            "k8s-public-loadbalancer", "k8s-cluster-admin-binding", "k8s-single-replica"} <= _rules(result["findings"])
    assert result["counts"]["high"] >= 3
    assert result["files_scanned"] == 1


def test_k8s_clean_manifest_has_no_high_or_medium(tmp_path):
    (tmp_path / "ok.yml").write_text(GOOD)
    result = k8s.review_k8s(str(tmp_path))
    assert result["counts"]["high"] == 0 and result["counts"]["medium"] == 0


def test_k8s_skips_non_kubernetes_yaml_and_missing_path(tmp_path):
    (tmp_path / "config.yml").write_text("name: thing\nvalue: 1\n")
    assert k8s.review_k8s(str(tmp_path))["files_scanned"] == 0
    assert k8s.review_k8s("/not/here")["success"] is False


def test_log_triage_finds_signatures_and_peak():
    text = "\n".join([
        "2026-11-12T10:01:05 INFO started",
        "2026-11-12T10:02:10 ERROR container OOMKilled exit code 137",
        "2026-11-12T10:02:20 ERROR container OOMKilled exit code 137",
        "2026-11-12T10:02:30 ERROR AccessDenied for arn:aws:iam::123:role/x",
        "2026-11-12T10:05:00 ERROR connection refused to 10.0.0.5",
    ])
    result = logs.triage_text(text)
    sigs = {s["signature"]: s for s in result["signals"]}
    assert sigs["oom"]["count"] == 2 and sigs["oom"]["runbook"] == "eks-pod-crashloop"
    assert "access-denied" in sigs and "conn-refused" in sigs
    assert result["peak_minute"]["minute"] == "2026-11-12 10:02"
    assert result["first_error_minute"] == "2026-11-12 10:02"
    assert result["last_error_minute"] == "2026-11-12 10:05"
    assert result["top_repeated"][0]["count"] == 2


def test_log_triage_file_errors(tmp_path):
    assert logs.triage_log(str(tmp_path / "missing.log"))["success"] is False
    f = tmp_path / "a.log"
    f.write_text("all fine\n")
    ok = logs.triage_log(str(f))
    assert ok["success"] and ok["error_lines"] == 0 and ok["peak_minute"] is None


def test_postmortem_marks_missing_sections():
    result = postmortem.draft_postmortem("ALB 502s", root_cause="Keep-alive shorter than ALB idle timeout", timeline=["10:02 alert fired"], action_items=["Raise keep-alive (owner: Ashok, 2026-11-20)"])
    assert result["success"]
    assert "# Post-mortem: ALB 502s" in result["markdown"]
    assert "Keep-alive shorter" in result["markdown"]
    assert "summary" in result["missing_sections"] and "root_cause" not in result["missing_sections"]
    assert postmortem.draft_postmortem("  ")["success"] is False


def test_new_tools_registered_and_safe():
    reset_controllers()
    reg = build_registry(force=True)
    for name in ("review_k8s", "triage_log", "draft_postmortem"):
        tool = reg.get(name)
        assert tool is not None and not tool.confirm_required
