"""Settings live in :mod:`app.core.config`; this module re-exports them.

Kept so existing ``from app.config import Settings, get_settings`` imports
continue to resolve to the single shared configuration object.
"""

from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
