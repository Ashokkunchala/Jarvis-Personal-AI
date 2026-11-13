"""Explicit-selection local document backups. No recursion, overwrite or restore."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from jarvis.memory.doc_memory import INDEXABLE_SUFFIXES, SECRET_CONTENT_MARKERS, _looks_secret

MAX_FILES = 50
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 10_000_000


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(ord(c) < 32 for c in value):
        raise ValueError('Supply a nonempty local path without control characters.')
    path = Path(value).expanduser().absolute()
    # Do not follow symlink/junction ancestors on supported Python/platforms.
    for part in [path, *path.parents]:
        reparse = part.exists() and bool(getattr(part.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
        if part.is_symlink() or reparse or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Symlink or junction paths are not supported for backups.')
    return path


def _snapshot(files, destination):
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('Select 1-50 explicit document file paths, not a directory.')
    output = _path(destination)
    if output.suffix.lower() != '.zip' or not output.parent.is_dir():
        raise ValueError('Choose a .zip destination in an existing local directory.')
    if output.exists():
        raise ValueError('Destination already exists. Choose a new name; backups never overwrite.')
    seen, records, payloads, total = set(), [], [], 0
    for index, value in enumerate(files):
        path = _path(value)
        resolved = path.resolve(strict=True)
        if resolved in seen or resolved == output.resolve(strict=False):
            raise ValueError('Duplicate files or a source equal to the destination are not allowed.')
        seen.add(resolved)
        if path.suffix.lower() not in INDEXABLE_SUFFIXES | {'.pdf', '.docx', '.xlsx', '.pptx'} or _looks_secret(path):
            raise ValueError('Only selected document/source formats are supported; secret-shaped names are refused.')
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Sources must be regular files.')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
                raise ValueError('Sources must be regular files no larger than 1 MB each.')
            payload = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > MAX_FILE_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('A source changed during reading or exceeded the file limit. Preview again.')
        if any(marker.encode() in payload for marker in SECRET_CONTENT_MARKERS):
            raise ValueError('Private-key-shaped content refused.')
        total += len(payload)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Selected files exceed the 10 MB total limit.')
        # Numbered member names avoid basename collisions and path traversal.
        member = f'files/{index + 1:03}{path.suffix.lower()}'
        records.append({'source': str(resolved), 'member': member, 'bytes': len(payload),
                        'sha256': hashlib.sha256(payload).hexdigest()})
        payloads.append(payload)
    manifest = {'format': 'jarvis-selected-documents-v1', 'destination': str(output.resolve(strict=False)),
                'files': records, 'total_bytes': total}
    token = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return output, manifest, token, payloads


def preview_backup(files, destination):
    _, manifest, token, _ = _snapshot(files, destination)
    return {'manifest': manifest, 'expected_manifest': token, 'created': False,
            'notice': 'Preview only. Review the exact files/destination, then request confirmed creation with this token. Archive is NOT encrypted. Secret checks are heuristics, not a guarantee; do not include credentials or sensitive documents. Preview reads the selected file bytes locally but returns only paths, sizes and hashes.'}


def create_backup(files, destination, expected_manifest):
    output, manifest, token, payloads = _snapshot(files, destination)
    if not isinstance(expected_manifest, str) or expected_manifest != token:
        raise ValueError('Selection, destination or content changed since preview. Preview and review again; no archive created.')
    # Build and validate the entire ZIP before creating any destination file.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for record, payload in zip(manifest['files'], payloads, strict=True):
            archive.writestr(record['member'], payload)
        archive.writestr('manifest.json', json.dumps({**manifest, 'created_at': datetime.now(UTC).isoformat()}, indent=2))
    archive_bytes = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive validation failed before writing; no file created.')
    # Exclusive creation is the final no-overwrite guard, even after preview.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(archive_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise OSError('Backup write failed. A partial destination file may remain; inspect it before relying on it. No cleanup or source deletion was attempted.') from exc
    return {'created': True, 'destination': str(output), 'files': len(payloads),
            'source_bytes': manifest['total_bytes'], 'archive_bytes': len(archive_bytes),
            'archive_sha256': hashlib.sha256(archive_bytes).hexdigest(),
            'notice': 'Created an unencrypted local ZIP containing the reviewed byte snapshot and a source-path/hash manifest. Not an application-consistent, encrypted, off-device or tested-restore backup. Source files were not changed. No upload, retention rotation, extraction or deletion performed. Filesystem tampering/concurrent path swaps are not fully prevented; use a trusted local directory.'}


def register_backup_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    properties = {'files': {'type': 'array', 'items': {'type': 'string'}, 'description': '1-50 explicit local document paths, 1 MB each, 10 MB total; no secrets.'},
                  'destination': {'type': 'string', 'description': 'New .zip path in an existing trusted directory. Unencrypted archive.'}}
    registry.register(Tool(name='preview_document_backup', description='Preview a bounded explicit-selection document ZIP backup; reads file bytes locally, returns only paths/sizes/hashes. No archive created; no secrets, recursion or uploads.',
                           parameters={'type': 'object', 'properties': properties, 'required': ['files', 'destination']}, handler=preview_backup, risk=Risk.SAFE, category='files'))
    registry.register(Tool(name='create_document_backup', description='Create an unencrypted local ZIP only after reviewing preview and explicit confirmation. Exact manifest token required. Never overwrites/deletes sources, uploads or restores. Secret heuristics are not a guarantee.',
                           parameters={'type': 'object', 'properties': {**properties, 'expected_manifest': {'type': 'string', 'description': 'Exact token from the reviewed backup preview.'}}, 'required': ['files', 'destination', 'expected_manifest']},
                           handler=create_backup, risk=Risk.MEDIUM, category='files', requires_confirmation=True,
                           allow_always=False, allow_auto_approve=False, never_auto_approve=True))
