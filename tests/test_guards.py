"""Unit tests for permission guard helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from flask import g
from vclient.testing import CharacterFactory, CompanyFactory, UserFactory

from vweb.lib.global_context import GlobalContext
from vweb.lib.guards import (
    can_edit_character,
    can_edit_traits_free,
    can_grant_experience,
    can_manage_campaign,
    is_admin,
    is_self,
    is_storyteller,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


@pytest.fixture
def guard_ctx(app: Flask) -> Callable[..., None]:
    """Enter an app context and seed `g.requesting_user` and `g.global_context`.

    Returns a setup function so each test can specify the role and permission
    settings it cares about without rebuilding the fixture plumbing.
    """

    def _setup(
        *,
        role: str = "PLAYER",
        user_id: str = "user-1",
        permission_manage_campaign: str | None = "STORYTELLER",
        permission_grant_xp: str | None = "STORYTELLER",
        permission_free_trait_changes: str | None = "STORYTELLER",
    ) -> None:
        company = CompanyFactory.build()
        company.settings.permission_manage_campaign = permission_manage_campaign
        company.settings.permission_grant_xp = permission_grant_xp
        company.settings.permission_free_trait_changes = permission_free_trait_changes

        g.requesting_user = UserFactory.build(id=user_id, role=role)
        g.global_context = GlobalContext(
            company=company,
            users=[g.requesting_user],
            campaigns=[],
            books_by_campaign={},
            characters_by_campaign={},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )

    with app.test_request_context():
        yield _setup


def test_is_self_matches_requesting_user(guard_ctx) -> None:
    """Verify is_self returns True only when the given id matches the requesting user."""
    # Given a requesting user with a known id
    guard_ctx(role="PLAYER", user_id="me")

    # When / Then
    assert is_self("me") is True
    assert is_self("someone-else") is False


@pytest.mark.parametrize(
    ("role", "expected"),
    [("ADMIN", True), ("STORYTELLER", False), ("PLAYER", False), ("UNAPPROVED", False)],
)
def test_is_admin_role_matrix(guard_ctx, role, expected) -> None:
    """Verify is_admin only returns True for the ADMIN role."""
    # Given a user with the parametrized role
    guard_ctx(role=role)

    # When / Then
    assert is_admin() is expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [("ADMIN", True), ("STORYTELLER", True), ("PLAYER", False), ("UNAPPROVED", False)],
)
def test_is_storyteller_role_matrix(guard_ctx, role, expected) -> None:
    """Verify is_storyteller treats ADMIN and STORYTELLER as privileged."""
    # Given a user with the parametrized role
    guard_ctx(role=role)

    # When / Then
    assert is_storyteller() is expected


@pytest.mark.parametrize("role", ["ADMIN", "STORYTELLER"])
def test_can_manage_campaign_privileged_roles_bypass_setting(guard_ctx, role) -> None:
    """Verify privileged roles bypass the restricted manage-campaign setting."""
    # Given a privileged user and a restrictive company setting
    guard_ctx(role=role, permission_manage_campaign="STORYTELLER")

    # When / Then
    assert can_manage_campaign() is True


def test_can_manage_campaign_player_with_unrestricted_setting(guard_ctx) -> None:
    """Verify players may manage campaigns when the company is UNRESTRICTED."""
    # Given a player and an unrestricted company setting
    guard_ctx(role="PLAYER", permission_manage_campaign="UNRESTRICTED")

    # When / Then
    assert can_manage_campaign() is True


def test_can_manage_campaign_player_restricted(guard_ctx) -> None:
    """Verify players may not manage campaigns when the setting is restrictive."""
    # Given a player and a storyteller-only setting
    guard_ctx(role="PLAYER", permission_manage_campaign="STORYTELLER")

    # When / Then
    assert can_manage_campaign() is False


@pytest.mark.parametrize("role", ["ADMIN", "STORYTELLER"])
def test_can_grant_experience_privileged_roles_to_anyone(guard_ctx, role) -> None:
    """Verify privileged users may grant XP to any target user."""
    # Given a privileged user
    guard_ctx(role=role, user_id="me", permission_grant_xp="STORYTELLER")

    # When / Then
    assert can_grant_experience("someone-else") is True


def test_can_grant_experience_unrestricted_setting(guard_ctx) -> None:
    """Verify any user may grant XP when the company setting is UNRESTRICTED."""
    # Given a player and UNRESTRICTED grant-xp setting
    guard_ctx(role="PLAYER", user_id="me", permission_grant_xp="UNRESTRICTED")

    # When / Then
    assert can_grant_experience("someone-else") is True


def test_can_grant_experience_player_to_self(guard_ctx) -> None:
    """Verify players may grant XP to themselves under restrictive settings."""
    # Given a restricted player
    guard_ctx(role="PLAYER", user_id="me", permission_grant_xp="STORYTELLER")

    # When / Then
    assert can_grant_experience("me") is True


def test_can_grant_experience_player_to_other_denied(guard_ctx) -> None:
    """Verify players may not grant XP to other users under restrictive settings."""
    # Given a restricted player
    guard_ctx(role="PLAYER", user_id="me", permission_grant_xp="STORYTELLER")

    # When / Then
    assert can_grant_experience("someone-else") is False


@pytest.mark.parametrize("role", ["ADMIN", "STORYTELLER"])
def test_can_edit_traits_free_privileged(guard_ctx, role) -> None:
    """Verify privileged roles always edit traits for free regardless of age."""
    # Given a privileged user and an old character
    guard_ctx(role=role, permission_free_trait_changes="STORYTELLER")
    character = CharacterFactory.build(date_created=datetime.now(UTC) - timedelta(days=30))

    # When / Then
    assert can_edit_traits_free(character) is True


def test_can_edit_traits_free_unrestricted_setting(guard_ctx) -> None:
    """Verify any user edits traits for free when the setting is UNRESTRICTED."""
    # Given a player and unrestricted setting
    guard_ctx(role="PLAYER", permission_free_trait_changes="UNRESTRICTED")
    character = CharacterFactory.build(date_created=datetime.now(UTC) - timedelta(days=30))

    # When / Then
    assert can_edit_traits_free(character) is True


def test_can_edit_traits_free_within_24h_fresh_character(guard_ctx) -> None:
    """Verify WITHIN_24_HOURS allows free edits for a character under a day old."""
    # Given a player and a freshly-created character
    guard_ctx(role="PLAYER", permission_free_trait_changes="WITHIN_24_HOURS")
    character = CharacterFactory.build(date_created=datetime.now(UTC) - timedelta(hours=1))

    # When / Then
    assert can_edit_traits_free(character) is True


def test_can_edit_traits_free_within_24h_old_character(guard_ctx) -> None:
    """Verify WITHIN_24_HOURS denies free edits for a character older than a day."""
    # Given a player and an old character
    guard_ctx(role="PLAYER", permission_free_trait_changes="WITHIN_24_HOURS")
    character = CharacterFactory.build(date_created=datetime.now(UTC) - timedelta(hours=25))

    # When / Then
    assert can_edit_traits_free(character) is False


def test_can_edit_traits_free_restricted_setting(guard_ctx) -> None:
    """Verify a restrictive setting denies free trait edits for players."""
    # Given a player and a storyteller-only setting
    guard_ctx(role="PLAYER", permission_free_trait_changes="STORYTELLER")
    character = CharacterFactory.build(date_created=datetime.now(UTC))

    # When / Then
    assert can_edit_traits_free(character) is False


@pytest.mark.parametrize("role", ["ADMIN", "STORYTELLER"])
def test_can_edit_character_privileged(guard_ctx, role) -> None:
    """Verify privileged users may edit any character."""
    # Given a privileged user and a character owned by someone else
    guard_ctx(role=role, user_id="me")
    character = CharacterFactory.build(user_player_id="someone-else")

    # When / Then
    assert can_edit_character(character) is True


def test_can_edit_character_owner(guard_ctx) -> None:
    """Verify players may edit their own characters."""
    # Given a player and their own character
    guard_ctx(role="PLAYER", user_id="me")
    character = CharacterFactory.build(user_player_id="me")

    # When / Then
    assert can_edit_character(character) is True


def test_can_edit_character_non_owner_denied(guard_ctx) -> None:
    """Verify players may not edit characters owned by other users."""
    # Given a player and someone else's character
    guard_ctx(role="PLAYER", user_id="me")
    character = CharacterFactory.build(user_player_id="someone-else")

    # When / Then
    assert can_edit_character(character) is False
