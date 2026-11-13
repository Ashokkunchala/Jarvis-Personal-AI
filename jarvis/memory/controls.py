"""Explicit retention and literal search for the existing backend memory store.

Expiration excludes an item from future chat context, but is not secure erasure.
Deletion of expired rows is a separate confirmed tool operation.
"""
from __future__ import annotations

from datetime import UTC, datetime


def _store():
    from app.personal_data import _connect
    return _connect()


def _now():
    return datetime.now(UTC).isoformat()


def search_memories(query: str = '', category: str = '', include_expired: bool = False):
    if not isinstance(query, str) or len(query) > 500 or not isinstance(category, str) or len(category) > 40:
        raise ValueError('Search text must be up to 500 characters and category up to 40.')
    if type(include_expired) is not bool:
        raise ValueError('include_expired must be a boolean.')
    where, params = [], []
    if query:
        # instr is a literal substring search: no SQL or FTS query interpretation.
        where.append('instr(lower(text),lower(?))>0')
        params.append(query)
    if category:
        where.append('category=?')
        params.append(category)
    if not include_expired:
        where.append('(expires_at IS NULL OR julianday(expires_at)>julianday(?))')
        params.append(_now())
    sql = 'SELECT * FROM memories'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    with _store() as db:
        return [dict(row) for row in db.execute(sql + ' ORDER BY id DESC LIMIT 500', params)]


def set_memory_expiry(memory_id: int, expires_at: str | None = None):
    if type(memory_id) is not int or memory_id < 1:
        raise ValueError('Choose an integer memory ID from memory_search_saved.')
    value = None
    if expires_at is not None:
        try:
            parsed = datetime.fromisoformat(expires_at)
            if parsed.tzinfo is None:
                raise ValueError('timezone missing')
            value = parsed.astimezone(UTC).isoformat()
        except (ValueError, TypeError) as exc:
            raise ValueError('expires_at must be an ISO date-time with timezone, or null to remove expiry.') from exc
    with _store() as db:
        changed = db.execute('UPDATE memories SET expires_at=? WHERE id=?', (value, memory_id)).rowcount
        if not changed:
            raise ValueError('Memory not found.')
    return {'memory_id': memory_id, 'expires_at': value,
            'notice': 'Expired items are excluded from future context, not erased. Already-sent chat context cannot be recalled. Use the confirmed purge tool for expired rows.'}


def retention_status():
    with _store() as db:
        total = db.execute('SELECT COUNT(*) FROM memories').fetchone()[0]
        ids = [row[0] for row in db.execute('SELECT id FROM memories WHERE expires_at IS NOT NULL AND julianday(expires_at)<=julianday(?) ORDER BY id', (_now(),))]
    return {'total_rows': total, 'expired_count': len(ids), 'expired_ids': ids,
            'notice': 'Expired rows remain in local storage and exports until explicitly purged. This does not cover document indexes or previous chat history.'}


def purge_expired_memories():
    with _store() as db:
        changed = db.execute('DELETE FROM memories WHERE expires_at IS NOT NULL AND julianday(expires_at)<=julianday(?)', (_now(),)).rowcount
    return {'deleted_rows': changed, 'notice': 'Deleted expired memory rows only. Not secure disk erasure; backups, exports and prior messages are unchanged.'}


def register_memory_controls(registry):
    from jarvis.tools.registry import Risk, Tool
    definitions = [
        ('memory_search_saved', 'Literal search/category review of saved backend memories. Excludes expired entries unless include_expired=true. Not semantic search; local backend DB only.', search_memories, Risk.SAFE,
         {'query': {'type': 'string'}, 'category': {'type': 'string'}, 'include_expired': {'type': 'boolean'}}, []),
        ('memory_set_expiry', 'Set explicit expiry on a saved memory by ID. Timezone required; null removes expiry. Expiry stops future context use but does not erase storage or previous chat context.', set_memory_expiry, Risk.LOW,
         {'memory_id': {'type': 'integer'}, 'expires_at': {'type': 'string', 'description': 'ISO date-time with explicit timezone; omit to remove expiry'}}, ['memory_id']),
        ('memory_retention_status', 'Show expired row IDs and counts before requesting a confirmed purge. No deletion.', retention_status, Risk.SAFE, {}, []),
        ('memory_purge_expired', 'Delete only expired backend memory rows after explicit confirmation. Does not erase exports, backups, prior messages or document indexes.', purge_expired_memories, Risk.HIGH, {}, []),
    ]
    for name, description, handler, risk, properties, required in definitions:
        registry.register(Tool(name=name, description=description,
                               parameters={'type': 'object', 'properties': properties, 'required': required},
                               handler=handler, risk=risk, category='memory',
                               requires_confirmation=risk == Risk.HIGH, never_auto_approve=risk == Risk.HIGH))
