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
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

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
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

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
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

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


def test_global_header_renders_app_name_and_campaign_pill(client, mock_global_context) -> None:
    """Verify the global header renders the app name and active campaign pill."""
    # Given an authenticated user with a campaign
    campaign = mock_global_context.campaigns[0]

    # When loading the campaign dashboard
    response = client.get(f"/campaign/{campaign.id}")
    body = response.get_data(as_text=True)

    # Then the new header markup is present
    assert response.status_code == 200
    # App name appears in the header (sm:inline label)
    assert "Test App" in body
    # Campaign overline and active campaign name appear in the pill
    assert ">Campaign<" in body
    assert campaign.name in body
    # User menu pill renders with the user's first name
    assert "Test" in body  # first name from UserFactory.build(name_first="Test", ...)


def test_global_header_has_no_drawer_markup(client, mock_global_context) -> None:
    """Verify the old drawer/sidebar plumbing is absent from rendered pages."""
    # Given an authenticated user with a campaign
    campaign = mock_global_context.campaigns[0]

    # When loading the campaign dashboard
    response = client.get(f"/campaign/{campaign.id}")
    body = response.get_data(as_text=True)

    # Then no drawer classes or mobile-nav IDs remain
    assert response.status_code == 200
    assert "drawer-toggle" not in body
    assert "my-drawer-2" not in body
    assert "drawer-side" not in body


def test_global_header_omits_campaign_switcher_when_no_campaigns(client, mocker) -> None:
    """Verify the campaign switcher is absent when the user has no campaigns."""
    # Given a global context with zero campaigns
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id")
    ctx = GlobalContext(
        company=company,
        users=[user],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

    # When loading the landing index (empty state)
    response = client.get("/")
    body = response.get_data(as_text=True)

    # Then the "Campaign" overline is not rendered
    assert response.status_code == 200
    assert ">Campaign<" not in body
    # And the empty state is still shown
    assert "No campaigns exist yet." in body
