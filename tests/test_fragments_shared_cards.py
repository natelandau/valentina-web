"""Tests for the shared_cards blueprint (/cards/*)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from vclient.testing import AuditLogFactory, CharacterFactory, RollStatisticsFactory, Routes

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture
    from vclient.models.audit_logs import AuditLog


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


@pytest.fixture
def _audit_log_rows(fake_vclient, mock_global_context) -> list[AuditLog]:
    """Seed the fake vclient with a default page of audit logs."""
    user = mock_global_context.users[0]
    logs = [
        AuditLogFactory.build(
            acting_user_id=user.id,
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
            changes=None,
        )
        for _ in range(3)
    ]
    fake_vclient.set_response(
        Routes.COMPANIES_AUDIT_LOGS_LIST,
        items=[log.model_dump(mode="json") for log in logs],
    )
    return logs


class TestAuditLogCardEndpoint:
    """Tests for GET /cards/audit-log."""

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_no_filters_returns_200(self, client: FlaskClient) -> None:
        """Verify an unscoped request renders a 200 response."""
        # When requesting /cards/audit-log with no filters
        response = client.get("/cards/audit-log")

        # Then the response is 200
        assert response.status_code == 200

    def test_filters_forwarded_to_vclient(
        self, client: FlaskClient, mock_global_context, mocker
    ) -> None:
        """Verify all filter query args are forwarded to get_audit_log_page."""
        # Given a patched get_audit_log_page
        mock_page = mocker.MagicMock(items=[], has_more=False, total=0)
        mock_fn = mocker.patch(
            "vweb.routes.fragments_shared_cards.views.get_audit_log_page",
            autospec=True,
            return_value=mock_page,
        )

        # When requesting with all six filter kwargs populated
        response = client.get(
            "/cards/audit-log"
            "?acting_user_id=a1&user_id=u1&campaign_id=c1"
            "&book_id=b1&chapter_id=ch1&character_id=char1"
            "&page_size=15&offset=30"
        )

        # Then the helper receives every filter by keyword
        assert response.status_code == 200
        kwargs = mock_fn.call_args.kwargs
        assert kwargs["acting_user_id"] == "a1"
        assert kwargs["user_id"] == "u1"
        assert kwargs["campaign_id"] == "c1"
        assert kwargs["book_id"] == "b1"
        assert kwargs["chapter_id"] == "ch1"
        assert kwargs["character_id"] == "char1"
        assert kwargs["limit"] == 15
        assert kwargs["offset"] == 30

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_renders_full_card_on_initial_load(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify the initial load response contains the full card shell."""
        # When requesting /cards/audit-log with no body_only flag
        response = client.get("/cards/audit-log")

        # Then the response contains the card chrome
        assert response.status_code == 200
        assert b'class="card surface-card' in response.data
        assert b"Audit Log" in response.data  # default title

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_acting_user_name_rendered(self, client: FlaskClient, mock_global_context) -> None:
        """Verify the acting user's username appears in the output."""
        # Given a row with an acting_user_id matching a known user
        user = mock_global_context.users[0]

        # When requesting the card
        response = client.get("/cards/audit-log")

        # Then the username shows in line 2
        assert user.username.encode() in response.data

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_custom_title_renders(self, client: FlaskClient, mock_global_context) -> None:
        """Verify a custom title query arg appears in the output."""
        # When requesting with a custom title
        response = client.get("/cards/audit-log?title=Recent+Changes")

        # Then the custom title is in the response
        assert b"Recent Changes" in response.data

    def test_empty_rows_shows_empty_message(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify the empty_message is rendered when no rows match."""
        # Given zero rows from vclient
        fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

        # When requesting with a custom empty_message
        response = client.get("/cards/audit-log?empty_message=Nothing+logged")

        # Then the empty message is in the response
        assert b"Nothing logged" in response.data

    def test_no_changes_hides_toggle(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify a row with changes=None has no expandable toggle (5a-A)."""
        # Given a log with changes=None
        log = AuditLogFactory.build(
            changes=None,
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[log.model_dump(mode="json")],
        )

        # When rendering the card
        response = client.get("/cards/audit-log")

        # Then the toggle button is not in the response
        assert b"Show changes" not in response.data

    def test_canonical_changes_render_old_new_grid(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify canonical {old, new} changes render in the Old/New grid."""
        # Given a log with a canonical change
        log = AuditLogFactory.build(
            changes={"name": {"old": "Alice", "new": "Bob"}},
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[log.model_dump(mode="json")],
        )

        # When rendering the card
        response = client.get("/cards/audit-log")

        # Then the toggle is present and both values appear
        assert b"Show changes" in response.data
        assert b"Alice" in response.data
        assert b"Bob" in response.data
        assert b"name" in response.data  # field-name row rendered

    def test_off_shape_changes_render_as_list(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify off-shape entries appear in the other-entries list (5c-A)."""
        # Given a log with a non-canonical change (flat scalar)
        log = AuditLogFactory.build(
            changes={"deleted_by": "user-1"},
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[log.model_dump(mode="json")],
        )

        # When rendering the card
        response = client.get("/cards/audit-log")

        # Then the toggle is present and the off-shape entry appears
        assert b"Show changes" in response.data
        assert b"deleted_by" in response.data
        assert b"user-1" in response.data

    def test_scope_filter_hides_redundant_entity_link(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify entity links matching an active scope filter are skipped."""
        # Given a log scoped by character, with that same character present
        character = CharacterFactory.build()
        mock_global_context.characters = [character]
        log = AuditLogFactory.build(
            character_id=character.id,
            user_id=None,
            campaign_id=None,
            book_id=None,
            chapter_id=None,
            changes=None,
        )
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[log.model_dump(mode="json")],
        )

        # When rendering the card scoped to that character
        response = client.get(f"/cards/audit-log?character_id={character.id}")

        # Then the "Character:" label is not in the output (scope-skip)
        assert b"Character:" not in response.data

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_prev_button_disabled_at_offset_zero(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify the Prev button is disabled when offset=0."""
        # When rendering the first page
        response = client.get("/cards/audit-log")

        # Then the Prev button tag carries the `disabled` attribute
        match = re.search(
            r'<button[^>]*aria-label="Previous page"[^>]*>',
            response.data.decode(),
        )
        assert match, "Previous page button not found"
        assert "disabled" in match.group(0)

    def test_next_button_disabled_when_no_more(
        self, client: FlaskClient, fake_vclient, mock_global_context
    ) -> None:
        """Verify the Next button is disabled when the API reports no more pages."""
        # Given a single-item page (fake_vclient sets total == len(items), so has_more=False)
        log = AuditLogFactory.build(
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
            changes=None,
        )
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[log.model_dump(mode="json")],
        )

        # When rendering
        response = client.get("/cards/audit-log")

        # Then the Next button tag carries the `disabled` attribute
        match = re.search(
            r'<button[^>]*aria-label="Next page"[^>]*>',
            response.data.decode(),
        )
        assert match, "Next page button not found"
        assert "disabled" in match.group(0)

    def test_pagination_urls_carry_filters(
        self, client: FlaskClient, mock_global_context, mocker
    ) -> None:
        """Verify Prev/Next URLs include active filters and body_only=true."""
        # Given a patched page with has_more=True (the fake client can't express
        # has_more=True because it always sets total == len(items); patch the helper.)
        items = [
            AuditLogFactory.build(
                user_id=None,
                campaign_id=None,
                character_id=None,
                book_id=None,
                chapter_id=None,
                changes=None,
            )
            for _ in range(10)
        ]
        mock_page = mocker.MagicMock(items=items, has_more=True, total=25, offset=0)
        mocker.patch(
            "vweb.routes.fragments_shared_cards.views.get_audit_log_page",
            autospec=True,
            return_value=mock_page,
        )

        # When rendering with an active filter
        response = client.get("/cards/audit-log?campaign_id=c-1")

        # Then Next URL carries the filter and body_only flag
        html = response.data.decode()
        assert "body_only=true" in html
        assert "campaign_id=c-1" in html
        assert "offset=10" in html  # next page offset

        # And empty-valued filters are NOT in the URL (build_fragment_url drops them)
        assert "acting_user_id=" not in html
        assert "user_id=" not in html
        assert "character_id=" not in html

    @pytest.mark.usefixtures("_audit_log_rows")
    def test_body_only_renders_body_without_card_chrome(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify body_only=true renders the inner body without outer card shell."""
        # When requesting with body_only=true
        response = client.get("/cards/audit-log?body_only=true")

        # Then the full-card chrome is NOT in the output but the list IS
        assert response.status_code == 200
        # The outer card shell is absent
        assert b'id="auditlog"' not in response.data
        # But the list of rows is present
        assert b'class="list ' in response.data

    def test_body_only_pagination_urls_are_also_body_only(
        self, client: FlaskClient, mock_global_context, mocker
    ) -> None:
        """Verify Prev/Next URLs inside a body_only response still carry body_only=true."""
        # Given a patched page with has_more=True
        items = [
            AuditLogFactory.build(
                user_id=None,
                campaign_id=None,
                character_id=None,
                book_id=None,
                chapter_id=None,
                changes=None,
            )
            for _ in range(5)
        ]
        mock_page = mocker.MagicMock(items=items, has_more=True, total=25, offset=10)
        mocker.patch(
            "vweb.routes.fragments_shared_cards.views.get_audit_log_page",
            autospec=True,
            return_value=mock_page,
        )

        # When requesting a body_only page with an active filter and non-zero offset
        response = client.get("/cards/audit-log?offset=10&body_only=true&campaign_id=c-1")

        # Then the outer card chrome is absent (body_only render confirmed)
        html = response.data.decode()
        assert 'id="auditlog"' not in html
        # And pagination links still carry body_only=true plus the active filter
        assert "body_only=true" in html
        assert "campaign_id=c-1" in html


class TestAuditLogWrapperComponent:
    """Tests that the <shared.cards.AuditLog /> wrapper renders correct HTMX."""

    def test_wrapper_points_at_audit_log_endpoint(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify the wrapper's hx-get URL targets /cards/audit-log."""
        # Given an app context for url_for
        from vweb import catalog

        # When rendering the wrapper with a character scope
        with client.application.test_request_context():
            html = catalog.render("shared.cards.AuditLog", character_id="ch-1", page_size=15)

        # Then the hx-get URL is /cards/audit-log with filters in the query
        assert "/cards/audit-log" in html
        assert "character_id=ch-1" in html
        assert "page_size=15" in html
        assert 'hx-trigger="load"' in html

    def test_wrapper_drops_empty_filter_kwargs(
        self, client: FlaskClient, mock_global_context
    ) -> None:
        """Verify unset filter kwargs don't appear as empty query args."""
        from vweb import catalog

        # When rendering the wrapper with only one filter set
        with client.application.test_request_context():
            html = catalog.render("shared.cards.AuditLog", campaign_id="c-1")

        # Then other filter kwargs are absent from the URL
        assert "user_id=" not in html
        assert "character_id=" not in html
        assert "book_id=" not in html
