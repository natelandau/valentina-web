"""Tests for campaign blueprint routes."""

from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    UserFactory,
)

from tests.conftest import get_csrf
from tests.helpers import build_global_context
from vweb.lib.global_context import GlobalContext


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
            books_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When visiting the campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then both characters appear
        assert response.status_code == 200
        assert "My Character" in body
        assert "Other Character" in body

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
            books_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

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
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

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
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When requesting the edit form
        campaign = ctx.campaigns[0]
        response = client.get(f"/campaign/{campaign.id}/edit-form")

        # Then a 403 is returned
        assert response.status_code == 403

    def test_returns_404_for_nonexistent_campaign(self, client, mocker) -> None:
        """Verify 404 is returned for a non-existent campaign."""
        # Given a STORYTELLER user (must be privileged to reach the 404 path)
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When requesting the edit form for a nonexistent campaign
        response = client.get("/campaign/nonexistent-id/edit-form")

        # Then a 404 is returned
        assert response.status_code == 404


class TestCampaignCreateView:
    """Tests for POST /campaign/create."""

    def test_creates_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful creation returns HX-Redirect."""
        # Given a STORYTELLER user and a mocked campaign service
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        new_campaign = CampaignFactory.build(name="New Campaign")
        mock_service = mocker.MagicMock()
        mock_service.create.return_value = new_campaign
        mocker.patch("vweb.routes.campaign.views.sync_campaigns_service", return_value=mock_service)
        mocker.patch("vweb.routes.campaign.views.clear_global_context_cache")

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
        mock_service.create.assert_called_once()

    def test_returns_403_for_player_role(self, client, mocker) -> None:
        """Verify players cannot create campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When attempting to create a campaign
        csrf = get_csrf(client)
        response = client.post(
            "/campaign/create",
            data={"name": "Test"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_returns_errors_for_short_name(self, client, mocker) -> None:
        """Verify validation rejects names shorter than 3 characters."""
        # Given a CSRF token (must be fetched before mocking the catalog)
        csrf = get_csrf(client)

        # Given a STORYTELLER user and a mocked catalog object
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        mock_catalog = mocker.MagicMock()
        mock_catalog.render.return_value = "<div>Name must be at least 3 characters.</div>"
        mocker.patch("vweb.routes.campaign.views.catalog", mock_catalog)
        response = client.post(
            "/campaign/create",
            data={"name": "Ab"},
            headers={"X-CSRFToken": csrf},
        )

        # Then the error message is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "at least 3 characters" in body

    def test_returns_errors_for_empty_name(self, client, mocker) -> None:
        """Verify validation rejects empty name."""
        # Given a CSRF token (must be fetched before mocking the catalog)
        csrf = get_csrf(client)

        # Given a STORYTELLER user and a mocked catalog object
        ctx = build_global_context(user_role="STORYTELLER")
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        mock_catalog = mocker.MagicMock()
        mock_catalog.render.return_value = "<div>Name must be at least 3 characters.</div>"
        mocker.patch("vweb.routes.campaign.views.catalog", mock_catalog)
        response = client.post(
            "/campaign/create",
            data={"name": ""},
            headers={"X-CSRFToken": csrf},
        )

        # Then the error message is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "at least 3 characters" in body


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
            books_by_campaign={camp1.id: [], camp2.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

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
            books_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When visiting a campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the add button is not present
        assert "+ Add New Campaign" not in body

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
            books_by_campaign={campaign.id: []},
            resources_modified_at="2026-01-01T00:00:00+00:00",
        )
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When visiting a campaign page
        response = client.get(f"/campaign/{campaign.id}")
        body = response.get_data(as_text=True)

        # Then the add button is present
        assert "+ Add New Campaign" in body


class TestCampaignUpdateView:
    """Tests for POST /campaign/<campaign_id>/update."""

    def test_updates_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful update returns HX-Redirect."""
        # Given a STORYTELLER user and a mocked campaign service
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        mock_service = mocker.MagicMock()
        mock_service.update.return_value = campaign
        mocker.patch("vweb.routes.campaign.views.sync_campaigns_service", return_value=mock_service)
        mocker.patch("vweb.routes.campaign.views.clear_global_context_cache")

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
        mock_service.update.assert_called_once()

    def test_returns_validation_errors(self, client, mocker) -> None:
        """Verify validation errors re-render the form."""
        # Given a CSRF token
        csrf = get_csrf(client)

        # Given a STORYTELLER user and a mocked catalog
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        mock_catalog = mocker.MagicMock()
        mock_catalog.render.return_value = "<div>Name must be at least 3 characters.</div>"
        mocker.patch("vweb.routes.campaign.views.catalog", mock_catalog)

        # When submitting an invalid form
        response = client.post(
            f"/campaign/{campaign.id}/update",
            data={"name": "Ab"},
            headers={"X-CSRFToken": csrf},
        )

        # Then the error message is returned
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "at least 3 characters" in body

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot update campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

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
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When attempting to update a nonexistent campaign
        csrf = get_csrf(client)
        response = client.post(
            "/campaign/nonexistent-id/update",
            data={"name": "Test Name"},
            headers={"X-CSRFToken": csrf},
        )

        # Then a 404 is returned
        assert response.status_code == 404


class TestCampaignDeleteView:
    """Tests for DELETE /campaign/<campaign_id>."""

    def test_deletes_campaign_and_redirects(self, client, mocker, fake_vclient) -> None:
        """Verify successful delete returns HX-Redirect to home."""
        # Given a STORYTELLER user and a mocked campaign service
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)
        mock_service = mocker.MagicMock()
        mocker.patch("vweb.routes.campaign.views.sync_campaigns_service", return_value=mock_service)
        mocker.patch("vweb.routes.campaign.views.clear_global_context_cache")

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
        mock_service.delete.assert_called_once_with(campaign.id)

        # And the session no longer has the campaign ID
        with client.session_transaction() as sess:
            assert "last_campaign_id" not in sess

    def test_returns_403_for_player(self, client, mocker) -> None:
        """Verify players cannot delete campaigns."""
        # Given a PLAYER user
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

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
        mocker.patch("vweb.app.load_global_context", return_value=ctx)

        # When attempting to delete a nonexistent campaign
        csrf = get_csrf(client)
        response = client.delete(
            "/campaign/nonexistent-id",
            headers={"X-CSRFToken": csrf},
        )

        # Then a 404 is returned
        assert response.status_code == 404
