"""Tests for the company hub page."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client.testing import CampaignFactory, CompanyFactory

if TYPE_CHECKING:
    from vweb.api_client.constants import ManageCampaignPermission


# The hook every create-campaign affordance uses to open the creation modal.
CREATE_CAMPAIGN_TRIGGER = "getElementById('campaign-create-modal').showModal()"


def test_hub_requires_auth(app) -> None:
    """Verify unauthenticated visitors are redirected away from the hub."""
    # Given an anonymous client
    client = app.test_client()

    # When visiting the hub
    response = client.get("/home")

    # Then the visitor is redirected (require_auth hook)
    assert response.status_code == 302
    assert "/home" not in response.headers["Location"]


def test_hub_shows_company_identity(client, use_context) -> None:
    """Verify the hub shows the company's name and description."""
    # Given a player in a company with a name and description
    company = CompanyFactory.build(name="Acme Gaming Co.", description="A chronicle group")
    use_context(user_role="PLAYER", company=company, campaigns=CampaignFactory.batch(2))

    # When visiting the hub
    response = client.get("/home")
    body = response.get_data(as_text=True)

    # Then the company identity renders
    assert response.status_code == 200
    assert "Acme Gaming Co." in body
    assert "A chronicle group" in body


@pytest.mark.parametrize(
    ("role", "sees_admin_tabs"),
    [("PLAYER", False), ("STORYTELLER", False), ("ADMIN", True)],
)
def test_hub_admin_tabs_only_for_admins(
    client, use_context, role: str, *, sees_admin_tabs: bool
) -> None:
    """Verify only admins get links to the members, settings, and audit log pages."""
    # Given a user with the role
    use_context(user_role=role, campaigns=CampaignFactory.batch(1))

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then the admin links render only for admins
    for href in ('href="/admin/users"', 'href="/admin/settings"', 'href="/admin"'):
        assert (href in body) is sees_admin_tabs


def test_hub_lists_campaign_cards(client, use_context) -> None:
    """Verify the hub renders a linked card per campaign."""
    # Given two campaigns
    blood = CampaignFactory.build(name="Blood and Smoke")
    nights = CampaignFactory.build(name="Chicago Nights")
    use_context(user_role="PLAYER", campaigns=[blood, nights])

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then both campaigns render as links
    assert "Blood and Smoke" in body
    assert "Chicago Nights" in body
    assert f"/campaign/{blood.id}" in body
    assert f"/campaign/{nights.id}" in body


@pytest.mark.parametrize("num_campaigns", [0, 1], ids=["empty", "with-campaigns"])
@pytest.mark.parametrize(
    ("role", "permission", "can_create"),
    [
        ("PLAYER", "STORYTELLER", False),
        ("PLAYER", "UNRESTRICTED", True),
        ("STORYTELLER", "STORYTELLER", True),
        ("ADMIN", "STORYTELLER", True),
    ],
)
def test_hub_create_campaign_respects_permission(
    client,
    use_context,
    role: str,
    permission: ManageCampaignPermission,
    num_campaigns: int,
    *,
    can_create: bool,
) -> None:
    """Verify the create-campaign affordance renders only for users who may manage campaigns."""
    # Given a user with the role in a company with the campaign permission
    company = CompanyFactory.build(name="Test Company")
    company.settings.permission_manage_campaign = permission
    use_context(user_role=role, company=company, campaigns=CampaignFactory.batch(num_campaigns))

    # When visiting the hub
    body = client.get("/home").get_data(as_text=True)

    # Then a way to create a campaign exists only when permitted
    assert (CREATE_CAMPAIGN_TRIGGER in body) is can_create
