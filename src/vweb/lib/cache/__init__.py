"""Centralized API-response caches.

Import as ``from vweb.lib import cache`` and call ``cache.<domain>.<verb>()``.
Every domain module is built on :mod:`vweb.lib.cache.base`, whose ``cached_fetch``
makes single-flight herd protection the default for all caches.
"""

from __future__ import annotations

from vweb.lib.cache import (
    base,
    blueprint,
    campaign_content,
    character_sheet,
    dicerolls,
    dictionary,
    global_context,
    options,
    statistics,
    system_status,
)

__all__ = [
    "base",
    "blueprint",
    "campaign_content",
    "character_sheet",
    "dicerolls",
    "dictionary",
    "global_context",
    "options",
    "statistics",
    "system_status",
]
