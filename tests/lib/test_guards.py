"""Unit tests for permission guard helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from flask import g

from vweb.api_client.testing import CharacterFactory, CompanyFactory, UserFactory
from vweb.lib.cache.global_context import GlobalContext
from vweb.lib.guards import (
    can_edit_character,
    can_edit_trackers,
    can_edit_traits_free,
    can_grant_experience,
    can_manage_campaign,
    can_manage_npcs,
    is_active_role,
    is_admin,
    is_approved_user,
    is_self,
    is_storyteller,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from flask import Flask


@pytest.fixture
def guard_ctx(app: Flask) -> Iterator[Callable[..., None]]:
    """Enter an app context and seed `g.requesting_user` and `g.global_context`.

    Returns a setup function so each test can specify the role and permission
    settings it cares about without rebuilding the fixture plumbing.
    """

    def _setup(
        *,
        role: str = "PLAYER",
        user_id: str = "user-1",
        permission_manage_campaign: Any = "STORYTELLER",
        permission_manage_npc: Any = "STORYTELLER",
        permission_grant_xp: Any = "STORYTELLER",
        permission_free_trait_changes: Any = "STORYTELLER",
    ) -> None:
        company = CompanyFactory.build()
        company.settings.permission_manage_campaign = permission_manage_campaign
        company.settings.permission_manage_npc = permission_manage_npc
        company.settings.permission_grant_xp = permission_grant_xp
        company.settings.permission_free_trait_changes = permission_free_trait_changes

        g.requesting_user = UserFactory.build(id=user_id, role=role)
        g.global_context = GlobalContext(
            company=company,
            users=[g.requesting_user],
            campaigns=[],
            characters_by_campaign={},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )

    with app.test_request_context():
        yield _setup


_ROLES = ("ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED")


def test_is_self_matches_requesting_user(guard_ctx) -> None:
    """Verify is_self is True only for the requesting user's id, never for None."""
    guard_ctx(role="PLAYER", user_id="me")

    assert is_self("me") is True
    assert is_self("someone-else") is False
    assert is_self(None) is False


@pytest.mark.parametrize("role", _ROLES)
def test_role_guards(guard_ctx, role) -> None:
    """Verify which roles count as admin, storyteller, and approved."""
    guard_ctx(role=role)

    assert is_admin() is (role == "ADMIN")
    assert is_storyteller() is (role in {"ADMIN", "STORYTELLER"})
    assert is_approved_user() is (role in {"ADMIN", "STORYTELLER", "PLAYER"})


@pytest.mark.parametrize("role", [*_ROLES, None])
def test_is_active_role(role) -> None:
    """Verify is_active_role passes usable membership roles and rejects the rest."""
    assert is_active_role(role) is (role in {"ADMIN", "STORYTELLER", "PLAYER"})


@pytest.mark.parametrize(
    "guard",
    [is_admin, is_storyteller, is_approved_user, lambda: is_self("user-1")],
    ids=["is_admin", "is_storyteller", "is_approved_user", "is_self"],
)
def test_guards_fail_closed_when_logged_out(app: Flask, guard) -> None:
    """Verify user guards deny when no user is attached to g."""
    with app.test_request_context():
        assert guard() is False


@pytest.mark.parametrize(
    ("guard", "setting_name"),
    [
        (can_manage_campaign, "permission_manage_campaign"),
        (can_manage_npcs, "permission_manage_npc"),
    ],
)
@pytest.mark.parametrize(
    ("role", "setting", "expected"),
    [
        ("ADMIN", "STORYTELLER", True),
        ("STORYTELLER", "STORYTELLER", True),
        ("PLAYER", "UNRESTRICTED", True),
        ("PLAYER", "STORYTELLER", False),
    ],
)
def test_company_setting_guards(guard_ctx, guard, setting_name, role, setting, expected) -> None:
    """Verify privileged roles bypass the setting and players need UNRESTRICTED."""
    guard_ctx(role=role, **{setting_name: setting})

    assert guard() is expected


@pytest.mark.parametrize(
    ("role", "setting", "target", "expected"),
    [
        ("ADMIN", "STORYTELLER", "someone-else", True),
        ("STORYTELLER", "STORYTELLER", "someone-else", True),
        ("PLAYER", "UNRESTRICTED", "someone-else", True),
        ("PLAYER", "PLAYER", "me", True),
        ("PLAYER", "PLAYER", "someone-else", False),
        ("PLAYER", "STORYTELLER", "me", False),
        ("PLAYER", "STORYTELLER", "someone-else", False),
    ],
)
def test_can_grant_experience(guard_ctx, role, setting, target, expected) -> None:
    """Verify who may grant experience to whom under each company setting."""
    guard_ctx(role=role, user_id="me", permission_grant_xp=setting)

    assert can_grant_experience(target) is expected


@pytest.mark.parametrize(
    ("role", "setting", "character_type", "age", "expected"),
    [
        ("ADMIN", "STORYTELLER", "PLAYER", timedelta(days=30), True),
        ("STORYTELLER", "STORYTELLER", "PLAYER", timedelta(days=30), True),
        ("PLAYER", "UNRESTRICTED", "PLAYER", timedelta(days=30), True),
        ("PLAYER", "WITHIN_24_HOURS", "PLAYER", timedelta(hours=1), True),
        ("PLAYER", "WITHIN_24_HOURS", "PLAYER", timedelta(hours=25), False),
        ("PLAYER", "STORYTELLER", "PLAYER", timedelta(0), False),
        ("PLAYER", "STORYTELLER", "NPC", timedelta(days=2), True),
        ("PLAYER", "STORYTELLER", "STORYTELLER", timedelta(days=2), True),
    ],
)
def test_can_edit_traits_free(guard_ctx, role, setting, character_type, age, expected) -> None:
    """Verify free trait edits: privileged always, players per setting, non-player types always."""
    guard_ctx(role=role, permission_free_trait_changes=setting)
    character = CharacterFactory.build(type=character_type, date_created=datetime.now(UTC) - age)

    assert can_edit_traits_free(character) is expected


# Columns: role, NPC setting, character type, owner, can_edit_character, can_edit_trackers
_EDIT_MATRIX = [
    ("ADMIN", "STORYTELLER", "PLAYER", "someone-else", True, True),
    ("STORYTELLER", "STORYTELLER", "PLAYER", "someone-else", True, True),
    ("ADMIN", "STORYTELLER", "NPC", None, True, True),
    ("STORYTELLER", "STORYTELLER", "NPC", None, True, True),
    ("PLAYER", "STORYTELLER", "PLAYER", "me", True, True),
    ("PLAYER", "STORYTELLER", "PLAYER", "someone-else", False, False),
    ("PLAYER", "UNRESTRICTED", "NPC", "someone-else", True, False),
    ("PLAYER", "STORYTELLER", "NPC", "me", False, True),
    ("PLAYER", "STORYTELLER", "NPC", None, False, False),
    ("PLAYER", "UNRESTRICTED", "STORYTELLER", "me", False, True),
]


@pytest.mark.parametrize(
    ("role", "npc_setting", "character_type", "owner", "can_edit", "can_track"), _EDIT_MATRIX
)
def test_character_edit_guards(
    guard_ctx, *, role, npc_setting, character_type, owner, can_edit, can_track
) -> None:
    """Verify character edits follow type and NPC setting, and tracker edits follow ownership."""
    guard_ctx(role=role, user_id="me", permission_manage_npc=npc_setting)
    character = CharacterFactory.build(user_player_id=owner, type=character_type)

    assert can_edit_character(character) is can_edit
    assert can_edit_trackers(character) is can_track
