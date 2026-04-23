"""Tests for the shared_cards blueprint (/cards/*)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import RollStatisticsFactory

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture


@pytest.fixture
def mock_statistics(mocker: MockerFixture) -> MagicMock:
    """Mock the generic statistics helper to avoid real vclient calls."""
    stats = RollStatisticsFactory.build()
    mock = mocker.patch("vweb.routes.fragments_shared_cards.views.get_statistics", autospec=True)
    mock.return_value = stats
    return mock


class TestStatisticsCardEndpoint:
    """Tests for GET /cards/statistics."""

    def test_campaign_scope_renders_200(
        self, client: FlaskClient, mock_statistics: MagicMock, mock_global_context
    ) -> None:
        """Verify a campaign-scoped request renders the content partial."""
        # Given a campaign ID
        campaign_id = mock_global_context.campaigns[0].id

        # When requesting /cards/statistics with campaign_id
        response = client.get(f"/cards/statistics?campaign_id={campaign_id}")

        # Then the response is 200 and dispatches to the campaign scope
        assert response.status_code == 200
        mock_statistics.assert_called_once_with("campaign", campaign_id)

    def test_user_scope_renders_200(self, client: FlaskClient, mock_statistics: MagicMock) -> None:
        """Verify a user-scoped request dispatches to the user scope."""
        # When requesting /cards/statistics with user_id
        response = client.get("/cards/statistics?user_id=u-1")

        # Then the response is 200 and dispatches to the user scope
        assert response.status_code == 200
        mock_statistics.assert_called_once_with("user", "u-1")

    def test_character_scope_renders_200(
        self, client: FlaskClient, mock_statistics: MagicMock
    ) -> None:
        """Verify a character-scoped request dispatches to the character scope."""
        # When requesting /cards/statistics with character_id
        response = client.get("/cards/statistics?character_id=c-1")

        # Then the response is 200 and dispatches to the character scope
        assert response.status_code == 200
        mock_statistics.assert_called_once_with("character", "c-1")

    def test_no_scope_returns_400(self, client: FlaskClient) -> None:
        """Verify a request with no scope returns 400."""
        # When requesting /cards/statistics without any scope
        response = client.get("/cards/statistics")

        # Then the response is 400
        assert response.status_code == 400

    def test_multiple_scopes_returns_400(self, client: FlaskClient) -> None:
        """Verify a request with more than one scope returns 400."""
        # When requesting with two scopes set
        response = client.get("/cards/statistics?campaign_id=c1&user_id=u1")

        # Then the response is 400
        assert response.status_code == 400

    @pytest.mark.usefixtures("mock_statistics")
    def test_custom_title_renders_in_output(self, client: FlaskClient) -> None:
        """Verify a custom title query arg appears in the rendered HTML."""
        # When requesting with a custom title
        response = client.get("/cards/statistics?user_id=u-1&title=Custom+Title")

        # Then the title appears in the response body
        assert b"Custom Title" in response.data

    @pytest.mark.usefixtures("mock_statistics")
    def test_default_title_is_statistics(self, client: FlaskClient) -> None:
        """Verify the default title 'Statistics' is used when no title query arg is present."""
        # When requesting without a title
        response = client.get("/cards/statistics?user_id=u-1")

        # Then the default title appears in the response body
        assert b"Statistics" in response.data


@pytest.fixture
def mock_rolls(mocker: MockerFixture) -> MagicMock:
    """Mock get_recent_player_dicerolls to avoid real vclient calls."""
    mock = mocker.patch(
        "vweb.routes.fragments_shared_cards.views.get_recent_player_dicerolls",
        autospec=True,
    )
    mock.return_value = []
    return mock


class TestDiceRollsCardEndpoint:
    """Tests for GET /cards/dice-rolls."""

    def test_campaign_scope_renders_200(
        self, client: FlaskClient, mock_rolls: MagicMock, mock_global_context
    ) -> None:
        """Verify a campaign-scoped request calls the helper with campaign_id."""
        # Given a campaign ID
        campaign_id = mock_global_context.campaigns[0].id

        # When requesting /cards/dice-rolls with campaign_id
        response = client.get(f"/cards/dice-rolls?campaign_id={campaign_id}")

        # Then the response is 200 and the helper is called with the campaign scope
        assert response.status_code == 200
        mock_rolls.assert_called_once()
        kwargs = mock_rolls.call_args.kwargs
        assert kwargs.get("campaign_id") == campaign_id
        assert kwargs.get("character_id", "") == ""
        assert kwargs.get("user_id", "") == ""

    def test_character_scope_renders_200(self, client: FlaskClient, mock_rolls: MagicMock) -> None:
        """Verify a character-scoped request calls the helper with character_id."""
        # When requesting /cards/dice-rolls with character_id
        response = client.get("/cards/dice-rolls?character_id=c-1")

        # Then the helper is called with the character scope
        assert response.status_code == 200
        kwargs = mock_rolls.call_args.kwargs
        assert kwargs.get("character_id") == "c-1"

    def test_user_scope_renders_200(self, client: FlaskClient, mock_rolls: MagicMock) -> None:
        """Verify a user-scoped request calls the helper with user_id."""
        # When requesting /cards/dice-rolls with user_id
        response = client.get("/cards/dice-rolls?user_id=u-1")

        # Then the helper is called with the user scope
        assert response.status_code == 200
        kwargs = mock_rolls.call_args.kwargs
        assert kwargs.get("user_id") == "u-1"

    def test_combined_scopes_pass_all_filters(
        self, client: FlaskClient, mock_rolls: MagicMock
    ) -> None:
        """Verify combined scopes pass all filters to the helper (vclient ANDs them)."""
        # When requesting with all three scopes set
        response = client.get("/cards/dice-rolls?campaign_id=c1&character_id=ch1&user_id=u1")

        # Then all three filters are forwarded
        assert response.status_code == 200
        kwargs = mock_rolls.call_args.kwargs
        assert kwargs.get("campaign_id") == "c1"
        assert kwargs.get("character_id") == "ch1"
        assert kwargs.get("user_id") == "u1"

    def test_no_scope_returns_400(self, client: FlaskClient) -> None:
        """Verify a request with zero scopes returns 400."""
        # When requesting without any scope
        response = client.get("/cards/dice-rolls")

        # Then the response is 400
        assert response.status_code == 400

    def test_empty_message_appears_when_no_rolls(
        self, client: FlaskClient, mock_rolls: MagicMock
    ) -> None:
        """Verify the empty_message query arg flows through to the rendered card."""
        # When requesting with an empty_message query arg and no rolls
        response = client.get("/cards/dice-rolls?campaign_id=c1&empty_message=Nothing+here")

        # Then the empty message is in the response
        assert b"Nothing here" in response.data

    def test_title_flows_through(self, client: FlaskClient, mock_rolls: MagicMock) -> None:
        """Verify the title query arg appears in the rendered HTML."""
        # When requesting with a custom title
        response = client.get("/cards/dice-rolls?campaign_id=c1&title=My+Recent+Rolls")

        # Then the title appears in the response
        assert b"My Recent Rolls" in response.data


class TestStatisticsWrapperComponent:
    """Tests that the <shared.cards.Statistics /> wrapper renders correct HTMX."""

    def test_wrapper_hx_get_points_at_statistics_endpoint(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify the wrapper-rendered HTML includes an hx-get to /cards/statistics with scope."""
        # Given an app context for url_for resolution
        from vweb import catalog

        # When rendering the wrapper with a campaign scope
        with client.application.test_request_context():
            html = catalog.render("shared.cards.Statistics", campaign_id="camp-abc", col_span=2)

        # Then the hx-get URL is /cards/statistics with campaign_id and col_span in the query
        assert "/cards/statistics" in html
        assert "campaign_id=camp-abc" in html
        assert "col_span=2" in html
        assert 'hx-trigger="load"' in html
        assert 'hx-swap="outerHTML"' in html


class TestRecentDiceRollsWrapperComponent:
    """Tests that the <shared.cards.RecentDiceRolls /> wrapper renders correct HTMX."""

    def test_wrapper_hx_get_points_at_dice_rolls_endpoint(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify the wrapper-rendered HTML includes an hx-get to /cards/dice-rolls with scope."""
        # Given an app context
        from vweb import catalog

        # When rendering the wrapper with a character scope
        with client.application.test_request_context():
            html = catalog.render(
                "shared.cards.RecentDiceRolls", character_id="ch-1", pagination=10
            )

        # Then the hx-get URL is /cards/dice-rolls with character_id and pagination in the query
        assert "/cards/dice-rolls" in html
        assert "character_id=ch-1" in html
        assert "pagination=10" in html

    def test_wrapper_drops_empty_scope_kwargs(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify unused scope kwargs don't appear as empty query args."""
        # Given an app context
        from vweb import catalog

        # When rendering the wrapper with only one scope set
        with client.application.test_request_context():
            html = catalog.render("shared.cards.RecentDiceRolls", campaign_id="camp-1")

        # Then unused scope kwargs do NOT appear in the URL at all
        assert "user_id=" not in html
        assert "character_id=" not in html
