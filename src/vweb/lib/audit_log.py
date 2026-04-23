"""Shared audit log helpers.

Used by both the admin audit log page and the shared lazy-loaded audit log card.
Cross-cutting infrastructure per CLAUDE.md's route-centric structure rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from markupsafe import Markup, escape


@dataclass(frozen=True)
class FieldDiff:
    """One field's old/new values, pre-rendered as display HTML."""

    field: str
    old: Markup
    new: Markup


@dataclass(frozen=True)
class OtherEntry:
    """A changes-dict entry whose value didn't match the canonical {old, new} shape."""

    key: str
    value: Markup


def format_change_value(value: Any) -> Markup:
    """Render a single change-dict value as safe HTML for the Old/New panel.

    None becomes a muted em-dash, booleans become Yes/No, lists and dicts become
    pretty-printed JSON inside a <pre> block, and other scalars become
    HTML-escaped strings.

    Args:
        value: The raw change value from an AuditLog.changes dict entry.

    Returns:
        Markup: Safe HTML ready to render without further escaping.
    """
    if value is None:
        return Markup('<em class="opacity-40">—</em>')
    if isinstance(value, bool):
        return Markup("Yes") if value else Markup("No")
    if isinstance(value, (list, dict)):
        pretty = json.dumps(value, indent=2, sort_keys=True, default=str)
        # Escape only chars that matter in HTML text content; leave quotes literal so
        # JSON double-quoted strings remain readable in the rendered <pre> block.
        safe_content = pretty.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # S704: safe because safe_content is built from manual &/</> replacement above,
        # not from untrusted input passed directly — ruff can't statically verify this.
        return Markup(  # noqa: S704
            f'<pre class="text-xs whitespace-pre-wrap break-words">{safe_content}</pre>'
        )
    return escape(str(value))


def split_changes(
    changes: dict[str, Any] | None,
) -> tuple[list[FieldDiff], list[OtherEntry]]:
    """Parse an AuditLog.changes dict into canonical field diffs plus off-shape entries.

    Canonical shape is `{field: {"old": ..., "new": ...}}` (extra keys tolerated).
    Anything that doesn't match — flat scalars, differently-nested dicts — surfaces
    as OtherEntry so nothing is silently dropped.

    Args:
        changes: The raw changes dict from an AuditLog entry, or None.

    Returns:
        A two-tuple of (diffs, others) where diffs contains FieldDiff objects for
        canonical entries and others contains OtherEntry objects for everything else.
    """
    diffs: list[FieldDiff] = []
    others: list[OtherEntry] = []
    if not changes:
        return diffs, others
    for key, value in changes.items():
        if isinstance(value, dict) and {"old", "new"} <= set(value.keys()):
            diffs.append(
                FieldDiff(
                    field=key,
                    old=format_change_value(value["old"]),
                    new=format_change_value(value["new"]),
                )
            )
        else:
            others.append(OtherEntry(key=key, value=format_change_value(value)))
    return diffs, others
