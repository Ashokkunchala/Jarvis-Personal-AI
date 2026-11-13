"""Central security, approval and audit engine for JARVIS.

One policy decision point for every tool call, on top of the existing
``ToolRegistry`` risk levels. The blueprint's four permission levels map onto
the registry without breaking its numeric serialization:

- Read     -> ``Risk.SAFE``   : allowed inside the granted scope
- Suggest  -> planning only    : no execution (handled by the brain, not here)
- Execute  -> ``Risk.LOW``     : allowed by explicit policy
- Medium   -> ``Risk.MEDIUM``  : preview + task-bound approval by default
- Critical -> ``Risk.HIGH``    : fresh one-time approval, never auto-approved

An approval is bound to the exact tool name and canonical arguments, expires
quickly, and can be consumed once. An emergency stop fails closed: while it is
active everything above ``Risk.SAFE`` is denied.

Local SQLite only (``~/.jarvis/security.db``). No secrets are ever stored.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jarvis.tools.registry import Risk, Tool, ToolRegistry

DEFAULT_TTL_SECONDS = 120
MAX_TTL_SECONDS = 3600
MAX_REASON_CHARS = 500
MAX_AUDIT_DETAIL_CHARS = 1000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    args_json TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    device TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    tool TEXT NOT NULL DEFAULT '',
    risk TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Policy decisions
ALLOW = "allow"
REQUIRE_APPROVAL = "requires_approval"
DENY = "deny"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def scope_hash(tool_name: str, args: dict[str, Any]) -> str:
    """Hash of tool name + canonical arguments. Changed args mean a new scope."""
    canonical = json.dumps(
        {"tool": tool_name, "args": args}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Approval:
    id: str
    tool: str
    args: dict[str, Any]
    reason: str
    status: str
    created_at: str
    expires_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "args": self.args,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class SecurityStore:
    """Approvals, audit events and the emergency-stop flag."""

    def __init__(self, path: Path | str | None = None):
        self.path = str(path or (Path.home() / ".jarvis" / "security.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------- approvals
    def request_approval(
        self, tool_name: str, args: dict[str, Any], reason: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> Approval:
        tool_name = (tool_name or "").strip()
        if not tool_name:
            raise ValueError("tool_name is required.")
        if not isinstance(args, dict):
            raise ValueError("args must be an object.")
        ttl = max(1, min(int(ttl_seconds), MAX_TTL_SECONDS))
        reason = (reason or "").strip()[:MAX_REASON_CHARS]
        created = _now()
        approval = Approval(
            id=f"appr-{uuid.uuid4().hex[:12]}",
            tool=tool_name,
            args=args,
            reason=reason,
            status="pending",
            created_at=_iso(created),
            expires_at=_iso(created + timedelta(seconds=ttl)),
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO approvals (id, tool, scope_hash, args_json, reason, status,"
                " created_at, expires_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    approval.id,
                    approval.tool,
                    scope_hash(tool_name, args),
                    json.dumps(args, default=str),
                    approval.reason,
                    approval.created_at,
                    approval.expires_at,
                ),
            )
        self.audit("user", "", "approval_requested", tool_name, "", "pending", reason)
        return approval

    def _row_to_approval(self, row: sqlite3.Row) -> Approval:
        return Approval(
            id=row["id"],
            tool=row["tool"],
            args=json.loads(row["args_json"]),
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return self._row_to_approval(row) if row else None

    def list_approvals(self, status: str | None = None, limit: int = 50) -> list[Approval]:
        limit = max(1, min(int(limit), 200))
        sql = "SELECT * FROM approvals"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        approvals = [self._row_to_approval(r) for r in rows]
        return [self._expire_if_due(a) for a in approvals]

    def _expire_if_due(self, approval: Approval) -> Approval:
        if approval.status == "pending" and _parse(approval.expires_at) <= _now():
            with self._connect() as db:
                db.execute(
                    "UPDATE approvals SET status = 'expired', decided_at = ? WHERE id = ? AND status = 'pending'",
                    (_iso(_now()), approval.id),
                )
            self.audit("system", "", "approval_expired", approval.tool, "", "expired", approval.id)
            return self.get_approval(approval.id) or approval
        return approval

    def decide(self, approval_id: str, approve: bool, reason: str = "") -> Approval:
        approval = self.get_approval(approval_id)
        if approval is None:
            raise ValueError(f"Unknown approval id: {approval_id}")
        approval = self._expire_if_due(approval)
        if approval.status != "pending":
            raise ValueError(f"Approval {approval_id} is already {approval.status}.")
        decision = "approved" if approve else "rejected"
        reason = (reason or "").strip()[:MAX_REASON_CHARS]
        with self._connect() as db:
            db.execute(
                "UPDATE approvals SET status = ?, decided_at = ? WHERE id = ?",
                (decision, _iso(_now()), approval_id),
            )
        self.audit("user", "", "approval_decided", approval.tool, "", decision, reason or approval_id)
        return self.get_approval(approval_id) or approval

    def consume(self, approval_id: str, tool_name: str, args: dict[str, Any]) -> Approval:
        """Consume an approved, unexpired, scope-matching approval exactly once."""
        approval = self.get_approval(approval_id)
        if approval is None:
            raise ValueError(f"Unknown approval id: {approval_id}")
        approval = self._expire_if_due(approval)
        if approval.status != "approved":
            raise ValueError(f"Approval {approval_id} is not approved (status: {approval.status}).")
        if approval.tool != tool_name or scope_hash(tool_name, args) != scope_hash(approval.tool, approval.args):
            self.audit("system", "", "approval_scope_mismatch", tool_name, "", "denied", approval_id)
            raise ValueError("Approval scope does not match this tool and arguments.")
        with self._connect() as db:
            db.execute(
                "UPDATE approvals SET status = 'consumed', consumed_at = ? WHERE id = ? AND status = 'approved'",
                (_iso(_now()), approval_id),
            )
        self.audit("user", "", "approval_consumed", tool_name, "", "consumed", approval_id)
        return self.get_approval(approval_id) or approval

    # ------------------------------------------------------------ emergency
    def set_emergency_stop(self, enabled: bool) -> bool:
        with self._connect() as db:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('emergency_stop', ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("1" if enabled else "0",),
            )
        self.audit("user", "", "emergency_stop", "", "", "enabled" if enabled else "disabled", "")
        return enabled

    def emergency_stop_active(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'emergency_stop'").fetchone()
        return bool(row and row[0] == "1")

    # ---------------------------------------------------------------- audit
    def audit(
        self,
        actor: str,
        device: str,
        action: str,
        tool: str = "",
        risk: str = "",
        outcome: str = "",
        detail: str = "",
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO audit_events (ts, actor, device, action, tool, risk, outcome, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _iso(_now()),
                    actor,
                    device,
                    action,
                    tool,
                    risk,
                    outcome,
                    (detail or "")[:MAX_AUDIT_DETAIL_CHARS],
                ),
            )

    def audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


class PolicyEngine:
    """Maps a tool to a policy decision. Never raises for unknown tools: denies."""

    def __init__(self, store: SecurityStore):
        self.store = store

    def decide(self, tool: Tool | None, tool_name: str = "") -> str:
        name = tool.name if tool else tool_name
        if self.store.emergency_stop_active() and (tool is None or tool.risk > Risk.SAFE):
            self.store.audit("system", "", "tool_blocked_emergency_stop", name, "", "denied", "")
            return DENY
        if tool is None:
            return DENY
        if tool.risk <= Risk.LOW and not tool.confirm_required:
            return ALLOW
        return REQUIRE_APPROVAL


# --------------------------------------------------------------------------
# Tool registration
# --------------------------------------------------------------------------
def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def _bool(description: str) -> dict[str, Any]:
    return {"type": "boolean", "description": description}


_store: SecurityStore | None = None


def get_store() -> SecurityStore:
    global _store
    if _store is None:
        _store = SecurityStore()
    return _store


def reset_security_state() -> None:
    """Drop the cached store (used by tests)."""
    global _store
    _store = None


def _parse_args(args_json: str | None) -> dict[str, Any]:
    if not args_json:
        return {}
    try:
        value = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise ValueError("args_json must be a JSON object string.") from exc
    if not isinstance(value, dict):
        raise ValueError("args_json must be a JSON object string.")
    return value


def register_tools(r: ToolRegistry) -> None:
    def _policy_check(tool_name: str, args_json: str = "") -> dict[str, Any]:
        args = _parse_args(args_json)
        tool = r.get(tool_name)
        decision = PolicyEngine(get_store()).decide(tool, tool_name)
        return {
            "success": True,
            "tool": tool_name,
            "known_tool": tool is not None,
            "risk": tool.risk.name if tool else None,
            "decision": decision,
            "emergency_stop": get_store().emergency_stop_active(),
            "scope_hash": scope_hash(tool_name, args),
        }

    def _request(tool_name: str, args_json: str = "", reason: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict[str, Any]:
        args = _parse_args(args_json)
        approval = get_store().request_approval(tool_name, args, reason, ttl_seconds)
        return {"success": True, "approval": approval.as_dict()}

    def _list(status: str = "", limit: int = 50) -> dict[str, Any]:
        approvals = get_store().list_approvals(status or None, limit)
        return {"success": True, "approvals": [a.as_dict() for a in approvals]}

    def _decide(approval_id: str, approve: bool, reason: str = "") -> dict[str, Any]:
        approval = get_store().decide(approval_id, approve, reason)
        return {"success": True, "approval": approval.as_dict()}

    def _events(limit: int = 50) -> dict[str, Any]:
        return {"success": True, "events": get_store().audit_events(limit)}

    def _emergency(enable: bool) -> dict[str, Any]:
        active = get_store().set_emergency_stop(enable)
        return {
            "success": True,
            "emergency_stop": active,
            "note": "While active, every tool above read-only is denied." if active else "Normal policy restored.",
        }

    r.tool(
        "security_policy_check",
        "Dry-run the central policy engine for a tool and arguments: allow, requires_approval or deny.",
        _obj(
            {
                "tool_name": _str("Registered tool name to check."),
                "args_json": _str("JSON object string of the intended arguments."),
            },
            ["tool_name"],
        ),
        risk=Risk.SAFE,
        category="security",
    )(_policy_check)

    r.tool(
        "security_request_approval",
        "Create a task-bound, expiring, one-time approval request for a sensitive action.",
        _obj(
            {
                "tool_name": _str("Tool the approval is for."),
                "args_json": _str("JSON object string of the exact arguments to approve."),
                "reason": _str("Why this action is needed."),
                "ttl_seconds": _int("Seconds until the approval expires (default 120, max 3600)."),
            },
            ["tool_name"],
        ),
        risk=Risk.LOW,
        category="security",
    )(_request)

    r.tool(
        "security_list_approvals",
        "List approval requests, newest first, optionally filtered by status.",
        _obj(
            {
                "status": _str("pending, approved, rejected, expired or consumed; empty for all."),
                "limit": _int("Maximum approvals to return (default 50)."),
            }
        ),
        risk=Risk.SAFE,
        category="security",
    )(_list)

    r.tool(
        "security_decide_approval",
        "Approve or reject a pending approval request. Consumed once, bound to exact tool and arguments.",
        _obj(
            {
                "approval_id": _str("Approval id, e.g. appr-..."),
                "approve": _bool("true to approve, false to reject."),
                "reason": _str("Optional decision note."),
            },
            ["approval_id", "approve"],
        ),
        risk=Risk.MEDIUM,
        category="security",
        requires_confirmation=True,
    )(_decide)

    r.tool(
        "security_audit_events",
        "Read the audit log: approvals, denials, emergency stops and blocked actions.",
        _obj({"limit": _int("Maximum events to return (default 50).")}),
        risk=Risk.SAFE,
        category="security",
    )(_events)

    r.tool(
        "security_emergency_stop",
        "Enable or disable the emergency stop. While active every tool above read-only is denied.",
        _obj({"enable": _bool("true to stop everything above read-only, false to restore.")}, ["enable"]),
        risk=Risk.HIGH,
        category="security",
        requires_confirmation=True,
    )(_emergency)
