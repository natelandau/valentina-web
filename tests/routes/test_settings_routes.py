"""Settings route tests."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from vweb.api_client.models.companies import Company, CompanySettings
from vweb.api_client.testing import CompanyFactory, Routes

if TYPE_CHECKING:
    from flask.testing import FlaskClient

    from vweb.lib.cache.global_context import GlobalContext


@pytest.fixture
def admin_context(mock_global_context: GlobalContext) -> GlobalContext:
    """Promote the test user to ADMIN."""
    mock_global_context.users[0].role = "ADMIN"
    return mock_global_context


@pytest.fixture
def _company_api(mocker, admin_context, fake_vclient) -> None:
    """Serve a known company from the API for reads and updates."""
    company = CompanyFactory.build(
        id="test-company-id",
        name="Acme Co",
        email="admin@acme.example",
        description="A test company",
    )
    mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.COMPANIES_UPDATE, model=company)


class TestSettingsRouteRegistered:
    """Smoke test: the /settings URL resolves to a registered view."""

    def test_settings_url_exists(self, app) -> None:
        """The /settings endpoint must be registered on the app."""
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/admin/settings" in rules


class TestSettingsAccessControl:
    """Server-side guard: only ADMIN may reach /settings."""

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
        fake_vclient,
    ) -> None:
        """Verify admin GET returns 200 with the settings page rendered."""
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build())
        fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[])
        response = client.get("/admin/settings")
        assert response.status_code == 200

    def test_non_admin_redirected_with_flash(
        self,
        client: FlaskClient,
        player_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify non-admin GET is redirected to / with an error flash."""
        mocker.patch("vweb.lib.cache.global_context.load", return_value=player_context)
        response = client.get("/admin/settings")
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
        fake_vclient,
    ) -> None:
        """Verify the Users tab badge reflects the unapproved user count."""
        # Given an admin user and two pending users surfaced via global context
        mock_global_context.users[0].role = "ADMIN"
        mock_global_context.pending_user_count = 2
        mocker.patch("vweb.lib.cache.global_context.load", return_value=mock_global_context)

        fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build())

        # When loading the settings page
        response = client.get("/admin/settings")

        # Then the Users tab and badge are present
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'href="/admin/users"' in body
        assert "animate-ping" in body


class TestSettingsGet:
    """GET /settings renders pre-populated form."""

    @pytest.fixture
    def company(self, mocker, admin_context: GlobalContext, fake_vclient) -> Company:
        """Serve a known company from the API."""
        company = CompanyFactory.build(
            id="test-company-id",
            name="Acme Co",
            email="admin@acme.example",
            description="A test company",
            settings=CompanySettings(
                character_autogen_xp_cost=15,
                character_autogen_num_choices=3,
                character_autogen_starting_points=25,
                permission_manage_campaign="STORYTELLER",
                permission_manage_npc="STORYTELLER",
                permission_grant_xp="UNRESTRICTED",
                permission_free_trait_changes="WITHIN_24_HOURS",
                permission_recoup_xp="UNRESTRICTED",
                specialty_xp_cost_enabled=True,
                custom_flaw_xp_cost=7,
            ),
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
        return company

    def test_get_renders_company_name(self, client: FlaskClient, company: Company) -> None:
        """Verify GET /settings renders the company name in the form."""
        response = client.get("/admin/settings")
        assert response.status_code == 200
        assert b'value="Acme Co"' in response.data

    def test_get_renders_company_email(self, client: FlaskClient, company: Company) -> None:
        """Verify GET /settings renders the company email in the form."""
        response = client.get("/admin/settings")
        assert b'value="admin@acme.example"' in response.data

    def test_get_renders_autogen_xp_cost(self, client: FlaskClient, company: Company) -> None:
        """Verify GET /settings renders the autogen XP cost in the form."""
        response = client.get("/admin/settings")
        assert b'value="15"' in response.data

    def test_get_renders_autogen_starting_points(
        self, client: FlaskClient, company: Company
    ) -> None:
        """Verify GET /settings renders the autogen starting-points value in the form."""
        # When loading the settings page
        response = client.get("/admin/settings")

        # Then the starting-points input is pre-populated with the company value
        assert b'name="character_autogen_starting_points"' in response.data
        assert b'value="25"' in response.data

    def test_get_renders_custom_flaw_xp_cost(self, client: FlaskClient, company: Company) -> None:
        """Verify GET /settings pre-populates the custom flaw XP cost input."""
        # When loading the settings page
        response = client.get("/admin/settings")

        # Then the custom flaw cost input holds the company value
        tag = re.search(
            r'<input[^>]*name="custom_flaw_xp_cost"[^>]*>', response.get_data(as_text=True)
        )
        assert tag is not None
        assert 'value="7"' in tag.group(0)

    @pytest.mark.usefixtures("company")
    def test_get_calls_companies_get_with_company_id(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify GET /settings fetches the session's company from the API."""
        client.get("/admin/settings")
        fake_vclient.assert_called(
            Routes.COMPANIES_GET, params={"company_id": "test-company-id"}, times=1
        )

    def test_settings_page_renders_manage_npc_select(
        self, client: FlaskClient, company: Company
    ) -> None:
        """Verify the settings page renders the Manage NPC permission control."""
        # When loading the settings page
        response = client.get("/admin/settings")

        # Then the Manage NPC select is present
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'name="permission_manage_npc"' in body

    def test_settings_page_renders_specialty_cost_toggle(
        self, client: FlaskClient, company: Company
    ) -> None:
        """Verify the specialty cost toggle renders checked when the setting is on."""
        body = client.get("/admin/settings").get_data(as_text=True)

        assert 'name="specialty_xp_cost_enabled"' in body
        tag = re.search(r'<input[^>]*name="specialty_xp_cost_enabled"[^>]*>', body)
        assert tag is not None
        assert "checked" in tag.group(0)

    def test_settings_page_toggle_unchecked_when_setting_off(
        self, client: FlaskClient, company: Company, fake_vclient
    ) -> None:
        """Verify the specialty cost toggle renders unchecked when the setting is off."""
        company.settings.specialty_xp_cost_enabled = False
        fake_vclient.set_response(Routes.COMPANIES_GET, model=company)

        body = client.get("/admin/settings").get_data(as_text=True)

        tag = re.search(r'<input[^>]*name="specialty_xp_cost_enabled"[^>]*>', body)
        assert tag is not None
        assert "checked" not in tag.group(0)


class TestSettingsPostSuccess:
    """POST /settings happy path."""

    @pytest.mark.usefixtures("_company_api")
    def test_post_valid_calls_update_and_redirects(self, client: FlaskClient, fake_vclient) -> None:
        """Verify valid POST sends the update to the API and redirects to /settings."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)

        response = client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf,
                "name": "New Name",
                "email": "new@acme.example",
                "description": "Updated description",
                "character_autogen_xp_cost": "20",
                "character_autogen_num_choices": "4",
                "character_autogen_starting_points": "30",
                "custom_flaw_xp_cost": "4",
                "permission_manage_campaign": "STORYTELLER",
                "permission_manage_npc": "UNRESTRICTED",
                "permission_grant_xp": "UNRESTRICTED",
                "permission_free_trait_changes": "",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin/settings")

        # A blank permission is left out of the body so the API keeps its value
        fake_vclient.assert_called(
            Routes.COMPANIES_UPDATE,
            params={"company_id": "test-company-id"},
            json={
                "name": "New Name",
                "email": "new@acme.example",
                "description": "Updated description",
                "settings": {
                    "character_autogen_xp_cost": 20,
                    "character_autogen_num_choices": 4,
                    "character_autogen_starting_points": 30,
                    "permission_manage_campaign": "STORYTELLER",
                    "permission_manage_npc": "UNRESTRICTED",
                    "permission_grant_xp": "UNRESTRICTED",
                    "specialty_xp_cost_enabled": False,
                    "custom_flaw_xp_cost": 4,
                },
            },
            times=1,
        )

    @pytest.mark.parametrize(
        ("extra", "expected"),
        [({"specialty_xp_cost_enabled": "on"}, True), ({}, False)],
    )
    @pytest.mark.usefixtures("_company_api")
    def test_post_specialty_cost_checkbox(
        self, client: FlaskClient, fake_vclient, extra: dict[str, str], *, expected: bool
    ) -> None:
        """Verify a checked box sends True and an absent box sends False, never None."""
        from tests.conftest import get_csrf

        response = client.post(
            "/admin/settings",
            data={"csrf_token": get_csrf(client), "name": "Acme Co", **extra},
        )
        assert response.status_code == 302
        fake_vclient.assert_called(
            Routes.COMPANIES_UPDATE,
            json_subset={"settings": {"specialty_xp_cost_enabled": expected}},
            times=1,
        )

    @pytest.mark.usefixtures("_company_api")
    def test_post_valid_flashes_success(self, client: FlaskClient) -> None:
        """Verify valid POST flashes a success message containing 'updated'."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf,
                "name": "New Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "character_autogen_starting_points": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("updated" in msg.lower() for _, msg in flashes)

    @pytest.mark.usefixtures("_company_api")
    def test_post_blank_optional_fields_become_none(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify blank optional form fields are left out of the update request."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf,
                "name": "Required Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "character_autogen_starting_points": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        fake_vclient.assert_called(
            Routes.COMPANIES_UPDATE,
            json={"name": "Required Name", "settings": {"specialty_xp_cost_enabled": False}},
            times=1,
        )


class TestSettingsPostValidation:
    """POST /settings validation error path."""

    @pytest.mark.parametrize(
        ("extra", "expect_checked"),
        [({"specialty_xp_cost_enabled": "on"}, True), ({}, False)],
    )
    @pytest.mark.usefixtures("_company_api")
    def test_post_invalid_rerender_preserves_specialty_toggle(
        self,
        client: FlaskClient,
        fake_vclient,
        extra: dict[str, str],
        *,
        expect_checked: bool,
    ) -> None:
        """Verify a 400 re-render keeps the submitted toggle state."""
        from tests.conftest import get_csrf

        response = client.post(
            "/admin/settings",
            data={
                "csrf_token": get_csrf(client),
                "name": "Acme Co",
                "character_autogen_xp_cost": "abc",
                **extra,
            },
        )

        assert response.status_code == 400
        body = response.get_data(as_text=True)
        tag = re.search(r'<input[^>]*name="specialty_xp_cost_enabled"[^>]*>', body)
        assert tag is not None
        assert ("checked" in tag.group(0)) is expect_checked
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.usefixtures("_company_api")
    def test_post_short_name_returns_400_and_preserves_input(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify a name shorter than 3 chars returns 400 and re-renders with the submitted value."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        response = client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf,
                "name": "Hi",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "character_autogen_starting_points": "",
                "permission_manage_campaign": "",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert 'value="Hi"' in body
        assert "text-error" in body
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.parametrize(
        "field",
        [
            "character_autogen_xp_cost",
            "character_autogen_num_choices",
            "character_autogen_starting_points",
            "custom_flaw_xp_cost",
        ],
    )
    @pytest.mark.usefixtures("_company_api")
    def test_post_invalid_int_returns_400(
        self, client: FlaskClient, fake_vclient, field: str
    ) -> None:
        """Verify a non-integer in an int field returns 400 with an error message."""
        # Given a CSRF token and a payload where one int field is non-numeric
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        data = {
            "csrf_token": csrf,
            "name": "Valid Name",
            "email": "",
            "description": "",
            "character_autogen_xp_cost": "",
            "character_autogen_num_choices": "",
            "character_autogen_starting_points": "",
            "permission_manage_campaign": "",
            "permission_grant_xp": "",
            "permission_free_trait_changes": "",
            field: "not-a-number",
        }

        # When posting to the settings endpoint
        response = client.post("/admin/settings", data=data)

        # Then the request is rejected and no update is issued
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert "whole number" in body.lower()
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.usefixtures("_company_api")
    def test_post_invalid_permission_returns_400(self, client: FlaskClient, fake_vclient) -> None:
        """Verify an invalid permission enum value returns 400."""
        from tests.conftest import get_csrf

        csrf = get_csrf(client)
        response = client.post(
            "/admin/settings",
            data={
                "csrf_token": csrf,
                "name": "Valid Name",
                "email": "",
                "description": "",
                "character_autogen_xp_cost": "",
                "character_autogen_num_choices": "",
                "character_autogen_starting_points": "",
                "permission_manage_campaign": "TOTALLY_FAKE_VALUE",
                "permission_grant_xp": "",
                "permission_free_trait_changes": "",
            },
        )
        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.usefixtures("_company_api")
    def test_post_missing_csrf_returns_400(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a POST without a CSRF token returns 400."""
        response = client.post("/admin/settings", data={"name": "Valid Name"})
        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)


class TestSettingsNavLink:
    """The Settings link in the user-avatar dropdown is gated to ADMIN."""

    @pytest.fixture
    def player_context(self, mock_global_context: GlobalContext) -> GlobalContext:  # type: ignore[name-defined]
        """Force the test user to PLAYER."""
        mock_global_context.users[0].role = "PLAYER"
        return mock_global_context

    @pytest.mark.skip(
        reason="Admin link dropped from global nav, will be restored in a future pass; see docs/superpowers/specs/2026-04-21-global-header-redesign-design.md"
    )
    def test_admin_sees_settings_link(
        self,
        client: FlaskClient,
        admin_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify admin users see the /settings link in navigation."""
        mocker.patch("vweb.lib.cache.global_context.load", return_value=admin_context)
        response = client.get(f"/profile/{admin_context.users[0].id}")
        assert b"/admin" in response.data

    @pytest.mark.skip(
        reason="Admin link dropped from global nav, will be restored in a future pass; see docs/superpowers/specs/2026-04-21-global-header-redesign-design.md"
    )
    def test_player_does_not_see_settings_link(
        self,
        client: FlaskClient,
        player_context: GlobalContext,
        mocker,  # type: ignore[name-defined]
    ) -> None:
        """Verify non-admin users do not see the /admin link in navigation."""
        mocker.patch("vweb.lib.cache.global_context.load", return_value=player_context)
        response = client.get(f"/profile/{player_context.users[0].id}")
        assert b"/admin" not in response.data
