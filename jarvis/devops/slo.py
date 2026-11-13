"""Offline event-ratio SLO arithmetic, not a live monitor or SLA decision."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext

SOURCE = 'https://sre.google/workbook/implementing-slos/'


def _instant(value):
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError('Window boundaries must be ISO date-times with timezones.')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError('Missing timezone')
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ValueError('Window boundaries must be valid ISO date-times with timezones.') from exc


def _target(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)) or len(str(value)) > 40:
        raise ValueError('target_percent must be a finite number above 0 and at most 100.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('target_percent must be numeric.') from exc
    if not result.is_finite() or not 0 < result <= 100 or result.as_tuple().exponent < -12:
        raise ValueError('target_percent must be above 0 and at most 100, with at most 12 decimal places.')
    return result


def review_slo(windows, target_percent, complete_window, event_definition):
    if complete_window is not True:
        raise ValueError('Confirm complete_window=true for a finished, complete evaluation window.')
    if not isinstance(event_definition, str) or not 1 <= len(event_definition.strip()) <= 500:
        raise ValueError('Describe what counts as a good event and the eligible population, up to 500 characters.')
    if not isinstance(windows, list) or not 1 <= len(windows) <= 1000:
        raise ValueError('Supply 1-1000 contiguous, nonoverlapping event-count windows.')
    target = _target(target_percent)
    rows = []
    now = datetime.now(UTC)
    for row in windows:
        if not isinstance(row, dict):
            raise ValueError('Every window must be an object.')
        start, end = _instant(row.get('start')), _instant(row.get('end'))
        if end <= start or end > now:
            raise ValueError('Each window needs start < end and an end no later than now.')
        total, good = row.get('total_events'), row.get('good_events')
        if type(total) is not int or type(good) is not int or not 0 <= good <= total <= 10**18:
            raise ValueError('Counts must be integers with 0 <= good_events <= total_events <= 10^18.')
        rows.append((start, end, total, good))
    rows.sort(key=lambda row: row[0])
    if any(b[0] != a[1] for a, b in zip(rows, rows[1:])):
        raise ValueError('Windows must be exactly contiguous without overlaps, duplicates or gaps.')
    total, good = sum(row[2] for row in rows), sum(row[3] for row in rows)
    bad = total - good
    # Counts are weighted by events, never averaged from per-window percentages.
    with localcontext() as ctx:
        ctx.prec = 60
        allowed = Decimal(total) * (100 - target) / 100
        remaining = allowed - bad
        sli = Decimal(good) * 100 / total if total else None
        consumed = Decimal(bad) * 100 / allowed if allowed else None
        # Compare exact integer/Decimal quantities, not rounded display ratios.
        met = Decimal(good) * 100 >= Decimal(total) * target if total else None
        return {
            'window_start': rows[0][0].isoformat(), 'window_end': rows[-1][1].isoformat(),
            'windows_reviewed': len(rows), 'event_definition': event_definition.strip(),
            'target_percent': str(target), 'total_events': total, 'good_events': good, 'bad_events': bad,
            'sli_percent': str(sli) if sli is not None else None,
            'objective_met': met, 'status': ('met' if met else 'not_met') if total else 'no_data',
            'allowed_bad_events': str(allowed), 'remaining_bad_events': str(remaining),
            'budget_consumed_percent': format(consumed, 'f') if consumed is not None else None,
            'zero_error_budget': target == 100, 'budget_exceeded': bool(total and remaining < 0),
            'source': SOURCE,
            'limits': 'Arithmetic over supplied completed event counts only. Completeness, event semantics, freshness and measurement coverage are asserted by the caller, not verified. Not a live monitor, contractual SLA decision, alert, time-based uptime calculation, forecast, burn-rate alerting or root-cause analysis. Zero events means no data, not 100% success. Fractional allowed events are mathematical budgets, not permission for a fractional failure. A 100% target has zero budget, so consumption percentage is undefined. No network, account access, files, notifications or changes.',
        }


def register_slo_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    registry.register(Tool(
        name='review_slo_budget',
        description='Offline event-ratio SLO and error-budget calculation from completed contiguous count windows. No live monitoring, SLA conclusion, alerts or changes. Zero events is no data.',
        parameters={'type': 'object', 'properties': {
            'windows': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'start': {'type': 'string'}, 'end': {'type': 'string'},
                'total_events': {'type': 'integer'}, 'good_events': {'type': 'integer'}},
                'required': ['start', 'end', 'total_events', 'good_events']}},
            'target_percent': {'type': 'string', 'description': 'Exact percentage above 0 and at most 100, e.g. 99.9'},
            'complete_window': {'type': 'boolean'},
            'event_definition': {'type': 'string', 'description': 'Explicit definition of good events and eligible population. No private values.'}},
            'required': ['windows', 'target_percent', 'complete_window', 'event_definition']},
        handler=review_slo, risk=Risk.SAFE, category='devops'))
