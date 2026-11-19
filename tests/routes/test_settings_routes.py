"""Tests for the admin blueprint guard and the /admin/settings page."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf
from tests.helpers import assert_redirects_to, session_flashes
from vweb.api_client.models.companies import Company, CompanySettings
from vweb.api_client.testing import CompanyFactory, Routes

if TYPE_CHECKING:
    from flask.testing import FlaskClient

    from vweb.api_client.constants import UserRole


@pytest.fixture
def _company_api(admin_context, fake_vclient) -> None:
    """Serve a known company from the API for reads and updates."""
    company = CompanyFactory.build(
        id="test-company-id",
        name="Acme Co",
        email="admin@acme.example",
        description="A test company",
    )
    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.COMPANIES_UPDATE, model=company)


def _input_tag(body: str, name: str) -> str:
    """Return the rendered <input> tag for a form field, failing when it is missing."""
    tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', body)
    assert tag is not None, f"no input named {name}"
    return tag.group(0)


class TestAdminAccessControl:
    """Server-side guard: only ADMIN may reach any /admin page or action."""

    @pytest.mark.parametrize("role", ["PLAYER", "STORYTELLER"])
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/admin"),
            ("GET", "/admin/settings"),
            ("POST", "/admin/settings"),
            ("GET", "/admin/users"),
            ("POST", "/admin/users/u-2/approve"),
            ("POST", "/admin/users/u-2/role"),
            ("POST", "/admin/users/u-2/deny"),
            ("GET", "/admin/users/u-2/merge"),
            ("POST", "/admin/users/u-2/merge"),
        ],
    )
    def test_non_admin_redirected_without_api_writes(
        self,
        client: FlaskClient,
        use_context,
        fake_vclient,
        *,
        role: UserRole,
        method: str,
        path: str,
    ) -> None:
        """Verify a non-admin is redirected home with an error and nothing reaches the API."""
        # Given a non-admin user
        use_context(user_role=role)

        # When requesting an admin page or action
        data = {"csrf_token": get_csrf(client), "role": "ADMIN", "target_user_id": "u-3"}
        response = client.open(path, method=method, data=data if method == "POST" else None)

        # Then the user is sent home with an error flash and the API sees no request
        assert_redirects_to(response, "/")
        assert [cat for cat, _ in session_flashes(client)] == ["error"]
        assert fake_vclient.requests == []


class TestSettingsGet:
    """GET /admin/settings renders the form pre-populated from the company."""

    @pytest.fixture
    def company(self, admin_context, fake_vclient) -> Company:
        """Serve a known company from the API."""
        company = CompanyFactory.build(
            id="test-company-id",
            name="Acme Co",
            email="admin@acme.example",
            description="A test company",
            settings=CompanySettings(
                id="settings-1",
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
                specialty_rules="RATING_BASED",
            ),
        )
        fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
        return company

    @pytest.mark.usefixtures("company")
    def test_fetches_session_company(self, client: FlaskClient, fake_vclient) -> None:
        """Verify the page fetches the session's company from the API."""
        response = client.get("/admin/settings")

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.COMPANIES_GET, params={"company_id": "test-company-id"}, times=1
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("name", "Acme Co"),
            ("email", "admin@acme.example"),
            ("character_autogen_xp_cost", "15"),
            ("character_autogen_starting_points", "25"),
            ("custom_flaw_xp_cost", "7"),
        ],
    )
    @pytest.mark.usefixtures("company")
    def test_inputs_prepopulated_from_company(
        self, client: FlaskClient, field: str, value: str
    ) -> None:
        """Verify each text input holds the company's saved value."""
        body = client.get("/admin/settings").get_data(as_text=True)

        assert f'value="{value}"' in _input_tag(body, field)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("permission_manage_npc", "STORYTELLER"),
            ("permission_grant_xp", "UNRESTRICTED"),
            ("specialty_rules", "RATING_BASED"),
        ],
    )
    @pytest.mark.usefixtures("company")
    def test_selects_show_saved_value(self, client: FlaskClient, field: str, value: str) -> None:
        """Verify each select has the company's saved option selected."""
        body = client.get("/admin/settings").get_data(as_text=True)

        select = re.search(rf'<select[^>]*name="{field}".*?</select>', body, re.DOTALL)
        assert select is not None, f"no select named {field}"
        option = re.search(rf'<option value="{value}"[^>]*>', select.group(0))
        assert option is not None
        assert "selected" in option.group(0)

    @pytest.mark.parametrize("enabled", [True, False])
    def test_specialty_cost_toggle_reflects_setting(
        self, client: FlaskClient, company: Company, fake_vclient, *, enabled: bool
    ) -> None:
        """Verify the specialty cost toggle is checked exactly when the setting is on."""
        company.settings.specialty_xp_cost_enabled = enabled
        fake_vclient.set_response(Routes.COMPANIES_GET, model=company)

        body = client.get("/admin/settings").get_data(as_text=True)

        assert ("checked" in _input_tag(body, "specialty_xp_cost_enabled")) is enabled


class TestSettingsPostSuccess:
    """POST /admin/settings happy path."""

    @pytest.mark.usefixtures("_company_api")
    def test_post_valid_sends_update_and_redirects(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a valid POST sends the update, flashes success, and redirects to settings."""
        response = client.post(
            "/admin/settings",
            data={
                "csrf_token": get_csrf(client),
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
                "specialty_rules": "RATING_BASED",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin/settings")
        assert [cat for cat, _ in session_flashes(client)] == ["success"]

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
                    "specialty_rules": "RATING_BASED",
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
    def test_post_blank_optional_fields_are_left_out(
        self, client: FlaskClient, fake_vclient
    ) -> None:
        """Verify blank optional fields are left out, except description, which is cleared."""
        client.post(
            "/admin/settings",
            data={
                "csrf_token": get_csrf(client),
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
            json={
                "name": "Required Name",
                "description": None,
                "settings": {"specialty_xp_cost_enabled": False},
            },
            times=1,
        )


class TestSettingsPostValidation:
    """POST /admin/settings validation error path."""

    @pytest.mark.parametrize(
        ("extra", "expect_checked"),
        [({"specialty_xp_cost_enabled": "on"}, True), ({}, False)],
    )
    @pytest.mark.usefixtures("_company_api")
    def test_rerender_preserves_specialty_toggle(
        self,
        client: FlaskClient,
        fake_vclient,
        extra: dict[str, str],
        *,
        expect_checked: bool,
    ) -> None:
        """Verify a 400 re-render keeps the submitted toggle state."""
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
        assert ("checked" in _input_tag(body, "specialty_xp_cost_enabled")) is expect_checked
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("name", "Hi"),
            ("character_autogen_xp_cost", "not-a-number"),
            ("character_autogen_num_choices", "not-a-number"),
            ("character_autogen_starting_points", "not-a-number"),
            ("custom_flaw_xp_cost", "not-a-number"),
            ("permission_manage_campaign", "TOTALLY_FAKE_VALUE"),
        ],
    )
    @pytest.mark.usefixtures("_company_api")
    def test_invalid_field_returns_400_and_preserves_input(
        self, client: FlaskClient, fake_vclient, field: str, bad_value: str
    ) -> None:
        """Verify an invalid field re-renders with 400, keeps the input, and sends nothing."""
        # Given a payload where one field is invalid
        data = {"csrf_token": get_csrf(client), "name": "Valid Name", field: bad_value}

        # When posting to the settings endpoint
        response = client.post("/admin/settings", data=data)

        # Then the form re-renders with the submitted name and no update is issued
        assert response.status_code == 400
        body = response.get_data(as_text=True)
        assert f'value="{data["name"]}"' in _input_tag(body, "name")
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)

    @pytest.mark.usefixtures("_company_api")
    def test_post_missing_csrf_returns_400(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a POST without a CSRF token returns 400."""
        response = client.post("/admin/settings", data={"name": "Valid Name"})
        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.COMPANIES_UPDATE)
