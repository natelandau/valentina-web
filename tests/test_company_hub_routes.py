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


def test_hub_lists_campaign_cards(client, mocker) -> None:
    """Verify the hub renders a linked card per campaign with stats."""
    # Given two campaigns with known names, counts, and threat levels
    blood = CampaignFactory.build(
        name="Blood and Smoke",
        num_books=3,
        num_player_characters=5,
        danger=3,
        desperation=0,
    )
    nights = CampaignFactory.build(name="Chicago Nights", num_books=1, num_player_characters=2)
    ctx = build_global_context(user_role="PLAYER", campaigns=[blood, nights])
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then both campaigns render as links with their stats
    assert "Blood and Smoke" in body
    assert "Chicago Nights" in body
    assert f"/campaign/{blood.id}" in body
    assert f"/campaign/{nights.id}" in body
    assert "3 books" in body
    # And danger/desperation badges render even at zero
    assert "Danger 3" in body
    assert "Desperation 0" in body


def test_hub_create_card_respects_permission(client, mocker) -> None:
    """Verify the New Campaign card renders only for users who may manage campaigns."""
    # Given a player in a company restricted to storytellers
    company = CompanyFactory.build(name="Test Company")
    company.settings.permission_manage_campaign = "STORYTELLER"
    ctx = build_global_context(
        user_role="PLAYER", company=company, campaigns=CampaignFactory.batch(1)
    )
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then no create affordance renders
    assert "New Campaign" not in body


def test_hub_create_card_for_unrestricted_company(client, mocker) -> None:
    """Verify players get the create card when campaign management is unrestricted."""
    # Given a player in an unrestricted company
    company = CompanyFactory.build(name="Test Company")
    company.settings.permission_manage_campaign = "UNRESTRICTED"
    ctx = build_global_context(
        user_role="PLAYER", company=company, campaigns=CampaignFactory.batch(1)
    )
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then the create card renders
    assert "New Campaign" in body


def test_hub_empty_state_for_manager(client, mocker) -> None:
    """Verify managers with zero campaigns see a create call-to-action."""
    # Given an admin with no campaigns
    ctx = build_global_context(user_role="ADMIN", campaigns=[])
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then the create-first-campaign empty state renders
    assert "Create your first campaign" in body


def test_hub_empty_state_for_player(client, mocker) -> None:
    """Verify players with zero campaigns see guidance instead of a create button."""
    # Given a player with no campaigns in a restricted company
    company = CompanyFactory.build(name="Test Company")
    company.settings.permission_manage_campaign = "STORYTELLER"
    ctx = build_global_context(user_role="PLAYER", company=company, campaigns=[])
    mocker.patch(LOAD_PATH, return_value=ctx)

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then the ask-your-storyteller empty state renders
    assert "storyteller" in body
    assert "New Campaign" not in body


def test_campaign_nav_has_no_admin_tab(client, mocker) -> None:
    """Verify the campaign section nav no longer offers an Admin tab, even to admins."""
    # Given an admin viewing a campaign page
    ctx = build_global_context(user_role="ADMIN")
    mocker.patch(LOAD_PATH, return_value=ctx)
    campaign = ctx.campaigns[0]

    # When loading the campaign overview
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then the section nav items exclude Admin (the header dropdown still links /admin)
    assert '"key": "admin"' not in body
    assert '"label": "Admin"' not in body
