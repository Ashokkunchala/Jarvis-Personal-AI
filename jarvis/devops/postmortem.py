"""Draft a blameless incident post-mortem as Markdown.

Pure text formatting. The caller supplies the facts; nothing is invented, and
sections with no input say so instead of guessing.
"""

from __future__ import annotations

from typing import Any


def _bullets(items: list[str] | None, empty: str) -> str:
    items = [i.strip() for i in (items or []) if i and i.strip()]
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def draft_postmortem(
    title: str,
    summary: str = "",
    impact: str = "",
    timeline: list[str] | None = None,
    root_cause: str = "",
    detection: str = "",
    resolution: str = "",
    action_items: list[str] | None = None,
) -> dict[str, Any]:
    if not title.strip():
        return {"success": False, "error": "A title is required."}
    todo = "_Not provided - fill in before sharing._"
    md = f"""# Post-mortem: {title.strip()}

## Summary
{summary.strip() or todo}

## Impact
{impact.strip() or todo}

## Timeline
{_bullets(timeline, "No timeline provided. Add timestamped events (UTC or IST, say which).")}

## Root cause
{root_cause.strip() or todo}

## Detection
{detection.strip() or todo}

## Resolution
{resolution.strip() or todo}

## What went well / what did not
- _Fill in. Keep it about systems and process, not people._

## Action items
{_bullets(action_items, "None yet. Each item needs an owner and a date.")}
"""
    missing = [name for name, val in (("summary", summary), ("impact", impact), ("root_cause", root_cause), ("detection", detection), ("resolution", resolution)) if not val.strip()]
    if not (timeline or []):
        missing.append("timeline")
    return {"success": True, "markdown": md, "missing_sections": missing}
