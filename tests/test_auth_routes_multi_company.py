"""Tests for multi-company auth flows (select-companies, select-company)."""

from __future__ import annotations

from unittest.mock import MagicMock

from vclient.models import UserLookupResult
from vclient.testing import CompanyFactory, UserFactory

from tests.conftest import get_csrf


def _make_lookup_result(**kwargs) -> UserLookupResult:
    """Build a UserLookupResult with sensible defaults."""
    defaults = {
        "company_id": "comp-1",
        "company_name": "Test Company",
        "user_id": "user-1",
        "role": "PLAYER",
    }
    defaults.update(kwargs)
    return UserLookupResult(**defaults)


def _mock_discord_oauth(mocker, discord_data=None) -> dict:
    """Set up mock Discord OAuth flow returning the given user data."""
    if discord_data is None:
        discord_data = {"id": "disc-1", "username": "testuser", "email": "test@example.com"}
    mock_discord = MagicMock()
    mock_discord.authorize_access_token.return_value = {"access_token": "fake"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = discord_data
    mock_discord.get.return_value = mock_resp
    mocker.patch("vweb.routes.auth.views.oauth", discord=mock_discord)
    return discord_data


class TestNewUserRedirectsToSelectCompanies:
    """Tests for new user being redirected to company selection."""

    def test_new_user_redirects_to_select_companies(self, client, mocker):
        """Verify new user with no lookup results is sent to /select-companies."""
        # Given a mock Discord OAuth flow
        _mock_discord_oauth(mocker)

        # Given no lookup results (completely new user)
        mocker.patch("vweb.routes.auth.views.lookup_user_companies", return_value=[])

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then redirect to /select-companies with pending_oauth in session
        assert response.status_code == 302
        assert response.location == "/select-companies"
        with client.session_transaction() as sess:
            assert "pending_oauth" in sess
            assert sess["pending_oauth"]["provider"] == "discord"


class TestSingleApprovedUser:
    """Tests for single approved user login."""

    def test_single_approved_redirects_to_index(self, client, mocker):
        """Verify single approved user is logged in and sent to index."""
        # Given a mock Discord OAuth flow
        _mock_discord_oauth(mocker)

        # Given a single approved lookup result
        result = _make_lookup_result(company_id="c1", user_id="u1", role="PLAYER")
        mocker.patch("vweb.routes.auth.views.lookup_user_companies", return_value=[result])
        mocker.patch("vweb.routes.auth.views.update_discord_profile")

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then session is set and redirects to /
        assert response.status_code == 302
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "u1"
            assert sess["company_id"] == "c1"
            assert "c1" in sess["companies"]


class TestSingleUnapprovedUser:
    """Tests for single unapproved user login."""

    def test_single_unapproved_redirects_to_pending(self, client, mocker):
        """Verify single unapproved user is sent to /pending-approval."""
        # Given a mock Discord OAuth flow
        _mock_discord_oauth(mocker)

        # Given a single unapproved lookup result
        result = _make_lookup_result(company_id="c1", user_id="u1", role="UNAPPROVED")
        mocker.patch("vweb.routes.auth.views.lookup_user_companies", return_value=[result])

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then redirect to /pending-approval
        assert response.status_code == 302
        assert response.location == "/pending-approval"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "u1"


class TestMultipleCompaniesWithApproved:
    """Tests for users with multiple companies, at least one approved."""

    def test_multiple_with_approved_redirects_to_select_company(self, client, mocker):
        """Verify multi-company user with approved roles is sent to /select-company."""
        # Given a mock Discord OAuth flow
        _mock_discord_oauth(mocker)

        # Given multiple lookup results with at least one approved
        results = [
            _make_lookup_result(company_id="c1", user_id="u1", role="PLAYER"),
            _make_lookup_result(
                company_id="c2",
                company_name="Other Co",
                user_id="u2",
                role="ADMIN",
            ),
        ]
        mocker.patch("vweb.routes.auth.views.lookup_user_companies", return_value=results)

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then redirect to /select-company
        assert response.status_code == 302
        assert response.location == "/select-company"
        with client.session_transaction() as sess:
            assert len(sess["companies"]) == 2


class TestMultipleCompaniesAllUnapproved:
    """Tests for users with multiple companies, all unapproved."""

    def test_multiple_all_unapproved_redirects_to_pending(self, client, mocker):
        """Verify multi-company user with all UNAPPROVED roles is sent to /pending-approval."""
        # Given a mock Discord OAuth flow
        _mock_discord_oauth(mocker)

        # Given multiple lookup results all UNAPPROVED
        results = [
            _make_lookup_result(company_id="c1", user_id="u1", role="UNAPPROVED"),
            _make_lookup_result(company_id="c2", user_id="u2", role="UNAPPROVED"),
        ]
        mocker.patch("vweb.routes.auth.views.lookup_user_companies", return_value=results)

        # When the callback is hit
        response = client.get("/auth/discord/callback")

        # Then redirect to /pending-approval
        assert response.status_code == 302
        assert response.location == "/pending-approval"


class TestSelectCompaniesView:
    """Tests for GET/POST /select-companies."""

    def test_get_shows_companies(self, client, mocker):
        """Verify GET /select-companies renders available companies."""
        # Given available companies from the API
        companies = CompanyFactory.batch(2)
        mocker.patch(
            "vweb.routes.auth.views.sync_companies_service"
        ).return_value.list_all.return_value = companies

        # When the page is requested
        response = client.get("/select-companies")

        # Then it renders successfully
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Join a Company" in body

    def test_post_registers_user_redirects_to_pending(self, client, mocker):
        """Verify POST /select-companies registers user and redirects to pending."""
        # Given pending OAuth data in session
        with client.session_transaction() as sess:
            sess["pending_oauth"] = {
                "provider": "discord",
                "data": {
                    "id": "disc-1",
                    "username": "testuser",
                    "email": "test@example.com",
                },
            }

        # Given a mock user service that returns a new user
        new_user = UserFactory.build(id="new-u", role="UNAPPROVED")
        mock_svc = MagicMock()
        mock_svc.register.return_value = new_user
        mocker.patch(
            "vweb.routes.auth.views.sync_user_self_registration_service", return_value=mock_svc
        )

        # Given a mock companies service for name lookup
        mock_company = CompanyFactory.build(id="comp-1", name="Test Company")
        mock_companies_svc = MagicMock()
        mock_companies_svc.list_all.return_value = [mock_company]
        mocker.patch(
            "vweb.routes.auth.views.sync_companies_service", return_value=mock_companies_svc
        )

        # Given a CSRF token
        csrf_token = get_csrf(client)

        # When submitting company selections
        response = client.post(
            "/select-companies",
            data={"company_ids": ["comp-1"], "csrf_token": csrf_token},
        )

        # Then redirected to pending approval with session set
        assert response.status_code == 302
        assert response.location == "/pending-approval"
        with client.session_transaction() as sess:
            assert sess["user_id"] == "new-u"
            assert sess["company_id"] == "comp-1"
            assert "pending_oauth" not in sess

    def test_post_without_pending_oauth_redirects_to_index(self, client, mocker):
        """Verify POST /select-companies without session data redirects to index."""
        # Given no pending_oauth in session
        with client.session_transaction() as sess:
            sess.pop("pending_oauth", None)

        csrf_token = get_csrf(client)

        # When submitting company selections
        response = client.post(
            "/select-companies",
            data={"company_ids": ["comp-1"], "csrf_token": csrf_token},
        )

        # Then redirected to index
        assert response.status_code == 302
        assert response.location == "/"

    def test_post_without_selections_redirects_back(self, client, mocker):
        """Verify POST /select-companies without selections redirects back."""
        # Given pending OAuth data in session
        with client.session_transaction() as sess:
            sess["pending_oauth"] = {
                "provider": "discord",
                "data": {"id": "disc-1", "username": "u", "email": "e@e.com"},
            }

        csrf_token = get_csrf(client)

        # When submitting with no company selections
        response = client.post(
            "/select-companies",
            data={"csrf_token": csrf_token},
        )

        # Then redirected back to select-companies
        assert response.status_code == 302
        assert response.location == "/select-companies"


class TestSelectCompanyView:
    """Tests for GET/POST /select-company."""

    def test_get_shows_approved_companies(self, client):
        """Verify GET /select-company renders approved companies only."""
        # Given a session with multiple companies, one unapproved
        with client.session_transaction() as sess:
            sess["companies"] = {
                "c1": {"user_id": "u1", "company_name": "Alpha", "role": "PLAYER"},
                "c2": {"user_id": "u2", "company_name": "Beta", "role": "UNAPPROVED"},
                "c3": {"user_id": "u3", "company_name": "Gamma", "role": "ADMIN"},
            }

        # When the page is requested
        response = client.get("/select-company")

        # Then it renders only approved companies
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Alpha" in body
        assert "Gamma" in body
        # Unapproved company should not appear
        assert "Beta" not in body

    def test_post_switches_session(self, client):
        """Verify POST /select-company switches active company and redirects to index."""
        # Given a CSRF token (must be fetched before changing user_id, since
        # get_csrf triggers hooks that validate user_id against mock context)
        csrf_token = get_csrf(client)

        # Given a session with multiple approved companies
        with client.session_transaction() as sess:
            sess["companies"] = {
                "c1": {"user_id": "u1", "company_name": "Alpha", "role": "PLAYER"},
                "c2": {"user_id": "u2", "company_name": "Beta", "role": "ADMIN"},
            }
            sess["company_id"] = "c1"
            sess["user_id"] = "u1"

        # When switching to company c2
        response = client.post(
            "/select-company",
            data={"company_id": "c2", "csrf_token": csrf_token},
        )

        # Then session is updated and redirected to index
        assert response.status_code == 302
        assert response.location == "/"
        with client.session_transaction() as sess:
            assert sess["company_id"] == "c2"
            assert sess["user_id"] == "u2"

    def test_post_invalid_company_id_shows_error(self, client):
        """Verify POST /select-company with invalid company_id redirects back."""
        csrf_token = get_csrf(client)

        # Given a session with companies
        with client.session_transaction() as sess:
            sess["companies"] = {
                "c1": {"user_id": "u1", "company_name": "Alpha", "role": "PLAYER"},
            }

        # When switching to a non-existent company
        response = client.post(
            "/select-company",
            data={"company_id": "invalid", "csrf_token": csrf_token},
        )

        # Then redirected back to select-company
        assert response.status_code == 302
        assert response.location == "/select-company"

    def test_post_unapproved_company_rejected(self, client):
        """Verify POST /select-company rejects switching to unapproved company."""
        csrf_token = get_csrf(client)

        # Given a session with an unapproved company
        with client.session_transaction() as sess:
            sess["companies"] = {
                "c1": {"user_id": "u1", "company_name": "Alpha", "role": "UNAPPROVED"},
            }

        # When trying to switch to the unapproved company
        response = client.post(
            "/select-company",
            data={"company_id": "c1", "csrf_token": csrf_token},
        )

        # Then redirected back to select-company
        assert response.status_code == 302
        assert response.location == "/select-company"
