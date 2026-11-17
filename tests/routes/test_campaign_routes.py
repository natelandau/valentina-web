"""Tests for campaign blueprint routes."""

import re

import pytest
from werkzeug.test import TestResponse

from tests.conftest import get_csrf
from tests.helpers import assert_has_element, build_global_context
from vweb.api_client.testing import (
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    Routes,
    UserFactory,
)
from vweb.lib.cache.global_context import GlobalContext


class TestCampaignView:
    """Tests for GET /campaign/<campaign_id>."""

    def test_renders_campaign_dashboard(self, client, mock_global_context) -> None:
        """Verify the campaign dashboard renders for a valid campaign ID."""
        # Given a valid campaign from the global context
        campaign = mock_global_context.campaigns[0]

        # When requesting the campaign page
        response = client.get(f"/campaign/{campaign.id}")

        # Then the dashboard renders successfully
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert campaign.name in body
        # And the lazy-load placeholders for Recent Dicerolls and Statistics are wired
        assert "/cards/dice-rolls?campaign_id=" + campaign.id in body
        assert "/cards/statistics?campaign_id=" + campaign.id in body

    def test_stores_campaign_in_session(self, client, mock_global_context) -> None:
        """Verify the selected campaign ID is stored in the session."""
        # Given a valid campaign
        campaign = mock_global_context.campaigns[0]

        # When visiting the campaign page
        client.get(f"/campaign/{campaign.id}")

        # Then the session stores the last campaign ID
        with client.session_transaction() as sess:
            assert sess["last_campaign_id"] == campaign.id

    def test_returns_404_for_invalid_campaign(self, client) -> None:
        """Verify 404 is returned for a non-existent campaign ID."""
        # When requesting a campaign that doesn't exist
        response = client.get("/campaign/nonexistent-id")

        # Then a 404 is returned
        assert response.status_code == 404

    def test_separates_user_and_other_characters(self, client, mocker) -> None:
        """Verify characters are split by ownership."""
        # Given a campaign with characters from different users
        campaign = CampaignFactory.build(name="Test Campaign")
        company = CompanyFactory.build(name="Test Company")
        user = UserFactory.build(
            id="test-user-id",
            name_first="Test",
            name_last="User",
            company_id="test-company-id",
        )
        my_char = CharacterFactory.build(
            name_full="My Character",
            user_player_id="test-user-id",
            type="PLAYER",
            campaign_id=campaign.id,
        )
        other_char = CharacterFactory.build(
            name_full="Other Character",
            user_player_id="other-user-id",
            type="PLAYER",
            campaign_id=campaign.id,
        )
        ctx = GlobalContext(
            company=company,
            users=[user],
            campaigns=[campaign],
            characters_by_campaign={campaign.id: [my_char, other_char]},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting the campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then both characters appear
        assert response.status_code == 200
        assert "Your Characters" in body
        # Autoescaping renders the apostrophe in the card title as &#39;
        assert "Other Players&#39; Characters" in body

    def test_empty_characters_shows_message(self, client, mock_global_context) -> None:
        """Verify empty state messages when no characters exist."""
        # Given a campaign with no characters
        campaign = mock_global_context.campaigns[0]

        # When requesting the campaign page
        response = client.get(f"/campaign/{campaign.id}")

        # Then the page renders successfully with no characters
        assert response.status_code == 200

    def test_no_campaign_experience_shows_zeros(self, client, mocker) -> None:
        """Verify campaign profile renders with zero values when user has no experience."""
        # Given a user with no campaign experience
        campaign = CampaignFactory.build(name="Test Campaign")
        company = CompanyFactory.build(name="Test Company")
        user = UserFactory.build(
            id="test-user-id", company_id="test-company-id", campaign_experience=[]
        )
        ctx = GlobalContext(
            company=company,
            users=[user],
            campaigns=[campaign],
            characters_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting the campaign page
        response = client.get(f"/campaign/{campaign.id}")

        # Then the experience card renders (with zero values since no campaign experience)
        assert response.status_code == 200


class TestCampaignEditFormView:
    """Tests for GET /campaign/<campaign_id>/edit-form."""

    def test_returns_prefilled_form(self, client, mocker) -> None:
        """Verify the edit form returns with campaign data pre-filled."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When requesting the edit form
        response = client.get(f"/campaign/{campaign.id}/edit-form")

        # Then the form renders with the campaign name pre-filled
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert campaign.name in body

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot access the edit form."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When requesting the edit form
        campaign = ctx.campaigns[0]
        response = client.get(f"/campaign/{campaign.id}/edit-form")

        # Then a 403 is returned
        assert response.status_code == 403

    def test_returns_404_for_nonexistent_campaign(self, client, mocker) -> None:
        """Verify 404 is returned for a non-existent campaign."""
        # Given a STORYTELLER user (must be privileged to reach the 404 path)
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When requesting the edit form for a nonexistent campaign
        response = client.get("/campaign/nonexistent-id/edit-form")

        # Then a 404 is returned
        assert response.status_code == 404


class TestCampaignCreateView:
    """Tests for POST /campaign/create."""

    def test_creates_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful creation returns HX-Redirect."""
        # Given a STORYTELLER user and an API returning the new campaign
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        new_campaign = CampaignFactory.build(name="New Campaign")
        fake_vclient.set_response(Routes.CAMPAIGNS_CREATE, model=new_campaign)

        # When submitting a valid campaign creation form
        csrf = get_csrf(client)
        response = client.post(
            "/campaign/create",
            data={"name": "New Campaign", "description": "A test campaign"},
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response redirects to the new campaign
        assert response.status_code == 200
        assert f"/campaign/{new_campaign.id}" in response.headers.get("HX-Redirect", "")
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_CREATE,
            json={"name": "New Campaign", "description": "A test campaign"},
            times=1,
        )

    @pytest.mark.parametrize(
        ("name", "message"),
        [("Ab", "Name must be at least 3 characters"), ("", "Name is required")],
    )
    def test_invalid_name_rerenders_form(self, client, mocker, fake_vclient, name, message) -> None:
        """Verify an invalid name shows a form error and sends nothing to the API."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When submitting the form with an invalid name
        response = client.post(
            "/campaign/create",
            data={"name": name},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then the form shows the error and the API is not called
        assert response.status_code == 200
        assert message in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_CREATE)

    def test_api_rejection_rerenders_form_with_its_reason(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a validation error from the API shows on the form instead of a server error."""
        # Given a STORYTELLER user and an API that rejects the name
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_error(
            Routes.CAMPAIGNS_CREATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        # When submitting the form
        response = client.post(
            "/campaign/create",
            data={"name": "Taken Name"},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then the form shows the API's reason
        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)

    def test_returns_403_for_player_role(self, client, mocker) -> None:
        """Verify players cannot create campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to create a campaign
        csrf = get_csrf(client)
        response = client.post(
            "/campaign/create",
            data={"name": "Test"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 403 is returned
        assert response.status_code == 403


class TestNavbarCampaignDropdown:
    """Tests for campaign dropdown rendering in the navbar."""

    def test_navbar_lists_all_campaigns(self, client, mocker) -> None:
        """Verify the navbar dropdown lists all campaigns."""
        # Given multiple campaigns
        camp1 = CampaignFactory.build(name="Alpha Campaign")
        camp2 = CampaignFactory.build(name="Beta Campaign")
        company = CompanyFactory.build(name="Test Company")
        user = UserFactory.build(id="test-user-id", company_id="test-company-id")
        ctx = GlobalContext(
            company=company,
            users=[user],
            campaigns=[camp1, camp2],
            characters_by_campaign={camp1.id: [], camp2.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting a campaign page
        response = client.get(f"/campaign/{camp1.id}")
        body = response.get_data(as_text=True)

        # Then both campaigns appear in the navbar
        assert "Alpha Campaign" in body
        assert "Beta Campaign" in body

    def test_navbar_hides_add_button_for_players(self, client, mocker) -> None:
        """Verify the Add New Campaign button is hidden for PLAYER role."""
        # Given a PLAYER user
        campaign = CampaignFactory.build(name="Test Campaign")
        company = CompanyFactory.build(name="Test Company")
        user = UserFactory.build(id="test-user-id", role="PLAYER", company_id="test-company-id")
        ctx = GlobalContext(
            company=company,
            users=[user],
            campaigns=[campaign],
            characters_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting a campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the add button is not present
        assert "+ Create Campaign" not in body

    def test_navbar_shows_add_button_for_storyteller(self, client, mocker) -> None:
        """Verify the Add New Campaign button is visible for STORYTELLER role."""
        # Given a STORYTELLER user
        campaign = CampaignFactory.build(name="Test Campaign")
        company = CompanyFactory.build(name="Test Company")
        user = UserFactory.build(
            id="test-user-id", role="STORYTELLER", company_id="test-company-id"
        )
        ctx = GlobalContext(
            company=company,
            users=[user],
            campaigns=[campaign],
            characters_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When visiting a campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the add button is present
        assert "+ Create Campaign" in body


class TestCampaignInGameDate:
    """The campaign form sets the in-game date that character ages are measured on."""

    @pytest.fixture(autouse=True)
    def _storyteller(self, mocker) -> None:
        self.ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=self.ctx)

    def _post(self, client, url: str, data: dict[str, str]) -> TestResponse:
        return client.post(
            url, data=data, headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"}
        )

    def test_create_sends_in_game_date(self, client, fake_vclient) -> None:
        """Verify a submitted in-game date reaches the create request."""
        fake_vclient.set_response(Routes.CAMPAIGNS_CREATE, model=CampaignFactory.build())

        self._post(client, "/campaign/create", {"name": "Noir", "in_game_date": "1990-06-01"})

        fake_vclient.assert_called(
            Routes.CAMPAIGNS_CREATE, json={"name": "Noir", "in_game_date": "1990-06-01"}, times=1
        )

    def test_update_sends_in_game_date(self, client, fake_vclient) -> None:
        """Verify moving the in-game date forward reaches the update request."""
        campaign = self.ctx.campaigns[0]
        fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=campaign)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)

        self._post(
            client,
            f"/campaign/{campaign.id}/update",
            {"name": campaign.name, "in_game_date": "2003-01-01"},
        )

        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE, json_subset={"in_game_date": "2003-01-01"}, times=1
        )

    def test_update_blank_date_clears_it(self, client, fake_vclient) -> None:
        """Verify blanking the in-game date sends null so the API clears it."""
        campaign = self.ctx.campaigns[0]
        fake_vclient.set_response(Routes.CAMPAIGNS_GET, model=campaign)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)

        self._post(
            client, f"/campaign/{campaign.id}/update", {"name": campaign.name, "in_game_date": ""}
        )

        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE, json_subset={"in_game_date": None}, times=1
        )

    def test_rejects_invalid_in_game_date(self, client, fake_vclient) -> None:
        """Verify an impossible date re-renders the form with an error and saves nothing."""
        response = self._post(
            client, "/campaign/create", {"name": "Noir", "in_game_date": "1990-02-31"}
        )

        assert "In-game date must be a valid date." in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_CREATE)

    def test_player_cannot_set_in_game_date(self, client, mocker, fake_vclient) -> None:
        """Verify only users who manage campaigns can change the in-game date."""
        ctx = build_global_context(user_role="PLAYER")
        ctx.company.settings.permission_manage_campaign = "STORYTELLER"
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        campaign = ctx.campaigns[0]

        response = self._post(
            client,
            f"/campaign/{campaign.id}/update",
            {"name": campaign.name, "in_game_date": "2003-01-01"},
        )

        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_UPDATE)


class TestCampaignUpdateView:
    """Tests for POST /campaign/<campaign_id>/update."""

    def test_updates_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful update returns HX-Redirect."""
        # Given a STORYTELLER user and an API returning the updated campaign
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)

        # When submitting a valid update form
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Updated Name", "description": "Updated desc"},
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response redirects to the campaign page
        assert response.status_code == 200
        assert f"/campaign/{campaign.id}" in response.headers.get("HX-Redirect", "")
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": campaign.id},
            json={"name": "Updated Name", "description": "Updated desc"},
            times=1,
        )

    def test_short_name_rerenders_form(self, client, mocker, fake_vclient) -> None:
        """Verify a name under 3 characters shows a form error and sends nothing."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When submitting a short name
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Ab", "description": "Kept"},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then the form shows the error and the API is not called
        assert response.status_code == 200
        assert "Name must be at least 3 characters" in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_UPDATE)

    def test_cleared_description_is_sent_to_the_api(self, client, mocker, fake_vclient) -> None:
        """Verify clearing a saved description sends an empty string, which the API clears."""
        # Given a STORYTELLER user and a campaign with a description
        campaign = CampaignFactory.build(description="A saved description")
        ctx = build_global_context(user_role="STORYTELLER", campaign=campaign)
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)

        # When submitting the form with the description emptied
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Good Name", "description": ""},
            headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"},
        )

        # Then the empty description reaches the API
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": campaign.id},
            json={"name": "Good Name", "description": ""},
            times=1,
        )

    def test_api_rejection_rerenders_form_with_its_reason(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a validation error from the API shows on the edit form."""
        # Given a STORYTELLER user and an API that rejects the name
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_error(
            Routes.CAMPAIGNS_UPDATE,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        # When submitting the form
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Taken Name", "description": "A saved description"},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then the form shows the API's reason
        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot update campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to update a campaign
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Test"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_returns_404_for_nonexistent_campaign(self, client, mocker) -> None:
        """Verify 404 is returned for a non-existent campaign."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to update a nonexistent campaign
        csrf = get_csrf(client)
        response = client.post(
            "/campaign/nonexistent-id/update",
            data={"name": "Test Name"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 404 is returned
        assert response.status_code == 404


class TestCampaignUpdateDangerDesperationView:
    """Tests for POST /campaign/<campaign_id>/update/<field>."""

    def test_updates_danger_and_returns_badge(self, client, mocker, fake_vclient) -> None:
        """Verify a storyteller can update danger and receive re-rendered badges."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        updated_campaign = CampaignFactory.build(id=campaign.id, danger=3, desperation=0)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=updated_campaign)

        # When posting a danger value update
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update/danger",
            data={"value": "3"},
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the badge partial is returned
        assert response.status_code == 200
        assert_has_element(response, id="danger-desperation-badges")
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": campaign.id},
            json={"danger": 3},
            times=1,
        )

    def test_updates_desperation(self, client, mocker, fake_vclient) -> None:
        """Verify a storyteller can update desperation."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)

        # When posting a desperation value update
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update/desperation",
            data={"value": "4"},
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response succeeds
        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": campaign.id},
            json={"desperation": 4},
            times=1,
        )

    def test_clears_global_context_cache(self, client, mocker, fake_vclient) -> None:
        """Verify cache is cleared after a successful update."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=campaign)
        mock_clear = mocker.patch("vweb.lib.cache.global_context.clear")

        # When posting a valid update
        csrf = get_csrf(client)
        client.post(
            f"/campaign/{campaign.id}/update/danger",
            data={"value": "2"},
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the global context cache is cleared
        mock_clear.assert_called_once()

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot update danger/desperation."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to update danger
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update/danger",
            data={"value": "3"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("invalid_field", "3"),
            ("danger", "abc"),
            ("danger", "7"),
            ("danger", "-1"),
        ],
        ids=["invalid-field", "non-integer", "over-max", "under-min"],
    )
    def test_returns_400_for_invalid_input(self, client, mocker, field, value) -> None:
        """Verify invalid field names and out-of-range values return 400."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When posting invalid input
        csrf = get_csrf(client)
        response = client.post(
            f"/campaign/{campaign.id}/update/{field}",
            data={"value": value},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 400 is returned
        assert response.status_code == 400


class TestCampaignDeleteView:
    """Tests for DELETE /campaign/<campaign_id>."""

    def test_deletes_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful delete returns HX-Redirect to home."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # Given the session has the campaign stored
        with client.session_transaction() as sess:
            sess["last_campaign_id"] = campaign.id

        # When sending a delete request
        csrf = get_csrf(client)
        response = client.delete(
            f"/campaign/{campaign.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response redirects to home
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/"
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_DELETE, params={"campaign_id": campaign.id}, times=1
        )

        # And the session no longer has the campaign ID
        with client.session_transaction() as sess:
            assert "last_campaign_id" not in sess

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot delete campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to delete a campaign
        csrf = get_csrf(client)
        response = client.delete(
            f"/campaign/{campaign.id}",
            headers={"X-CSRFToken": csrf},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_returns_404_for_nonexistent_campaign(self, client, mocker) -> None:
        """Verify 404 is returned for a non-existent campaign."""
        # Given a STORYTELLER user
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When attempting to delete a nonexistent campaign
        csrf = get_csrf(client)
        response = client.delete(
            "/campaign/nonexistent-id",
            headers={"X-CSRFToken": csrf},
        )

        # Then a 404 is returned
        assert response.status_code == 404


class TestCampaignSummaryCard:
    """Tests for the new top-of-page summary card on the campaign dashboard."""

    def test_renders_campaign_name_and_eyebrow(self, client, mock_global_context) -> None:
        """Verify the card shows the CAMPAIGN eyebrow and campaign name."""
        # Given an authenticated user with a campaign
        campaign = mock_global_context.campaigns[0]

        # When loading the campaign dashboard
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the eyebrow + title render inside the summary card
        assert response.status_code == 200
        assert 'id="campaign-summary-card"' in body
        # Eyebrow label
        assert "Campaign" in body
        # Title
        assert campaign.name in body

    def test_renders_start_date_pill(self, client, mock_global_context) -> None:
        """Verify the summary card shows a Started MMM YYYY pill from date_created."""
        campaign = mock_global_context.campaigns[0]

        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        expected = campaign.date_created.strftime("Started %b %Y")
        assert expected in body

    def test_hides_book_pill_when_no_books(self, client, mock_global_context) -> None:
        """Verify the book count pill is omitted when there are no books."""
        # Given a campaign with no books
        campaign = mock_global_context.campaigns[0]
        campaign.num_books = 0
        campaign.num_chapters = 0

        # When loading the campaign dashboard
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then neither the book nor the chapter count pill renders
        assert not re.search(r"\d+ books", body)
        assert "chapters" not in body

    def test_shows_book_count_pill(self, client, mock_global_context) -> None:
        """Verify the summary card shows book and chapter counts from campaign facets."""
        # Given a campaign with two books and five chapters
        campaign = mock_global_context.campaigns[0]
        campaign.num_books = 2
        campaign.num_chapters = 5

        # When loading the campaign dashboard
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the pill renders both the book and chapter counts
        assert response.status_code == 200
        assert "2 books" in body
        assert "5 chapters" in body

    def test_omits_page_header(self, client, mock_global_context) -> None:
        """Verify the old shared PageHeader 'Campaign' before_text no longer renders."""
        campaign = mock_global_context.campaigns[0]

        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # The old PageHeader put the before_text in a text-3xl font-thin
        # opacity-50 span. The new summary card uses a small uppercase
        # eyebrow instead — the old class signature should not appear.
        assert "text-3xl font-thin opacity-50" not in body

    def test_danger_desperation_renders_vertical_in_card(self, client, mock_global_context) -> None:
        """Verify the badges container stacks vertically at lg+ inside the summary card."""
        campaign = mock_global_context.campaigns[0]

        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # `lg:flex-col` is unique to the vertical prop branch — its presence
        # proves the badges wrap horizontally on mobile and stack at lg+.
        assert 'id="danger-desperation-badges"' in body
        assert "lg:flex-col" in body
