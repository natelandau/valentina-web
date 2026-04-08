"""Tests for main blueprint routes."""

from datetime import UTC, datetime

from vclient.testing import (
    CampaignFactory,
    CompanyFactory,
    UserFactory,
)

from vweb.lib.global_context import GlobalContext


def test_index_redirects_authenticated_user_to_campaign(client, mock_global_context) -> None:
    """Verify authenticated users are redirected to a campaign page."""
    # Given an authenticated user with campaigns
    campaign = mock_global_context.campaigns[0]

    # When visiting the index
    response = client.get("/")

    # Then redirected to the most recent campaign
    assert response.status_code == 302
    assert f"/campaign/{campaign.id}" in response.headers["Location"]


def test_index_redirects_to_session_campaign(client, mocker) -> None:
    """Verify the index redirects to the session-stored campaign."""
    # Given two campaigns where the older one is in the session
    older = CampaignFactory.build(
        name="Older",
        date_modified=datetime(2025, 1, 1, tzinfo=UTC),
    )
    newer = CampaignFactory.build(
        name="Newer",
        date_modified=datetime(2026, 1, 1, tzinfo=UTC),
    )
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    ctx = GlobalContext(
        company=company,
        users=[user],
        campaigns=[older, newer],
        characters_by_campaign={older.id: [], newer.id: []},
        books_by_campaign={older.id: [], newer.id: []},
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mocker.patch("vweb.app.load_global_context", return_value=ctx)

    # Given the older campaign is in the session
    with client.session_transaction() as sess:
        sess["last_campaign_id"] = older.id

    # When visiting the index
    response = client.get("/")

    # Then redirected to the session campaign, not the newest
    assert response.status_code == 302
    assert f"/campaign/{older.id}" in response.headers["Location"]


def test_index_defaults_to_most_recent_campaign(client, mocker) -> None:
    """Verify the index defaults to the most recently modified campaign when no session."""
    # Given two campaigns with different modification dates
    older = CampaignFactory.build(
        name="Older",
        date_modified=datetime(2025, 1, 1, tzinfo=UTC),
    )
    newer = CampaignFactory.build(
        name="Newer",
        date_modified=datetime(2026, 1, 1, tzinfo=UTC),
    )
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    ctx = GlobalContext(
        company=company,
        users=[user],
        campaigns=[older, newer],
        characters_by_campaign={older.id: [], newer.id: []},
        books_by_campaign={older.id: [], newer.id: []},
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mocker.patch("vweb.app.load_global_context", return_value=ctx)

    # When visiting the index (no session campaign)
    response = client.get("/")

    # Then redirected to the newer campaign
    assert response.status_code == 302
    assert f"/campaign/{newer.id}" in response.headers["Location"]


def test_index_unauthenticated_returns_200(app) -> None:
    """Verify unauthenticated users see the landing page at /."""
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_index_no_campaigns_shows_empty_state(client, mocker) -> None:
    """Verify the empty state message when no campaigns exist."""
    # Given a global context with no campaigns
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    ctx = GlobalContext(
        company=company,
        users=[user],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mocker.patch("vweb.app.load_global_context", return_value=ctx)

    # When visiting the index
    response = client.get("/")
    body = response.get_data(as_text=True)

    # Then the empty state is shown
    assert response.status_code == 200
    assert "No campaigns exist yet." in body
    assert "Create one." in body


def test_development_mode_uses_cookie_sessions(app) -> None:
    """Verify development mode uses default cookie-based sessions."""
    from flask.sessions import SecureCookieSessionInterface

    assert isinstance(app.session_interface, SecureCookieSessionInterface)
