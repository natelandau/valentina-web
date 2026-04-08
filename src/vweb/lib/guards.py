"""Permission guards for view-layer authorization checks.

Centralize role- and company-settings-based permission logic so views and
templates can ask a single question ("can this user do X?") without
duplicating the underlying rules.

All guards fail closed when no user is attached to ``flask.g`` — this
keeps callers like blueprint before-request hooks simple (``if not
is_admin(): abort()``) without a separate null check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from flask import g

if TYPE_CHECKING:
    from vclient.models import Character, User


def _current_user() -> User | None:
    """Return the requesting user, or None when no user is attached to ``g``."""
    return getattr(g, "requesting_user", None)


def is_self(user_id: str) -> bool:
    """Check whether ``user_id`` identifies the requesting user.

    Use for "does the requesting user own this user-scoped resource?" checks
    (profile edits, quickrolls, personal settings) so the rule has one home
    and one name.
    """
    user = _current_user()
    return user is not None and user.id == user_id


def is_admin() -> bool:
    """Check whether the requesting user has the ADMIN role.

    Use for actions reserved strictly for admins (storytellers excluded).
    """
    user = _current_user()
    return user is not None and user.role == "ADMIN"


def is_storyteller() -> bool:
    """Check whether the requesting user is a storyteller or admin.

    Admins are treated as storytellers for every gameplay-facing check.
    Most company-level permission guards short-circuit on this before
    consulting the company settings.
    """
    user = _current_user()
    return user is not None and user.role in ("ADMIN", "STORYTELLER")


def can_manage_campaign() -> bool:
    """Check whether the user may create or modify campaigns, books, or chapters.

    Admins and storytellers always qualify; other players only qualify when
    the company has opened campaign management to everyone.
    """
    if is_storyteller():
        return True

    return g.global_context.company.settings.permission_manage_campaign == "UNRESTRICTED"


def can_grant_experience(target_user_id: str) -> bool:
    """Check whether the user may grant experience to ``target_user_id``.

    "Experience" covers both XP and cool points — both currencies run through
    the same ``permission_grant_xp`` company setting. Privileged users and
    companies with unrestricted granting always pass; otherwise a player may
    only grant experience to themselves.
    """
    if is_storyteller():
        return True

    if g.global_context.company.settings.permission_grant_xp == "UNRESTRICTED":
        return True

    return is_self(target_user_id)


def can_edit_traits_free(character: Character) -> bool:
    """Check whether the user may change traits without spending XP.

    Privileged users always qualify. Otherwise the company setting decides:
    ``UNRESTRICTED`` allows anyone, and ``WITHIN_24_HOURS`` allows free edits
    only while the character is less than a day old.
    """
    if is_storyteller():
        return True

    setting = g.global_context.company.settings.permission_free_trait_changes
    if setting == "UNRESTRICTED":
        return True

    return setting == "WITHIN_24_HOURS" and datetime.now(UTC) - character.date_created < timedelta(
        hours=24
    )


def can_edit_character(character: Character) -> bool:
    """Check whether the user may edit ``character``.

    Privileged users may edit any character; players may only edit their own.
    """
    if is_storyteller():
        return True

    return is_self(character.user_player_id)
