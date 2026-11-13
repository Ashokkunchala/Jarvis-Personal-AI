"""Read-only local document memory: search your own notes and docs, with citations.

JARVIS indexes folders the user explicitly opts in (for example an FDE notes
folder or a project's docs directory) into a local SQLite FTS5 index at
``~/.jarvis/docs.db``. It only ever READS the source files; it never edits,
moves or deletes them. Answers come back with the file path and line number
so every claim can be checked against the source.

Safety rules baked in:

* explicit opt-in roots only - nothing is indexed until the user adds a folder
* secret-shaped files are never indexed: .env, private keys, tokens,
  credentials, keystores, and files whose contents look like a private key
* noisy folders (.git, node_modules, venvs, build output) are skipped
* reindex is incremental (mtime + size), deletions are detected, and removing
  a root wipes its entries from the index

Inspired by OpenJarvis's indexed-memory design (Apache-2.0,
https://github.com/open-jarvis/OpenJarvis), implemented here on the Python
standard library only - no Rust extension or vector database required.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["DocMemory", "FTS5_UNAVAILABLE"]

MAX_FILE_BYTES = 512 * 1024
MAX_FILES_PER_ROOT = 5000
MAX_SNIPPET_CHARS = 240

INDEXABLE_SUFFIXES = frozenset({
    ".md", ".txt", ".rst", ".py", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sql", ".sh", ".ps1", ".csv",
})

# Never index anything that looks like it could hold a secret.
SECRET_NAME_PATTERNS = (
    ".env", ".env.", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "secret", "credential", "token", "keystore",
)
SECRET_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".kdbx", ".asc"})
SECRET_CONTENT_MARKERS = ("PRIVATE KEY-----", "BEGIN OPENSSH PRIVATE KEY")

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".idea", ".vscode", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".terraform", "target", "out", "bin", "obj",
})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (
    path TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS docs (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS docs_root_idx ON docs (root);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _fts5_available(db: sqlite3.Connection) -> bool:
    try:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        db.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.Error:
        return False


FTS5_UNAVAILABLE = "This Python's SQLite was built without FTS5; document memory is unavailable."


def _looks_secret(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() in SECRET_SUFFIXES:
        return True
    return any(pattern in name for pattern in SECRET_NAME_PATTERNS)


def _match_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (AND of quoted terms)."""
    terms = re.findall(r"[\w]+", query.lower())
    return " AND ".join(f'"{term}"' for term in terms[:8])


class DocMemory:
    """SQLite FTS index over explicitly allowed folders."""

    def __init__(self, path: Path | str | None = None):
        self.path = str(path or (Path.home() / ".jarvis" / "docs.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            if not _fts5_available(db):
                raise RuntimeError(FTS5_UNAVAILABLE)
            db.executescript(_SCHEMA)
            db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts "
                "USING fts5(path UNINDEXED, title, content, tokenize='unicode61')"
            )

    # ------------------------------------------------------------------ db
    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # ----------------------------------------------------------------- roots
    def add_root(self, folder: Path | str) -> dict[str, Any]:
        """Opt a folder in for indexing. The folder itself is never modified."""
        root = Path(folder).expanduser()
        if not root.exists():
            raise ValueError(f"Folder does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Not a folder: {root}")
        resolved = root.resolve()
        if resolved.parent == resolved or resolved == Path.home().resolve():
            raise ValueError(
                "Pick a specific notes/docs folder, not a whole drive or your home directory."
            )
        with self._connect() as db:
            db.execute(
                "INSERT INTO roots (path, added_at) VALUES (?, ?) "
                "ON CONFLICT(path) DO NOTHING",
                (str(resolved), _now()),
            )
        return {"root": str(resolved), **self.reindex(root=resolved)}

    def remove_root(self, folder: Path | str) -> dict[str, Any]:
        """Stop indexing a folder and delete its index entries (files untouched)."""
        resolved = str(Path(folder).expanduser().resolve())
        with self._connect() as db:
            rows = db.execute(
                "SELECT path FROM docs WHERE root = ?", (resolved,)
            ).fetchall()
            for row in rows:
                db.execute("DELETE FROM docs_fts WHERE path = ?", (row["path"],))
            db.execute("DELETE FROM docs WHERE root = ?", (resolved,))
            cur = db.execute("DELETE FROM roots WHERE path = ?", (resolved,))
        return {"root": resolved, "removed": cur.rowcount > 0, "forgotten_docs": len(rows)}

    def list_roots(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT r.path, r.added_at, COUNT(d.path) AS docs "
                "FROM roots r LEFT JOIN docs d ON d.root = r.path "
                "GROUP BY r.path ORDER BY r.path"
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- indexing
    def _iter_files(self, root: Path):
        yielded = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                if yielded >= MAX_FILES_PER_ROOT:
                    return
                candidate = Path(dirpath) / filename
                if candidate.suffix.lower() not in INDEXABLE_SUFFIXES:
                    continue
                if _looks_secret(candidate):
                    continue
                try:
                    size = candidate.stat().st_size
                except OSError:
                    continue
                if size > MAX_FILE_BYTES:
                    continue
                yielded += 1
                yield candidate

    def _read(self, path: Path) -> str | None:
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        if b"\x00" in raw[:1024]:
            return None  # binary, not notes
        head = raw[:4096].decode("utf-8", errors="ignore")
        if any(marker in head for marker in SECRET_CONTENT_MARKERS):
            return None
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _title(path: Path, content: str) -> str:
        for line in content.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:120]
        return path.name

    def reindex(self, root: Path | str | None = None) -> dict[str, Any]:
        """Incrementally index opted-in roots: new/changed files in, gone files out."""
        with self._connect() as db:
            if root is not None:
                roots = [str(Path(root).expanduser().resolve())]
            else:
                roots = [r["path"] for r in db.execute("SELECT path FROM roots")]
            stats = {"roots": len(roots), "added": 0, "updated": 0, "skipped": 0, "removed": 0}
            for root_path in roots:
                seen: set[str] = set()
                base = Path(root_path)
                if not base.is_dir():
                    # Root vanished from disk: drop its entries so answers stay honest.
                    stale = db.execute(
                        "SELECT path FROM docs WHERE root = ?", (root_path,)
                    ).fetchall()
                    for row in stale:
                        db.execute("DELETE FROM docs_fts WHERE path = ?", (row["path"],))
                    stats["removed"] += len(stale)
                    db.execute("DELETE FROM docs WHERE root = ?", (root_path,))
                    continue
                for file_path in self._iter_files(base):
                    key = str(file_path)
                    seen.add(key)
                    try:
                        stat = file_path.stat()
                    except OSError:
                        continue
                    existing = db.execute(
                        "SELECT mtime, size FROM docs WHERE path = ?", (key,)
                    ).fetchone()
                    if existing and existing["mtime"] == stat.st_mtime and existing["size"] == stat.st_size:
                        stats["skipped"] += 1
                        continue
                    content = self._read(file_path)
                    if content is None:
                        stats["skipped"] += 1
                        continue
                    title = self._title(file_path, content)
                    db.execute(
                        "INSERT INTO docs (path, root, mtime, size, title, content, indexed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(path) DO UPDATE SET root=excluded.root, mtime=excluded.mtime, "
                        "size=excluded.size, title=excluded.title, content=excluded.content, "
                        "indexed_at=excluded.indexed_at",
                        (key, root_path, stat.st_mtime, stat.st_size, title, content, _now()),
                    )
                    db.execute("DELETE FROM docs_fts WHERE path = ?", (key,))
                    db.execute(
                        "INSERT INTO docs_fts (path, title, content) VALUES (?, ?, ?)",
                        (key, title, content),
                    )
                    stats["updated" if existing else "added"] += 1
                stale = db.execute(
                    "SELECT path FROM docs WHERE root = ?", (root_path,)
                ).fetchall()
                for row in stale:
                    if row["path"] not in seen:
                        db.execute("DELETE FROM docs_fts WHERE path = ?", (row["path"],))
                        db.execute("DELETE FROM docs WHERE path = ?", (row["path"],))
                        stats["removed"] += 1
        return stats

    # ---------------------------------------------------------------- search
    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Full-text search over indexed docs. Every hit carries its source."""
        limit = max(1, min(int(limit), 25))
        match = _match_query(query or "")
        if not match:
            return {"query": query, "results": [], "indexed_docs": self.status()["indexed_docs"]}
        with self._connect() as db:
            rows = db.execute(
                "SELECT path, title, snippet(docs_fts, 2, '[', ']', ' ... ', 32) AS snip "
                "FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            ).fetchall()
            results = []
            for row in rows:
                content_row = db.execute(
                    "SELECT content FROM docs WHERE path = ?", (row["path"],)
                ).fetchone()
                line_no = self._first_match_line(content_row["content"] if content_row else "", query)
                snippet = " ".join(str(row["snip"]).split())[:MAX_SNIPPET_CHARS]
                results.append({
                    "path": row["path"],
                    "title": row["title"],
                    "line": line_no,
                    "snippet": snippet,
                    "citation": f"{row['path']}:{line_no}",
                })
        return {"query": query, "results": results, "indexed_docs": self.status()["indexed_docs"]}

    @staticmethod
    def _first_match_line(content: str, query: str) -> int:
        terms = re.findall(r"[\w]+", (query or "").lower())
        if not terms:
            return 1
        for number, line in enumerate(content.splitlines(), start=1):
            lowered = line.lower()
            if any(term in lowered for term in terms):
                return number
        return 1

    # ---------------------------------------------------------------- control
    def forget(self, file_path: Path | str) -> dict[str, Any]:
        """Remove one file from the index (the file itself is untouched)."""
        key = str(Path(file_path).expanduser().resolve())
        with self._connect() as db:
            db.execute("DELETE FROM docs_fts WHERE path = ?", (key,))
            cur = db.execute("DELETE FROM docs WHERE path = ?", (key,))
        return {"path": key, "forgotten": cur.rowcount > 0}

    def clear(self) -> dict[str, Any]:
        """Drop the entire index and all roots. Source files are never touched."""
        with self._connect() as db:
            docs = db.execute("SELECT COUNT(*) AS n FROM docs").fetchone()["n"]
            db.execute("DELETE FROM docs_fts")
            db.execute("DELETE FROM docs")
            db.execute("DELETE FROM roots")
        return {"cleared": True, "forgotten_docs": docs}

    def status(self) -> dict[str, Any]:
        with self._connect() as db:
            docs = db.execute("SELECT COUNT(*) AS n FROM docs").fetchone()["n"]
            roots = db.execute("SELECT COUNT(*) AS n FROM roots").fetchone()["n"]
        return {"indexed_docs": docs, "roots": roots, "db": self.path}
