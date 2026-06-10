"""Tests for the company hub page."""

from __future__ import annotations

from vclient.testing import CampaignFactory, CompanyFactory

from tests.helpers import build_global_context

LOAD_PATH = "vweb.lib.cache.global_context.load"


def test_hub_requires_auth(app) -> None:
    """Verify unauthenticated visitors are redirected away from the hub."""
    # Given an anonymous client
    client = app.test_client()

    # When visiting the hub
    response = client.get("/home")

    # Then the visitor is redirected (require_auth hook)
    assert response.status_code == 302


def test_hub_renders_masthead_with_stats(client, mocker) -> None:
    """Verify the hub masthead shows company name, description, and counts."""
    # Given a player in a company with two campaigns
    company = CompanyFactory.build(name="Acme Gaming Co.", description="A chronicle group")
    ctx = build_global_context(
        user_role="PLAYER",
        company=company,
        campaigns=CampaignFactory.batch(2),
    )
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    response = client.get("/home")
    body = response.get_data(as_text=True)

    # Then the masthead renders the company identity and stat strip
    assert response.status_code == 200
    assert "Acme Gaming Co." in body
    assert "A chronicle group" in body
    assert "members" in body
    assert "campaigns" in body
    assert "characters" in body


def test_hub_hides_admin_tabs_from_players(client, mocker) -> None:
    """Verify players see no company tab row on the hub."""
    # Given a player
    ctx = build_global_context(user_role="PLAYER", campaigns=CampaignFactory.batch(1))
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then no admin tab links render
    assert "Audit log" not in body
    assert "/admin/users" not in body
    assert "/admin/settings" not in body


def test_hub_shows_admin_tabs_to_admins(client, mocker) -> None:
    """Verify admins see Campaigns, Members, Settings, and Audit log tabs."""
    # Given an admin
    ctx = build_global_context(user_role="ADMIN", campaigns=CampaignFactory.batch(1))
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then all four company tabs render
    assert "Campaigns" in body
    assert "Members" in body
    assert "/admin/users" in body
    assert "/admin/settings" in body
    assert "Audit log" in body


def test_hub_members_tab_shows_pending_badge(client, mocker) -> None:
    """Verify the Members tab pings when users await approval."""
    # Given an admin with pending users
    ctx = build_global_context(
        user_role="ADMIN",
        campaigns=CampaignFactory.batch(1),
        pending_user_count=2,
    )
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then the ping badge animation markup is present
    assert "animate-ping" in body
