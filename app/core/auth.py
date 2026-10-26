import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import sqlite3
from pathlib import Path

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import get_settings

security = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    """Hash token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(48)


def verify_token_hmac(supplied: str, expected: str) -> bool:
    """Verify token using constant-time comparison."""
    try:
        return hmac.compare_digest(supplied, expected)
    except Exception:
        return False


def get_db_path() -> Path:
    settings = get_settings()
    return Path(settings.jarvis_db_path)


def get_db_connection():
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class TokenAuth:
    def __init__(self):
        self._init_device_table()
    
    def _init_device_table(self):
        with get_db_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen TEXT,
                    revoked_at TEXT,
                    user_agent TEXT,
                    ip_address TEXT
                );
                CREATE TABLE IF NOT EXISTS auth_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    action TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    details TEXT
                );
            """)
            conn.commit()
    
    def validate_token(self, authorization: Optional[str] = None) -> dict:
        settings = get_settings()
        expected = settings.jarvis_api_token
        
        if len(expected) < 32 or expected.startswith("replace_"):
            raise HTTPException(
                status_code=503, 
                detail="Set a random JARVIS_API_TOKEN of at least 32 characters in .env."
            )
        
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization header.")
        
        supplied = authorization.removeprefix("Bearer ").strip()
        if not supplied:
            raise HTTPException(status_code=401, detail="Empty token.")
        
        if verify_token_hmac(supplied, expected):
            self._log_audit("legacy_token_used", success=True)
            return {"type": "legacy", "valid": True}
        
        token_h = hash_token(supplied)
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE token_hash=? AND revoked_at IS NULL",
                (token_h,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE devices SET last_seen=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), row["id"])
                )
                conn.commit()
                self._log_audit("device_token_used", device_id=row["device_id"], success=True)
                return {"type": "device", "device_id": row["device_id"], "name": row["name"], "valid": True}
        
        self._log_audit("token_invalid", success=False)
        raise HTTPException(status_code=401, detail="Missing or invalid device token.")
    
    def issue_device_token(self, name: str, user_agent: str = None, ip_address: str = None) -> dict:
        token = generate_token()
        token_h = hash_token(token)
        device_id = secrets.token_urlsafe(16)
        now = datetime.now(timezone.utc).isoformat()
        
        with get_db_connection() as conn:
            conn.execute(
                """INSERT INTO devices (device_id, name, token_hash, created_at, user_agent, ip_address)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (device_id, name.strip()[:100], token_h, now, user_agent, ip_address)
            )
            conn.commit()
        
        self._log_audit("device_token_issued", device_id=device_id, success=True)
        return {"device_id": device_id, "token": token, "name": name, "created_at": now}
    
    def revoke_device(self, device_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with get_db_connection() as conn:
            cur = conn.execute(
                "UPDATE devices SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                (now, device_id)
            )
            conn.commit()
            revoked = cur.rowcount > 0
        if revoked:
            self._log_audit("device_token_revoked", device_id=device_id, success=True)
        return revoked
    
    def list_devices(self) -> List[dict]:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT device_id, name, created_at, last_seen, revoked_at FROM devices ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    
    def _log_audit(self, action: str, device_id: str = None, success: bool = True, ip_address: str = None, user_agent: str = None, details: str = None):
        try:
            with get_db_connection() as conn:
                conn.execute(
                    """INSERT INTO auth_audit (device_id, action, ip_address, user_agent, timestamp, success, details)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (device_id, action, ip_address, user_agent, datetime.now(timezone.utc).isoformat(), 1 if success else 0, details)
                )
                conn.commit()
        except Exception:
            pass


token_auth = TokenAuth()


def require_api_token(authorization: Optional[str] = Header(default=None), request: Request = None):
    return token_auth.validate_token(authorization)


def require_device_token_legacy(authorization: Optional[str] = Header(default=None)):
    return require_api_token(authorization)
