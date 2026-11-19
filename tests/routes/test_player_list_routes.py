"""Tests for the campaign-scoped player list."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import g

from vweb.api_client.testing import CampaignFactory, CharacterFactory, CompanyFactory, UserFactory
from vweb.lib.cache.global_context import GlobalContext
from vweb.routes.player_list.services import (
    HAS_CHARACTERS_NO,
    HAS_CHARACTERS_YES,
    build_filter_options,
    filter_players,
    get_all_players,
)

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

    from vweb.api_client.models import User

CAMPAIGN_ID = "camp-1"


@pytest.fixture
def roster() -> list[User]:
    """Build a roster: the session player, a storyteller with a character, and an admin."""
    return [
        UserFactory.build(id="test-user-id", username="mallory", role="PLAYER"),
        UserFactory.build(id="st-1", username="Bob", role="STORYTELLER"),
        UserFactory.build(id="admin-1", username="alice", role="ADMIN"),
    ]


@pytest.fixture
def player_context(use_context, roster: list[User]) -> GlobalContext:
    """Serve a context where only the storyteller owns a character in the campaign."""
    campaign = CampaignFactory.build(id=CAMPAIGN_ID, name="Test Campaign")
    ctx = GlobalContext(
        company=CompanyFactory.build(),
        users=roster,
        campaigns=[campaign],
        characters_by_campaign={
            CAMPAIGN_ID: [
                CharacterFactory.build(campaign_id=CAMPAIGN_ID, user_player_id="st-1"),
                CharacterFactory.build(campaign_id=CAMPAIGN_ID, user_player_id=None),
            ]
        },
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    return use_context(ctx)


def _listed_user_ids(body: str, roster: list[User]) -> set[str]:
    """Return the ids of roster users whose profile link appears in the page."""
    return {user.id for user in roster if f"/profile/{user.id}" in body}


class TestPlayerListRoutes:
    """Wiring for the player list page and its filtered HTMX list."""

    @pytest.mark.usefixtures("player_context")
    def test_page_lists_every_company_member(self, client: FlaskClient, roster: list[User]) -> None:
        """Verify any member sees the whole roster and the campaign is remembered."""
        response = client.get(f"/campaign/{CAMPAIGN_ID}/players")

        assert response.status_code == 200
        assert _listed_user_ids(response.get_data(as_text=True), roster) == {
            "test-user-id",
            "st-1",
            "admin-1",
        }
        with client.session_transaction() as sess:
            assert sess["last_campaign_id"] == CAMPAIGN_ID

    @pytest.mark.usefixtures("player_context")
    @pytest.mark.parametrize(
        ("query", "expected_ids"),
        [
            ("", {"test-user-id", "st-1", "admin-1"}),
            ("?role=ADMIN", {"admin-1"}),
            ("?has_characters=yes", {"st-1"}),
            ("?role=PLAYER&has_characters=no", {"test-user-id"}),
        ],
        ids=["no-filters", "role", "has-characters", "combined"],
    )
    def test_list_partial_applies_query_filters(
        self, client: FlaskClient, roster: list[User], query: str, expected_ids: set[str]
    ) -> None:
        """Verify the HTMX list shows only the members matching the filter query."""
        response = client.get(
            f"/campaign/{CAMPAIGN_ID}/players/list{query}", headers={"HX-Request": "true"}
        )

        assert response.status_code == 200
        assert _listed_user_ids(response.get_data(as_text=True), roster) == expected_ids

    @pytest.mark.usefixtures("player_context")
    @pytest.mark.parametrize("suffix", ["", "/list"], ids=["page", "list"])
    def test_campaign_outside_users_context_returns_404(
        self, client: FlaskClient, suffix: str
    ) -> None:
        """Verify the player list of a campaign the user cannot see returns 404."""
        assert client.get(f"/campaign/not-mine/players{suffix}").status_code == 404


class TestPlayerListServices:
    """Unit tests for the roster ordering and filters."""

    def test_roster_sorted_by_username_ignoring_case(
        self, app: Flask, player_context: GlobalContext
    ) -> None:
        """Verify the roster is sorted A-Z by username regardless of case."""
        with app.test_request_context():
            g.global_context = player_context
            assert [u.username for u in get_all_players()] == ["alice", "Bob", "mallory"]

    @pytest.mark.parametrize(
        ("role", "has_characters", "expected_ids"),
        [
            (None, None, ["test-user-id", "st-1", "admin-1"]),
            ("STORYTELLER", None, ["st-1"]),
            (None, HAS_CHARACTERS_YES, ["st-1"]),
            (None, HAS_CHARACTERS_NO, ["test-user-id", "admin-1"]),
            ("ADMIN", HAS_CHARACTERS_YES, []),
            (None, "maybe", ["test-user-id", "st-1", "admin-1"]),
        ],
        ids=["none", "role", "with-characters", "without-characters", "combined", "unknown-value"],
    )
    def test_filter_players(
        self,
        app: Flask,
        player_context: GlobalContext,
        roster: list[User],
        role: str | None,
        has_characters: str | None,
        expected_ids: list[str],
    ) -> None:
        """Verify role and has-characters filters combine, and unknown filter values are ignored."""
        with app.test_request_context():
            g.global_context = player_context
            result = filter_players(roster, CAMPAIGN_ID, role=role, has_characters=has_characters)

        assert [u.id for u in result] == expected_ids

    def test_filter_options_are_distinct_sorted_roles(self, roster: list[User]) -> None:
        """Verify the role filter offers each role in the roster once, sorted."""
        roster.append(UserFactory.build(role="PLAYER"))

        assert build_filter_options(roster) == ["ADMIN", "PLAYER", "STORYTELLER"]
