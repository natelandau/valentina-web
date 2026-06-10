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
