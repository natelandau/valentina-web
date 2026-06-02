"""Tests for the shared_cards blueprint (/cards/*)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from vclient.testing import (
    AuditLogFactory,
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    RollStatisticsFactory,
    Routes,
    UserFactory,
)

from vweb.lib.global_context import GlobalContext

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
            html = catalog.render("shared.cards.RecentDiceRolls", character_id="ch-1", page_size=10)

        # Then the hx-get URL is /cards/dice-rolls with character_id and page_size in the query
        assert "/cards/dice-rolls" in html
        assert "character_id=ch-1" in html
        assert "page_size=10" in html

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


@pytest.fixture
def audit_rows() -> list[AuditLog]:
    """Build audit log rows without seeding vclient, for use with _set_page."""
    return AuditLogFactory.batch(3)


def _set_page(mocker, items: list[AuditLog], *, has_more: bool = False) -> None:
    """Patch get_audit_log_page to return items with controllable has_more.

    The fake vclient always sets has_more=False (total == len(items)). This helper
    patches the helper directly so tests can express has_more=True without relying
    on the fake client's internal pagination logic.
    """
    mock_page = mocker.MagicMock(items=items, has_more=has_more, total=len(items) + int(has_more))
    mocker.patch(
        "vweb.routes.fragments_shared_cards.views.get_audit_log_page",
        autospec=True,
        return_value=mock_page,
    )


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
        """Verify all ten filter query args are forwarded to get_audit_log_page."""
        # Given a patched get_audit_log_page
        mock_page = mocker.MagicMock(items=[], has_more=False, total=0)
        mock_fn = mocker.patch(
            "vweb.routes.fragments_shared_cards.views.get_audit_log_page",
            autospec=True,
            return_value=mock_page,
        )

        # When requesting with all ten filter kwargs populated
        response = client.get(
            "/cards/audit-log"
            "?acting_user_id=a1&user_id=u1&campaign_id=c1"
            "&book_id=b1&chapter_id=ch1&character_id=char1"
            "&entity_type=CAMPAIGN&operation=UPDATE"
            "&date_from=2025-01-01&date_to=2025-02-01"
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
        assert kwargs["entity_type"] == "CAMPAIGN"
        assert kwargs["operation"] == "UPDATE"
        assert kwargs["date_from"] == "2025-01-01"
        assert kwargs["date_to"] == "2025-02-01"
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
            r'<button[^>]*aria-label="Newer entries"[^>]*>',
            response.data.decode(),
        )
        assert match, "Newer entries button not found"
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
            r'<button[^>]*aria-label="Older entries"[^>]*>',
            response.data.decode(),
        )
        assert match, "Older entries button not found"
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

    def test_admin_filters_threaded_into_pagination(
        self, client: FlaskClient, mocker: MockerFixture, audit_rows: list
    ) -> None:
        """Verify entity_type and operation filters appear in the pagination URLs."""
        # Given a full page with more available
        _set_page(mocker, audit_rows, has_more=True)

        # When requesting with admin filters set
        response = client.get(
            "/cards/audit-log?campaign_id=c1&entity_type=CAMPAIGN&operation=UPDATE&page_size=3"
        )

        # Then the filters are carried into the Next/Prev button URLs
        body = response.get_data(as_text=True)
        assert "entity_type=CAMPAIGN" in body
        assert "operation=UPDATE" in body

    def test_min_height_capped_for_large_page_size(
        self, client: FlaskClient, mocker, audit_rows: list
    ) -> None:
        """Verify the body min-height is capped so a large page_size does not over-stretch."""
        # Given an audit log page requested with a large page size
        _set_page(mocker, audit_rows, has_more=False)

        # When rendering with page_size well above the cap
        response = client.get("/cards/audit-log?campaign_id=c1&page_size=25")

        # Then min-height is capped at the 10-row equivalent (10 * 5.5 = 55.0rem)
        body = response.get_data(as_text=True)
        assert "min-height: 55.0rem" in body


class TestAuditLogFilters:
    """show_filters toggles the filter bar on the shared card."""

    def test_show_filters_renders_filter_bar(
        self, client: FlaskClient, mocker, audit_rows: list, mock_global_context
    ) -> None:
        """Verify show_filters=true renders the filter bar with options."""
        # Given an audit log page
        _set_page(mocker, audit_rows, has_more=False)

        # When requesting the card with filters enabled
        response = client.get("/cards/audit-log?show_filters=true")

        # Then the filter bar and its controls render
        body = response.get_data(as_text=True)
        assert "auditlog-filters" in body
        assert "Entity Type" in body
        assert "Operation" in body

        # And the acting-user dropdown is populated from the global context users
        user = mock_global_context.users[0]
        assert user.username in body

    def test_filters_hidden_by_default(self, client: FlaskClient, mocker, audit_rows: list) -> None:
        """Verify the filter bar is absent when show_filters is not set."""
        # Given an audit log page
        _set_page(mocker, audit_rows, has_more=False)

        # When requesting the card normally
        response = client.get("/cards/audit-log?campaign_id=c1")

        # Then no filter bar is rendered
        body = response.get_data(as_text=True)
        assert "auditlog-filters" not in body

    def test_filter_values_are_xss_safe(
        self, client: FlaskClient, mocker, audit_rows: list
    ) -> None:
        """Verify a quote-injection payload in a filter value cannot break out of the Alpine x-data string."""
        import re

        # Given a malicious filter value attempting JS string breakout
        _set_page(mocker, audit_rows, has_more=False)
        payload = "';alert(1)//"

        # When the filter bar is rendered with that value seeded back in
        response = client.get(f"/cards/audit-log?show_filters=true&entity_type={payload}")

        # Then the x-data block seeds the value with tojson unicode escaping (no JS breakout).
        # Pull out the x-data attribute specifically so pagination hx-get URLs don't interfere.
        body = response.get_data(as_text=True)
        match = re.search(r"x-data='(\{.*?\})'", body, re.DOTALL)
        assert match, "x-data block not found in response"
        x_data_block = match.group(0)

        # The raw single quote must NOT appear unescaped inside the x-data attribute
        assert "';alert(1)//" not in x_data_block  # no raw breakout
        assert "&#39;;alert(1)//" not in x_data_block  # no html-entity form the parser would decode
        # tojson encodes the single quote as ' to prevent JS string breakout
        assert "\\u0027;alert(1)//" in x_data_block

    def test_card_id_is_sanitized(self, client: FlaskClient, mocker, audit_rows: list) -> None:
        """Verify a malicious card_id is stripped to a DOM-id-safe slug, blocking injection."""
        # Given a card_id carrying a JS-breakout payload
        _set_page(mocker, audit_rows, has_more=False)
        payload = "x');alert(1)//"

        # When the card renders with that card_id
        response = client.get(f"/cards/audit-log?show_filters=true&card_id={payload}")

        # Then the dangerous characters are gone and only the safe slug remains
        body = response.get_data(as_text=True)
        assert "');alert(1)//" not in body
        assert "&#39;);alert(1)//" not in body
        assert 'id="xalert1-filters"' in body  # quotes/parens/semicolons/slashes stripped


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
        assert "show_filters=" not in html


def _character_context(
    characters: list, *, user_role: str = "PLAYER", campaign=None
) -> tuple[GlobalContext, object]:
    """Build a GlobalContext populated for the character list endpoint.

    Populates both ``characters_by_campaign`` (campaign scope) and ``characters``
    (user scope), and a requesting user with id ``test-user-id`` so visibility
    and bucket splits resolve.
    """
    campaign = campaign or CampaignFactory.build(name="Test Campaign")
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(id="test-user-id", company_id="test-company-id", role=user_role)

    by_campaign: dict[str, list] = {campaign.id: []}
    for character in characters:
        by_campaign.setdefault(character.campaign_id, []).append(character)

    ctx = GlobalContext(
        company=company,
        users=[user],
        campaigns=[campaign],
        characters_by_campaign=by_campaign,
        characters=list(characters),
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    return ctx, campaign


class TestCharacterListCardEndpoint:
    """Tests for GET /cards/character-list."""

    def test_no_scope_returns_400(self, client: FlaskClient) -> None:
        """Verify a request with neither campaign nor user scope is rejected."""
        # When requesting the card with no scope
        response = client.get("/cards/character-list")

        # Then the endpoint aborts with 400
        assert response.status_code == 400

    def test_campaign_scope_all_renders_roster(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify campaign scope with bucket=all renders every visible character."""
        # Given a campaign with two player characters from different owners
        campaign = CampaignFactory.build(name="Test Campaign")
        mine = CharacterFactory.build(
            name="My Hero", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        theirs = CharacterFactory.build(
            name="Their Hero", type="PLAYER", user_player_id="other-user", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([mine, theirs], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the all-bucket card
        response = client.get(f"/cards/character-list?campaign_id={campaign.id}&bucket=all")
        body = response.get_data(as_text=True)

        # Then both characters render
        assert response.status_code == 200
        assert "My Hero" in body
        assert "Their Hero" in body

    def test_bucket_mine_limits_to_session_user(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify bucket=mine shows only the requesting user's characters."""
        # Given a roster split across the session user and another owner
        campaign = CampaignFactory.build(name="Test Campaign")
        mine = CharacterFactory.build(
            name="My Hero", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        theirs = CharacterFactory.build(
            name="Their Hero", type="PLAYER", user_player_id="other-user", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([mine, theirs], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the mine bucket
        response = client.get(f"/cards/character-list?campaign_id={campaign.id}&bucket=mine")
        body = response.get_data(as_text=True)

        # Then only the session user's character renders
        assert "My Hero" in body
        assert "Their Hero" not in body

    def test_bucket_others_excludes_session_user(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify bucket=others hides the requesting user's characters."""
        # Given a roster split across the session user and another owner
        campaign = CampaignFactory.build(name="Test Campaign")
        mine = CharacterFactory.build(
            name="My Hero", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        theirs = CharacterFactory.build(
            name="Their Hero", type="PLAYER", user_player_id="other-user", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([mine, theirs], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the others bucket
        response = client.get(f"/cards/character-list?campaign_id={campaign.id}&bucket=others")
        body = response.get_data(as_text=True)

        # Then only the other owner's character renders
        assert "Their Hero" in body
        assert "My Hero" not in body

    def test_user_scope_renders_owned_characters(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify user scope renders the target user's characters across campaigns."""
        # Given two characters owned by the target user and one owned by someone else
        owned_a = CharacterFactory.build(name="Owned A", type="PLAYER", user_player_id="u-target")
        owned_b = CharacterFactory.build(name="Owned B", type="NPC", user_player_id="u-target")
        not_owned = CharacterFactory.build(
            name="Not Owned", type="PLAYER", user_player_id="u-other"
        )
        ctx, _ = _character_context([owned_a, owned_b, not_owned])
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the user-scoped card
        response = client.get("/cards/character-list?user_id=u-target")
        body = response.get_data(as_text=True)

        # Then only that user's characters render
        assert response.status_code == 200
        assert "Owned A" in body
        assert "Owned B" in body
        assert "Not Owned" not in body

    def test_link_user_profile_skips_link_for_ownerless_npc(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify an NPC with no owner renders without a profile link instead of crashing."""
        # Given a campaign whose roster includes an NPC with no owning player
        campaign = CampaignFactory.build(name="Test Campaign")
        npc = CharacterFactory.build(
            name="Ownerless Npc", type="NPC", user_player_id=None, campaign_id=campaign.id
        )
        ctx, _ = _character_context([npc], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the card with profile links enabled (the "Other Players" box)
        response = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=all&link_user_profile=true"
        )
        body = response.get_data(as_text=True)

        # Then the NPC renders without a profile link, and url_for(user_id=None) does not 500
        assert response.status_code == 200
        assert "Ownerless Npc" in body
        assert "/profile/None" not in body

    def test_user_scope_returns_all_context_characters_without_type_filtering(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify user-scoped card returns every owned character verbatim from the context.

        The API already scopes the roster by role via the on-behalf-of header, so
        the card no longer applies client-side type filtering.
        """
        # Given a target user owning a player and a storyteller character
        player_char = CharacterFactory.build(
            name="Owned Player", type="PLAYER", user_player_id="u-target"
        )
        story_char = CharacterFactory.build(
            name="Owned Storyteller", type="STORYTELLER", user_player_id="u-target"
        )
        ctx, _ = _character_context([player_char, story_char], user_role="PLAYER")
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When the user-scoped card is requested
        body = client.get("/cards/character-list?user_id=u-target").get_data(as_text=True)

        # Then both characters render because the API already filtered the bucket
        assert "Owned Player" in body
        assert "Owned Storyteller" in body

    def test_type_filter_narrows_results(self, client: FlaskClient, mocker: MockerFixture) -> None:
        """Verify the type filter param narrows the rendered body."""
        # Given a campaign with one player and one NPC character
        campaign = CampaignFactory.build(name="Test Campaign")
        player = CharacterFactory.build(
            name="Player One", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        npc = CharacterFactory.build(
            name="Npc One", type="NPC", user_player_id="test-user-id", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([player, npc], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When requesting the body filtered to NPC
        response = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=all&type=NPC&body_only=true"
        )
        body = response.get_data(as_text=True)

        # Then only the NPC renders
        assert "Npc One" in body
        assert "Player One" not in body

    def test_type_filter_shown_only_when_multiple_types_present(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify the type filter appears only when the roster has more than one type."""
        # Given a campaign with both PLAYER and NPC characters
        campaign = CampaignFactory.build(name="Mixed Campaign")
        player = CharacterFactory.build(
            name="Player One", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        npc = CharacterFactory.build(
            name="Npc One", type="NPC", user_player_id="test-user-id", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([player, npc], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When rendering the full card with mixed types
        mixed = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=all&show_type=true"
        ).get_data(as_text=True)

        # Then the type select is present
        assert 'name="type"' in mixed
        assert "All types" in mixed

    def test_type_filter_hidden_when_single_type(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify a single-type roster renders no type filter control."""
        # Given a campaign whose characters are all the same type and owner
        campaign = CampaignFactory.build(name="Single Type Campaign")
        one = CharacterFactory.build(
            name="Player One", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        two = CharacterFactory.build(
            name="Player Two", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([one, two], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When rendering the full card
        body = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=mine&show_type=true"
        ).get_data(as_text=True)

        # Then no type filter is rendered
        assert "All types" not in body

    def test_show_filters_false_suppresses_all_filters(
        self, client: FlaskClient, mocker: MockerFixture
    ) -> None:
        """Verify show_filters=false hides the filter row even with multiple values present."""
        # Given a campaign with mixed types and owners (which would normally show filters)
        campaign = CampaignFactory.build(name="Mixed Campaign")
        player = CharacterFactory.build(
            name="Player One", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        npc = CharacterFactory.build(
            name="Npc One", type="NPC", user_player_id="other-user", campaign_id=campaign.id
        )
        ctx, campaign = _character_context([player, npc], campaign=campaign)
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

        # When rendering with filters disabled
        body = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=all&show_type=true&show_filters=false"
        ).get_data(as_text=True)

        # Then no filter controls render, but the roster still does
        assert "All types" not in body
        assert 'name="type"' not in body
        assert "Player One" in body
        assert "Npc One" in body
