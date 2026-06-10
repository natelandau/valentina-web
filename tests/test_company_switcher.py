"""Tests for the header company switcher."""

from __future__ import annotations

from tests.helpers import build_global_context

LOAD_PATH = "vweb.lib.cache.global_context.load"


def test_header_renders_company_pill(client, mock_global_context) -> None:
    """Verify the header shows the company pill with overline and name."""
    # Given an authenticated user with a campaign
    campaign = mock_global_context.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then the company pill renders with its overline label and name
    assert ">Company<" in body
    assert "Test Company" in body


def test_company_monogram_has_accessible_label(client, mock_global_context) -> None:
    """Verify the mobile monogram chip carries the full company name for a11y."""
    # Given an authenticated user with a campaign
    campaign = mock_global_context.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then the monogram link is labeled with the company name
    assert 'aria-label="Test Company"' in body


def test_company_dropdown_no_switch_forms_with_single_company(
    client, mock_global_context
) -> None:
    """Verify the switch-company forms are absent when only one company is approved."""
    # Given the default single-company session
    campaign = mock_global_context.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then no select-company form renders, but Company home does
    assert 'action="/select-company"' not in body
    assert "Company home" in body


def test_company_dropdown_lists_companies_when_multiple(client, mock_global_context) -> None:
    """Verify approved companies render as switch forms in the dropdown."""
    # Given a second approved company in the session (top-level reassignment so
    # the cookie session registers as modified)
    with client.session_transaction() as sess:
        sess["companies"] = {
            **sess["companies"],
            "second-co": {
                "user_id": "second-user-id",
                "company_name": "Night Owls LARP",
                "role": "ADMIN",
            },
        }
    campaign = mock_global_context.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then both companies appear with a switch form
    assert "Night Owls LARP" in body
    assert 'action="/select-company"' in body


def test_company_dropdown_admin_links(client, mocker) -> None:
    """Verify admins get Members, Settings, and Audit log entries in the dropdown."""
    # Given an admin user
    ctx = build_global_context(user_role="ADMIN")
    mocker.patch(LOAD_PATH, return_value=ctx)
    campaign = ctx.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then the admin entries render in the company dropdown
    assert "Members" in body
    assert "/admin/settings" in body
    assert "Audit log" in body


def test_user_menu_omits_switch_company(client, mock_global_context) -> None:
    """Verify the Switch Company item left the user menu (it lives in the company pill now)."""
    # Given a session with two approved companies (the old menu item's trigger condition)
    with client.session_transaction() as sess:
        sess["companies"] = {
            **sess["companies"],
            "second-co": {
                "user_id": "second-user-id",
                "company_name": "Night Owls LARP",
                "role": "ADMIN",
            },
        }
    campaign = mock_global_context.campaigns[0]

    # When loading a campaign page
    body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

    # Then the user-menu link text is gone
    assert "Switch Company" not in body
