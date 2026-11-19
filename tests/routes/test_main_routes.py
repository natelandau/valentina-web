"""Tests for the index entry rules and the public landing page."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vweb.api_client.testing import CampaignFactory

OLDER = CampaignFactory.build(name="Older", date_modified=datetime(2025, 1, 1, tzinfo=UTC))
NEWER = CampaignFactory.build(name="Newer", date_modified=datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    ("campaigns", "remembered", "expected_location"),
    [
        ([NEWER], None, f"/campaign/{NEWER.id}"),
        ([OLDER, NEWER], OLDER.id, f"/campaign/{OLDER.id}"),
        ([OLDER, NEWER], None, "/home"),
        ([], None, "/home"),
    ],
    ids=["single-campaign", "remembered-campaign", "ambiguous-goes-to-hub", "no-campaigns"],
)
def test_index_sends_member_to_entry_page(
    client, use_context, campaigns: list, remembered: str | None, expected_location: str
) -> None:
    """Verify the index opens the only or remembered campaign, else the company hub."""
    # Given a member with the campaigns and an optionally remembered campaign
    use_context(user_role="PLAYER", campaigns=campaigns)
    if remembered:
        with client.session_transaction() as sess:
            sess["last_campaign_id"] = remembered

    # When visiting the index
    response = client.get("/")

    # Then the member lands on the entry page
    assert response.status_code == 302
    assert response.headers["Location"].endswith(expected_location)


def test_landing_page_is_public_and_mints_no_session(app) -> None:
    """Verify anonymous visitors see the landing page without a session being persisted.

    Each persisted session is a Redis key in production, so bots and crawlers hitting the
    public landing page must not mint one.
    """
    response = app.test_client().get("/")

    assert response.status_code == 200
    set_cookies = response.headers.getlist("Set-Cookie")
    assert not any(cookie.startswith("session=") for cookie in set_cookies), set_cookies


def test_authenticated_page_includes_csrf_header(client, mock_global_context) -> None:
    """Verify logged-in pages emit the HTMX X-CSRFToken header so mutations pass CSRF."""
    campaign = mock_global_context.campaigns[0]

    response = client.get(f"/campaign/{campaign.id}")

    assert response.status_code == 200
    assert "X-CSRFToken" in response.get_data(as_text=True)


def test_development_mode_uses_cookie_sessions(app) -> None:
    """Verify development mode uses cookie sessions instead of Redis."""
    from flask.sessions import SecureCookieSessionInterface

    assert isinstance(app.session_interface, SecureCookieSessionInterface)
