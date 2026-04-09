"""Settings route tests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models.companies import CompanySettings
from vclient.testing import CompanyFactory

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient

    from vweb.lib.global_context import GlobalContext


class TestSettingsRouteRegistered:
    """Smoke test: the /settings URL resolves to a registered view."""

    def test_settings_url_exists(self, app) -> None:
        """The /settings endpoint must be registered on the app."""
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/settings" in rules


class TestSettingsAccessControl:
    """Server-side guard: only ADMIN may reach /settings."""

    @pytest.fixture
    def admin_context(self, mock_global_context: GlobalContext) -> GlobalContext:  # type: ignore[name-defined]
        """Promote the test user to ADMIN."""
        mock_global_context.users[0].role = "ADMIN"
        return mock_global_context

    @pytest.fixture
    def player_context(self, mock_global_context: GlobalContext) -> GlobalContext:  # type: ignore[name-defined]
        """Force the test user to PLAYER."""
        mock_global_context.users[0].role = "PLAYER"
        return mock_global_context

    def test_admin_can_get_settings(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify admin GET returns 200 with the settings page rendered."""
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)
        company = CompanyFactory.build()
        svc = MagicMock()
        svc.get.return_value = company
        mocker.patch("vweb.routes.settings.views.sync_companies_service", return_value=svc)
        users_svc = MagicMock()
        users_svc.list_all_unapproved.return_value = []
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=users_svc,
        )
        response = client.get("/settings")
        assert response.status_code == 200

    def test_non_admin_redirected_with_flash(
        self,
        client: FlaskClient,
        player_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify non-admin GET is redirected to / with an error flash."""
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=player_context)
        response = client.get("/settings")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("permission" in msg.lower() for _, msg in flashes)


class TestSettingsTabs:
    """Settings page renders the tab strip with pending badge count."""

    def test_settings_page_shows_users_tab_with_badge(
        self,
        client: FlaskClient,
        mock_global_context: GlobalContext,
        mocker,
    ) -> None:
        """Verify the Users tab badge reflects the unapproved user count."""
        # Given an admin user and two pending users
        mock_global_context.users[0].role = "ADMIN"
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=mock_global_context)

        company = CompanyFactory.build()
        companies_svc = MagicMock()
        companies_svc.get.return_value = company
        mocker.patch(
            "vweb.routes.settings.views.sync_companies_service",
            return_value=companies_svc,
        )

        users_svc = MagicMock()
        users_svc.list_all_unapproved.return_value = [MagicMock(), MagicMock()]
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=users_svc,
        )

        # When loading the settings page
        response = client.get("/settings")

        # Then the Users tab and badge are present
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'href="/settings/users"' in body
        assert "badge" in body
        assert ">2<" in body


class TestSettingsGet:
    """GET /settings renders pre-populated form."""

    @pytest.fixture
    def admin_context(self, mock_global_context: GlobalContext) -> GlobalContext:
        """Promote the test user to ADMIN."""
        mock_global_context.users[0].role = "ADMIN"
        return mock_global_context

    @pytest.fixture
    def mock_companies_svc(self, mocker, admin_context: GlobalContext) -> MagicMock:
        """Patch sync_companies_service to return a known company."""
        company = CompanyFactory.build(
            id="test-company-id",
            name="Acme Co",
            email="admin@acme.example",
            description="A test company",
            settings=CompanySettings(
                character_autogen_xp_cost=15,
                character_autogen_num_choices=3,
                permission_manage_campaign="STORYTELLER",
                permission_grant_xp="UNRESTRICTED",
                permission_free_trait_changes="WITHIN_24_HOURS",
            ),
        )
        svc = MagicMock()
        svc.get.return_value = company
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)
        mocker.patch(
            "vweb.routes.settings.views.sync_companies_service",
            return_value=svc,
        )
        users_svc = MagicMock()
        users_svc.list_all_unapproved.return_value = []
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=users_svc,
        )
        return svc

    def test_get_renders_company_name(
        self, client: FlaskClient, mock_companies_svc: MagicMock
    ) -> None:
        """Verify GET /settings renders the company name in the form."""
        response = client.get("/settings")
        assert response.status_code == 200
        assert b'value="Acme Co"' in response.data

    def test_get_renders_company_email(
        self, client: FlaskClient, mock_companies_svc: MagicMock
    ) -> None:
        """Verify GET /settings renders the company email in the form."""
        response = client.get("/settings")
        assert b'value="admin@acme.example"' in response.data

    def test_get_renders_autogen_xp_cost(
        self, client: FlaskClient, mock_companies_svc: MagicMock
    ) -> None:
        """Verify GET /settings renders the autogen XP cost in the form."""
        response = client.get("/settings")
        assert b'value="15"' in response.data

    def test_get_calls_companies_get_with_company_id(
        self, client: FlaskClient, mock_companies_svc: MagicMock, app: Flask
    ) -> None:
        """Verify GET /settings calls the companies service with the correct company ID."""
        client.get("/settings")
        mock_companies_svc.get.assert_called_once()
        called_with = mock_companies_svc.get.call_args[0][0]
        assert called_with == "PLACEHOLDER"


class TestSettingsPostSuccess:
    """POST /settings happy path."""

    @pytest.fixture
    def admin_context(self, mock_global_context):
        mock_global_context.users[0].role = "ADMIN"
        return mock_global_context

    @pytest.fixture
    def mock_companies_svc(self, mocker, admin_context):
        company = CompanyFactory.build(
            id="test-company-id",
            name="Acme Co",
            email="admin@acme.example",
            description="A test company",
            settings=CompanySettings(),
        )
        svc = MagicMock()
        svc.get.return_value = company
        svc.update.return_value = company
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)
        mocker.patch(
            "vweb.routes.settings.views.sync_companies_service",
            return_value=svc,
        )
        users_svc = MagicMock()
        users_svc.list_all_unapproved.return_value = []
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=users_svc,
        )
        return svc

    def test_post_valid_calls_update_and_redirects(
        self, client: FlaskClient, mock_companies_svc
    ) -> None:
        """Verify valid POST calls update and redirects to /settings."""
        from vclient.models.companies import CompanyUpdate

        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "New Name",
                "email": "new@acme.example",
                "description": "Updated description",
                "character_autogen_xp_cost": "20",
                "character_autogen_num_choices": "4",
                "permission_manage_campaign": "STORYTELLER",
                "permission_grant_xp": "UNRESTRICTED",
                "permission_free_trait_changes": "",  # blank → None
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/settings")

        mock_companies_svc.update.assert_called_once()
        args, kwargs = mock_companies_svc.update.call_args
        assert args[0] == "PLACEHOLDER"
        update_req: CompanyUpdate = kwargs["request"]
        assert isinstance(update_req, CompanyUpdate)
        assert update_req.name == "New Name"
        assert update_req.email == "new@acme.example"
        assert update_req.description == "Updated description"
        assert update_req.settings is not None
        assert update_req.settings.character_autogen_xp_cost == 20
        assert update_req.settings.character_autogen_num_choices == 4
        assert update_req.settings.permission_manage_campaign == "STORYTELLER"
        assert update_req.settings.permission_grant_xp == "UNRESTRICTED"
        assert update_req.settings.permission_free_trait_changes is None

    def test_post_valid_flashes_success(self, client: FlaskClient, mock_companies_svc) -> None:
        """Verify valid POST flashes a success message containing 'updated'."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "New Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("updated" in msg.lower() for _, msg in flashes)

    def test_post_blank_optional_fields_become_none(
        self, client: FlaskClient, mock_companies_svc
    ) -> None:
        """Verify blank optional form fields are converted to None in the update request."""
        from vclient.models.companies import CompanyUpdate

        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "Required Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        update_req: CompanyUpdate = mock_companies_svc.update.call_args[1]["request"]
        assert update_req.email is None
        assert update_req.description is None
        assert update_req.settings.character_autogen_xp_cost is None
        assert update_req.settings.character_autogen_num_choices is None
        assert update_req.settings.permission_manage_campaign is None


class TestSettingsPostValidation:
    """POST /settings validation error path."""

    @pytest.fixture
    def admin_context(self, mock_global_context):
        mock_global_context.users[0].role = "ADMIN"
        return mock_global_context

    @pytest.fixture
    def mock_companies_svc(self, mocker, admin_context):
        company = CompanyFactory.build(
            id="test-company-id",
            name="Acme Co",
            email="admin@acme.example",
            description="A test company",
            settings=CompanySettings(),
        )
        svc = MagicMock()
        svc.get.return_value = company
        svc.update.return_value = company
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)
        mocker.patch(
            "vweb.routes.settings.views.sync_companies_service",
            return_value=svc,
        )
        users_svc = MagicMock()
        users_svc.list_all_unapproved.return_value = []
        mocker.patch(
            "vweb.routes.settings.services.sync_users_service",
            return_value=users_svc,
        )
        return svc

    def test_post_short_name_returns_400_and_preserves_input(
        self, client: FlaskClient, mock_companies_svc
    ) -> None:
        """Verify a name shorter than 3 chars returns 400 and re-renders with the submitted value."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        response = client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "Hi",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert 'value="Hi"' in body
        assert "text-error" in body
        mock_companies_svc.update.assert_not_called()

    def test_post_invalid_int_returns_400(self, client: FlaskClient, mock_companies_svc) -> None:
        """Verify a non-integer in an int field returns 400 with an error message."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        response = client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "Valid Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "abc",
                "character_autogen_num_choices": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert "whole number" in body.lower() or "text-error" in body
        mock_companies_svc.update.assert_not_called()

    def test_post_invalid_permission_returns_400(
        self, client: FlaskClient, mock_companies_svc
    ) -> None:
        """Verify an invalid permission enum value returns 400."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        response = client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "name": "Valid Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "permission_manage_campaign": "TOTALLY_FAKE_VALUE",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        assert response.status_code == 400
        mock_companies_svc.update.assert_not_called()

    def test_post_missing_csrf_returns_400(self, client: FlaskClient, mock_companies_svc) -> None:
        """Verify a POST without a CSRF token returns 400."""
        response = client.post("/settings", data={"name": "Valid Name"})
        assert response.status_code == 400
        mock_companies_svc.update.assert_not_called()


class TestSettingsNavLink:
    """The Settings link in the user-avatar dropdown is gated to ADMIN."""

    @pytest.fixture
    def admin_context(self, mock_global_context: GlobalContext) -> GlobalContext:  # type: ignore[name-defined]
        """Promote the test user to ADMIN."""
        mock_global_context.users[0].role = "ADMIN"
        return mock_global_context

    @pytest.fixture
    def player_context(self, mock_global_context: GlobalContext) -> GlobalContext:  # type: ignore[name-defined]
        """Force the test user to PLAYER."""
        mock_global_context.users[0].role = "PLAYER"
        return mock_global_context

    def test_admin_sees_settings_link(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify admin users see the /settings link in navigation."""
        from vclient.testing import RollStatisticsFactory

        mocker.patch("vweb.lib.hooks.load_global_context", return_value=admin_context)
        mock_users_svc = MagicMock()
        mock_users_svc.get_statistics.return_value = RollStatisticsFactory.build()
        mocker.patch("vweb.routes.profile.views.sync_users_service", return_value=mock_users_svc)
        response = client.get(f"/profile/{admin_context.users[0].id}")
        assert b"/settings" in response.data

    def test_player_does_not_see_settings_link(
        self,
        client: FlaskClient,
        player_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify non-admin users do not see the /settings link in navigation."""
        from vclient.testing import RollStatisticsFactory

        mocker.patch("vweb.lib.hooks.load_global_context", return_value=player_context)
        mock_users_svc = MagicMock()
        mock_users_svc.get_statistics.return_value = RollStatisticsFactory.build()
        mocker.patch("vweb.routes.profile.views.sync_users_service", return_value=mock_users_svc)
        response = client.get(f"/profile/{player_context.users[0].id}")
        assert b"/settings" not in response.data
