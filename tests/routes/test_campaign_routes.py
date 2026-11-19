"""Tests for campaign blueprint routes."""

from __future__ import annotations

import re

import pytest

from tests.conftest import get_csrf, htmx_post
from tests.helpers import assert_has_element, assert_shows_error
from vweb.api_client.testing import (
    CampaignExperienceFactory,
    CampaignFactory,
    Routes,
    UserFactory,
)
from vweb.lib.form_validation import CAMPAIGN_NAME_MIN_LENGTH, name_errors

CAMPAIGN_WRITE_ROUTES = (
    Routes.CAMPAIGNS_CREATE,
    Routes.CAMPAIGNS_UPDATE,
    Routes.CAMPAIGNS_DELETE,
    Routes.USERS_EXPERIENCE_XP_ADD,
    Routes.USERS_EXPERIENCE_CP_ADD,
)


class TestCampaignDashboard:
    """Tests for GET /campaign/<campaign_id>."""

    def test_renders_campaign_and_wires_lazy_cards(self, client, mock_global_context) -> None:
        """Verify the dashboard shows the campaign, loads its cards, and remembers the campaign."""
        campaign = mock_global_context.campaigns[0]

        response = client.get(f"/campaign/{campaign.id}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert campaign.name in body
        # Dice rolls, statistics, and the player's and others' characters load lazily
        assert f"/cards/dice-rolls?campaign_id={campaign.id}" in body
        assert f"/cards/statistics?campaign_id={campaign.id}" in body
        assert "bucket=mine" in body
        assert "bucket=others" in body
        with client.session_transaction() as sess:
            assert sess["last_campaign_id"] == campaign.id

    def test_navbar_lists_all_campaigns(self, client, use_context) -> None:
        """Verify the navbar campaign switcher lists every campaign in the company."""
        camp1 = CampaignFactory.build(name="Alpha Campaign")
        camp2 = CampaignFactory.build(name="Beta Campaign")
        use_context(user_role="PLAYER", campaigns=[camp1, camp2])

        body = client.get(f"/campaign/{camp1.id}").get_data(as_text=True)

        assert "Alpha Campaign" in body
        assert "Beta Campaign" in body

    @pytest.mark.parametrize(("role", "can_manage"), [("STORYTELLER", True), ("PLAYER", False)])
    def test_manage_controls_only_for_managers(self, client, set_role, role, can_manage) -> None:
        """Verify only managers get the create and edit campaign controls."""
        campaign = set_role(role).campaigns[0]

        body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

        assert (f"/campaign/{campaign.id}/edit-form" in body) is can_manage
        assert ("getElementById('campaign-create-modal').showModal()" in body) is can_manage

    def test_summary_shows_start_month(self, client, mock_global_context) -> None:
        """Verify the summary card shows the month and year the campaign started."""
        campaign = mock_global_context.campaigns[0]

        body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

        assert campaign.date_created.strftime("%b %Y") in body

    @pytest.mark.parametrize(
        ("num_books", "num_chapters", "shows_counts"), [(2, 5, True), (0, 0, False)]
    )
    def test_summary_shows_book_and_chapter_counts(
        self, client, mock_global_context, num_books, num_chapters, shows_counts
    ) -> None:
        """Verify the summary card shows the campaign's book and chapter counts, if any."""
        campaign = mock_global_context.campaigns[0]
        campaign.num_books = num_books
        campaign.num_chapters = num_chapters

        body = client.get(f"/campaign/{campaign.id}").get_data(as_text=True)

        assert bool(re.search(r"\d+ books", body)) is shows_counts
        assert ("chapters" in body) is shows_counts
        if shows_counts:
            assert "2 books" in body
            assert "5 chapters" in body


class TestCampaignAccessControl:
    """Tests that players cannot manage campaigns or grant experience."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/campaign/create"),
            ("get", "/campaign/{id}/edit-form"),
            ("post", "/campaign/{id}/update"),
            ("post", "/campaign/{id}/update/danger"),
            ("delete", "/campaign/{id}"),
            ("get", "/campaign/{id}/experience/form"),
            ("post", "/campaign/{id}/experience"),
        ],
    )
    def test_player_is_forbidden(self, client, set_role, fake_vclient, method, path) -> None:
        """Verify a player gets 403 and nothing is written to the API."""
        # Given a player in a company that restricts campaign management and experience grants
        campaign = set_role("PLAYER").campaigns[0]

        # When the player sends the request directly
        response = getattr(client, method)(
            path.format(id=campaign.id),
            data={"name": "Test Name", "value": "3", "xp": "5"},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        # Then it is refused before any write
        assert response.status_code == 403
        for route in CAMPAIGN_WRITE_ROUTES:
            fake_vclient.assert_not_called(route)

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [("get", ""), ("get", "/edit-form"), ("post", "/update"), ("delete", "")],
    )
    @pytest.mark.usefixtures("storyteller")
    def test_unknown_campaign_returns_404(self, client, method, suffix) -> None:
        """Verify a campaign outside the company returns 404."""
        response = getattr(client, method)(
            f"/campaign/nonexistent-id{suffix}",
            data={"name": "Test Name"},
            headers={"X-CSRFToken": get_csrf(client)},
        )

        assert response.status_code == 404


class TestCampaignCreateAndUpdate:
    """Tests for the campaign create and edit modal."""

    def test_edit_form_is_prefilled(self, client, storyteller) -> None:
        """Verify the edit form opens with the campaign's current name."""
        response = client.get(f"/campaign/{storyteller.id}/edit-form")

        assert response.status_code == 200
        assert storyteller.name in response.get_data(as_text=True)

    def test_create_sends_campaign_and_redirects(self, client, storyteller, fake_vclient) -> None:
        """Verify a created campaign reaches the API and the client is sent to it."""
        new_campaign = CampaignFactory.build()
        fake_vclient.set_response(Routes.CAMPAIGNS_CREATE, model=new_campaign)

        response = htmx_post(
            client,
            "/campaign/create",
            {"name": "Noir", "description": "A test campaign", "in_game_date": "1990-06-01"},
        )

        assert response.headers.get("HX-Redirect") == f"/campaign/{new_campaign.id}"
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_CREATE,
            json={"name": "Noir", "description": "A test campaign", "in_game_date": "1990-06-01"},
            times=1,
        )

    @pytest.mark.parametrize(
        ("form", "expected_body"),
        [
            (
                {"name": "Updated Name", "description": "Updated desc"},
                {"name": "Updated Name", "description": "Updated desc"},
            ),
            ({"name": "Good Name", "description": ""}, {"name": "Good Name", "description": ""}),
            (
                {"name": "Good Name", "description": "", "in_game_date": "2003-01-01"},
                {"name": "Good Name", "description": "", "in_game_date": "2003-01-01"},
            ),
            (
                {"name": "Good Name", "description": "", "in_game_date": ""},
                {"name": "Good Name", "description": "", "in_game_date": None},
            ),
        ],
        ids=["values", "cleared-description", "new-date", "blank-date-clears"],
    )
    def test_update_sends_changes_and_redirects(
        self, client, storyteller, fake_vclient, form, expected_body
    ) -> None:
        """Verify edits reach the API, a blank field clears it, and an absent date is untouched."""
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=storyteller)

        response = htmx_post(client, f"/campaign/{storyteller.id}/update", form)

        assert response.headers.get("HX-Redirect") == f"/campaign/{storyteller.id}"
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": storyteller.id},
            json=expected_body,
            times=1,
        )

    @pytest.mark.parametrize("path", ["/campaign/create", "/campaign/{id}/update"])
    @pytest.mark.parametrize("name", ["Ab", ""], ids=["too-short", "blank"])
    def test_invalid_name_rerenders_form_without_calling_api(
        self, client, storyteller, fake_vclient, path, name
    ) -> None:
        """Verify an invalid name shows a form error and nothing reaches the API."""
        response = htmx_post(client, path.format(id=storyteller.id), {"name": name})

        assert response.status_code == 200
        expected = name_errors(name, min_length=CAMPAIGN_NAME_MIN_LENGTH)[0]
        assert expected in response.get_data(as_text=True)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_CREATE)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_UPDATE)

    def test_invalid_in_game_date_rerenders_form_without_calling_api(
        self, client, storyteller, fake_vclient
    ) -> None:
        """Verify an impossible in-game date shows a form error and nothing is saved."""
        response = htmx_post(
            client, "/campaign/create", {"name": "Noir", "in_game_date": "1990-02-31"}
        )

        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_CREATE)

    @pytest.mark.parametrize(
        ("path", "route"),
        [
            ("/campaign/create", Routes.CAMPAIGNS_CREATE),
            ("/campaign/{id}/update", Routes.CAMPAIGNS_UPDATE),
        ],
        ids=["create", "update"],
    )
    def test_api_rejection_rerenders_form_with_its_reason(
        self, client, storyteller, fake_vclient, path, route
    ) -> None:
        """Verify a validation error from the API shows on the form instead of a server error."""
        fake_vclient.set_error(
            route,
            status_code=400,
            invalid_parameters=[{"field": "name", "message": "Name is already taken"}],
        )

        response = htmx_post(client, path.format(id=storyteller.id), {"name": "Taken Name"})

        assert response.status_code == 200
        assert "Name is already taken" in response.get_data(as_text=True)


class TestCampaignUpdateDangerDesperation:
    """Tests for POST /campaign/<campaign_id>/update/<field>."""

    @pytest.mark.parametrize(("field", "value"), [("danger", 3), ("desperation", 4)])
    def test_sends_value_and_returns_badges(
        self, client, storyteller, fake_vclient, mocker, field, value
    ) -> None:
        """Verify the value reaches the API, the context is refreshed, and the badges re-render."""
        fake_vclient.set_response(Routes.CAMPAIGNS_UPDATE, model=storyteller)
        clear_context = mocker.patch("vweb.lib.cache.global_context.clear")

        response = htmx_post(
            client, f"/campaign/{storyteller.id}/update/{field}", {"value": str(value)}
        )

        assert response.status_code == 200
        assert_has_element(response, id="danger-desperation-badges")
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_UPDATE,
            params={"campaign_id": storyteller.id},
            json={field: value},
            times=1,
        )
        clear_context.assert_called_once()

    @pytest.mark.parametrize(
        ("field", "value"),
        [("invalid_field", "3"), ("danger", "abc"), ("danger", "7"), ("danger", "-1")],
        ids=["invalid-field", "non-integer", "over-max", "under-min"],
    )
    def test_invalid_input_returns_400(
        self, client, storyteller, fake_vclient, field, value
    ) -> None:
        """Verify invalid field names and out-of-range values return 400 and save nothing."""
        response = htmx_post(client, f"/campaign/{storyteller.id}/update/{field}", {"value": value})

        assert response.status_code == 400
        fake_vclient.assert_not_called(Routes.CAMPAIGNS_UPDATE)


class TestCampaignDelete:
    """Tests for DELETE /campaign/<campaign_id>."""

    def test_deletes_campaign_and_forgets_it(self, client, storyteller, fake_vclient) -> None:
        """Verify the campaign is deleted, dropped from the session, and the client goes home."""
        with client.session_transaction() as sess:
            sess["last_campaign_id"] = storyteller.id

        response = client.delete(
            f"/campaign/{storyteller.id}", headers={"X-CSRFToken": get_csrf(client)}
        )

        assert response.headers.get("HX-Redirect") == "/"
        fake_vclient.assert_called(
            Routes.CAMPAIGNS_DELETE, params={"campaign_id": storyteller.id}, times=1
        )
        with client.session_transaction() as sess:
            assert "last_campaign_id" not in sess


class TestCampaignExperience:
    """Tests for the campaign experience card and grant form."""

    def test_card_shows_users_campaign_xp(self, client, use_context) -> None:
        """Verify the experience card shows the user's XP in this campaign."""
        # Given a user with XP in the campaign
        campaign = CampaignFactory.build()
        user = UserFactory.build(
            id="test-user-id",
            campaign_experience=[
                CampaignExperienceFactory.build(campaign_id=campaign.id, xp_current=4321)
            ],
        )
        use_context(user_role="PLAYER", campaign=campaign, user=user)

        # When loading the experience card
        response = client.get(f"/campaign/{campaign.id}/experience")

        # Then the XP is shown
        assert response.status_code == 200
        assert b"4321" in response.data

    def test_form_names_the_campaign(self, client, storyteller) -> None:
        """Verify a storyteller gets the grant form for this campaign."""
        response = client.get(f"/campaign/{storyteller.id}/experience/form")

        assert response.status_code == 200
        assert storyteller.name in response.get_data(as_text=True)

    def test_grant_sends_xp_and_refreshes_card(self, client, storyteller, fake_vclient) -> None:
        """Verify a grant reaches the API and the experience card reloads."""
        response = htmx_post(
            client, f"/campaign/{storyteller.id}/experience", {"xp": "5", "cool_points": "0"}
        )

        assert response.status_code == 200
        fake_vclient.assert_called(
            Routes.USERS_EXPERIENCE_XP_ADD,
            params={"user_id": "test-user-id"},
            json_subset={"amount": 5, "campaign_id": storyteller.id},
            times=1,
        )
        assert f'hx-get="/campaign/{storyteller.id}/experience"' in response.get_data(as_text=True)

    def test_invalid_grant_rerenders_form_without_calling_api(
        self, client, storyteller, fake_vclient
    ) -> None:
        """Verify an invalid amount shows a form error and nothing is granted."""
        response = htmx_post(
            client, f"/campaign/{storyteller.id}/experience", {"xp": "-1", "cool_points": "0"}
        )

        assert response.status_code == 200
        assert_shows_error(response)
        fake_vclient.assert_not_called(Routes.USERS_EXPERIENCE_XP_ADD)


class TestCampaignNotesPage:
    """Tests for the campaign notes page."""

    @pytest.mark.parametrize(("role", "editable"), [("STORYTELLER", "true"), ("PLAYER", "false")])
    def test_loads_notes_table_editable_only_for_managers(
        self, client, set_role, role, editable
    ) -> None:
        """Verify the page lazy-loads the notes table, editable only for managers."""
        campaign = set_role(role).campaigns[0]

        response = client.get(f"/campaign/{campaign.id}/notes")

        assert response.status_code == 200
        expected = f"/campaign/{campaign.id}/notes/items?editable={editable}"
        assert expected in response.get_data(as_text=True)
