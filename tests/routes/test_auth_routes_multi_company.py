"""Tests for routing a login by its memberships, and for the company selection pages."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from tests.helpers import (
    assert_redirects_to,
    identify_resolving,
    mock_oauth_provider,
    session_flashes,
)
from vweb.api_client.exceptions import UnprocessableEntityError
from vweb.api_client.models import IdentityResolution
from vweb.api_client.testing import CompanyFactory, Routes, UserFactory, UserLookupResultFactory

if TYPE_CHECKING:
    from flask.testing import FlaskClient

PENDING_OAUTH = {
    "provider": "discord",
    "token": "cred-1",
    "username": "testuser",
    "email": "test@example.com",
}


def _mock_discord_oauth(mocker) -> None:
    """Set up a Discord OAuth flow that returns a token and a profile."""
    mock_oauth_provider(
        mocker,
        "discord",
        token={"access_token": "fake"},
        profile={"id": "disc-1", "username": "testuser", "email": "test@example.com"},
    )


@pytest.mark.parametrize(
    ("roles", "expected_location", "expected_user", "expected_companies"),
    [
        (["PLAYER"], "/", "u1", ["c1"]),
        (["UNAPPROVED"], "/pending-approval", "u1", ["c1"]),
        (["PLAYER", "DEACTIVATED"], "/", "u1", ["c1"]),
        (["PLAYER", "ADMIN"], "/select-company", None, ["c1", "c2"]),
        (["UNAPPROVED", "UNAPPROVED"], "/pending-approval", "u1", ["c1", "c2"]),
    ],
    ids=[
        "single-approved",
        "single-unapproved",
        "deactivated-dropped",
        "multiple-approved-pick",
        "all-unapproved",
    ],
)
def test_login_routes_by_verified_memberships(
    client: FlaskClient,
    mocker,
    roles: list[str],
    expected_location: str,
    expected_user: str | None,
    expected_companies: list[str],
) -> None:
    """Verify the callback signs in, sends to pending approval, or asks which company to use."""
    # Given a visitor with a verified membership per role, in companies c1, c2, ...
    with client.session_transaction() as sess:
        sess.clear()
    _mock_discord_oauth(mocker)
    results = [
        UserLookupResultFactory.build(company_id=f"c{i}", user_id=f"u{i}", role=role)
        for i, role in enumerate(roles, start=1)
    ]
    mocker.patch("vweb.routes.auth.views_oauth.lookup_user_companies", return_value=results)
    mocker.patch(
        "vweb.routes.auth.views_oauth.identify_in_companies",
        return_value=identify_resolving(results),
    )

    # When the callback is hit
    response = client.get("/auth/discord/callback")

    # Then the visitor lands where the memberships dictate with a long-lived session
    assert_redirects_to(response, expected_location)
    with client.session_transaction() as sess:
        assert sess.get("user_id") == expected_user
        assert list(sess["companies"]) == expected_companies
        assert sess.permanent is True


def test_login_refused_when_every_membership_deactivated(client: FlaskClient, mocker) -> None:
    """Verify a user deactivated in every matched company gets no session."""
    # Given a single deactivated membership
    with client.session_transaction() as sess:
        sess.clear()
    _mock_discord_oauth(mocker)
    result = UserLookupResultFactory.build(company_id="c1", user_id="u1", role="DEACTIVATED")
    mocker.patch("vweb.routes.auth.views_oauth.lookup_user_companies", return_value=[result])
    mocker.patch(
        "vweb.routes.auth.views_oauth.identify_in_companies",
        return_value=identify_resolving([result]),
    )

    # When the callback is hit
    response = client.get("/auth/discord/callback")

    # Then the user lands on the index, unbound to the deactivated membership
    assert response.location == "/"
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "companies" not in sess
    assert [category for category, _ in session_flashes(client)] == ["error"]


class TestSelectCompaniesView:
    """Tests for GET/POST /select-companies, where a new user joins companies."""

    def test_get_lists_companies(self, client: FlaskClient, fake_vclient) -> None:
        """Verify the page lists every company the user can join."""
        companies = [CompanyFactory.build(name="Alpha Co"), CompanyFactory.build(name="Beta Co")]
        fake_vclient.set_response(Routes.COMPANIES_LIST, items=companies)

        response = client.get("/select-companies")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Alpha Co" in body
        assert "Beta Co" in body

    def test_post_registers_user_and_sends_to_pending(
        self, client: FlaskClient, mocker, fake_vclient
    ) -> None:
        """Verify registration verifies the stored credential and signs the new user in."""
        # Given a pending login and an identify that creates an UNAPPROVED user
        with client.session_transaction() as sess:
            sess["pending_oauth"] = PENDING_OAUTH
        new_user = UserFactory.build(id="new-u", role="UNAPPROVED")
        mock_identify = mocker.patch(
            "vweb.routes.auth.views.identify_in_companies",
            return_value={"comp-1": IdentityResolution(resolution="created", user=new_user)},
        )
        fake_vclient.set_response(
            Routes.COMPANIES_LIST,
            items=[CompanyFactory.build(id="comp-1", name="Test Company")],
        )

        # When submitting company selections
        response = client.post(
            "/select-companies",
            data={"company_ids": ["comp-1"], "csrf_token": get_csrf(client)},
        )

        # Then identify ran with the stored credential and hints
        mock_identify.assert_called_once_with(
            ["comp-1"],
            provider="discord",
            token="cred-1",
            username="testuser",
            email="test@example.com",
        )
        # And the new user is signed in and sent to pending approval
        assert response.location == "/pending-approval"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "new-u"
            assert sess["company_id"] == "comp-1"
            assert sess["companies"]["comp-1"]["company_name"] == "Test Company"
            assert "pending_oauth" not in sess

    @pytest.mark.parametrize(
        "pending",
        [None, {"provider": "discord", "data": {}}],
        ids=["missing", "without-credential"],
    )
    def test_post_without_usable_pending_login_returns_home(
        self, client: FlaskClient, pending: dict | None
    ) -> None:
        """Verify registering without a stored credential is treated as an expired session."""
        with client.session_transaction() as sess:
            sess.pop("pending_oauth", None)
            if pending is not None:
                sess["pending_oauth"] = pending

        response = client.post(
            "/select-companies",
            data={"company_ids": ["comp-1"], "csrf_token": get_csrf(client)},
        )

        assert response.location == "/"
        with client.session_transaction() as sess:
            assert "pending_oauth" not in sess

    @pytest.mark.parametrize(
        "identify",
        [
            {
                "side_effect": UnprocessableEntityError(
                    "bad", 422, {"code": "TOKEN_VERIFICATION_FAILED"}
                )
            },
            {"return_value": {}},
        ],
        ids=["token-rejected", "no-company-resolved"],
    )
    def test_post_failed_registration_returns_home(
        self, client: FlaskClient, mocker, identify: dict
    ) -> None:
        """Verify a registration the API does not complete aborts with an error and no session."""
        # Given a signed-out visitor with a pending login the API will not register
        csrf_token = get_csrf(client)
        with client.session_transaction() as sess:
            for key in ("user_id", "company_id", "companies"):
                sess.pop(key)
            sess["pending_oauth"] = PENDING_OAUTH
        mocker.patch("vweb.routes.auth.views.identify_in_companies", **identify)

        # When submitting company selections
        response = client.post(
            "/select-companies",
            data={"company_ids": ["comp-1"], "csrf_token": csrf_token},
        )

        # Then the visitor is sent home with an error and the pending payload cleared
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert "pending_oauth" not in sess
            assert "user_id" not in sess
        assert [category for category, _ in session_flashes(client)] == ["error"]

    def test_post_without_selections_redirects_back(self, client: FlaskClient) -> None:
        """Verify submitting no companies returns to the selection page."""
        with client.session_transaction() as sess:
            sess["pending_oauth"] = PENDING_OAUTH

        response = client.post("/select-companies", data={"csrf_token": get_csrf(client)})

        assert response.location == "/select-companies"


class TestSelectCompanyView:
    """Tests for GET/POST /select-company, where a member switches the active company."""

    def test_get_lists_only_approved_companies(self, client: FlaskClient) -> None:
        """Verify the picker offers approved companies only."""
        with client.session_transaction() as sess:
            sess["companies"] = {
                "c1": {"user_id": "u1", "company_name": "Alpha", "role": "PLAYER"},
                "c2": {"user_id": "u2", "company_name": "Beta", "role": "UNAPPROVED"},
                "c3": {"user_id": "u3", "company_name": "Gamma", "role": "ADMIN"},
            }

        response = client.get("/select-company")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Alpha" in body
        assert "Gamma" in body
        assert "Beta" not in body

    def test_post_switches_company_and_forgets_campaign(self, client: FlaskClient) -> None:
        """Verify switching companies swaps the session user and drops the remembered campaign."""
        # Given two approved memberships and a remembered campaign
        with client.session_transaction() as sess:
            sess["companies"]["second-co"] = {
                "user_id": "second-user-id",
                "company_name": "Second Company",
                "role": "PLAYER",
            }
            sess["last_campaign_id"] = "stale-campaign-id"

        # When switching to the second company
        response = client.post(
            "/select-company",
            data={"company_id": "second-co", "csrf_token": get_csrf(client)},
        )

        # Then the session acts as the second membership and entry rules re-evaluate
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert sess["company_id"] == "second-co"
            assert sess["user_id"] == "second-user-id"
            assert "last_campaign_id" not in sess

    @pytest.mark.parametrize(
        ("company_id", "role"),
        [("invalid", "PLAYER"), ("c1", "UNAPPROVED")],
        ids=["unknown-company", "unapproved-membership"],
    )
    def test_post_rejects_company_user_cannot_enter(
        self, client: FlaskClient, company_id: str, role: str
    ) -> None:
        """Verify switching to an unknown or unapproved company is refused."""
        csrf_token = get_csrf(client)
        with client.session_transaction() as sess:
            sess["companies"] = {"c1": {"user_id": "u1", "company_name": "Alpha", "role": role}}

        response = client.post(
            "/select-company", data={"company_id": company_id, "csrf_token": csrf_token}
        )

        assert response.location == "/select-company"
        with client.session_transaction() as sess:
            assert sess["company_id"] == "test-company-id"
