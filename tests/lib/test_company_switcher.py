"""Tests for the header company switcher."""

from __future__ import annotations

import pytest
from flask import url_for


def _campaign_page(client, campaign_id: str) -> str:
    return client.get(f"/campaign/{campaign_id}").get_data(as_text=True)


def test_header_names_the_company(client, mock_global_context) -> None:
    """Verify the company link carries the company name, including for screen readers."""
    body = _campaign_page(client, mock_global_context.campaigns[0].id)

    assert 'aria-label="Test Company"' in body


def test_switch_forms_list_only_approved_companies(client, mock_global_context) -> None:
    """Verify switch forms appear for two or more approved companies, never unapproved ones."""
    # Given a single approved company, no switch form renders
    assert 'action="/select-company"' not in _campaign_page(
        client, mock_global_context.campaigns[0].id
    )

    # Given a second approved company and an unapproved one (top-level reassignment so the
    # cookie session registers as modified)
    with client.session_transaction() as sess:
        sess["companies"] = {
            **sess["companies"],
            "second-co": {"user_id": "u2", "company_name": "Night Owls LARP", "role": "ADMIN"},
            "pending-co": {"user_id": "u3", "company_name": "Pending Co", "role": "UNAPPROVED"},
        }

    body = _campaign_page(client, mock_global_context.campaigns[0].id)

    assert 'action="/select-company"' in body
    assert 'name="company_id" value="second-co"' in body
    assert "pending-co" not in body


@pytest.mark.parametrize(("role", "shown"), [("ADMIN", True), ("STORYTELLER", False)])
def test_admin_links_only_for_admins(app, client, use_context, role: str, shown: bool) -> None:  # noqa: FBT001
    """Verify only admins get the members, settings, and audit log links."""
    ctx = use_context(user_role=role)

    body = _campaign_page(client, ctx.campaigns[0].id)

    with app.test_request_context():
        admin_urls = [url_for(e) for e in ("admin.users", "admin.settings", "admin.audit_log")]
    for url in admin_urls:
        assert (f'href="{url}"' in body) is shown
