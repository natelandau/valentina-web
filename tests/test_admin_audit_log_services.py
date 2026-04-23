"""Tests for admin audit log service layer."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from vclient.testing import (
    AuditLogFactory,
    CampaignBookFactory,
    CharacterFactory,
)

from vweb.lib.audit_log import get_audit_log_page, resolve_entities

if TYPE_CHECKING:
    from flask import Flask

    from vweb.lib.global_context import GlobalContext


class TestGetAuditLogPage:
    """Tests for get_audit_log_page service function."""

    def test_filters_forwarded(self, app: Flask, mocker) -> None:
        """Verify all non-empty filters are forwarded to the API with datetime parsing."""
        # Given a mocked companies service
        mock_svc = MagicMock()
        mock_svc.get_audit_log_page.return_value = MagicMock()
        mocker.patch(
            "vweb.lib.audit_log.sync_companies_service",
            return_value=mock_svc,
        )

        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"

            # When calling with all filters populated
            get_audit_log_page(
                limit=20,
                offset=10,
                entity_type="USER",
                operation="CREATE",
                acting_user_id="user-123",
                date_from="2026-01-01",
                date_to="2026-01-31",
            )

        # Then the API receives parsed kwargs including datetime objects and None for unused filters
        mock_svc.get_audit_log_page.assert_called_once_with(
            "test-company-id",
            limit=20,
            offset=10,
            acting_user_id="user-123",
            user_id=None,
            campaign_id=None,
            book_id=None,
            chapter_id=None,
            character_id=None,
            entity_type="USER",
            operation="CREATE",
            date_from=datetime.fromisoformat("2026-01-01"),
            date_to=datetime.fromisoformat("2026-01-31"),
        )

    def test_empty_filters_omitted(self, app: Flask, mocker) -> None:
        """Verify empty-string filter values are not passed to the API."""
        # Given a mocked companies service
        mock_svc = MagicMock()
        mock_svc.get_audit_log_page.return_value = MagicMock()
        mocker.patch(
            "vweb.lib.audit_log.sync_companies_service",
            return_value=mock_svc,
        )

        with app.test_request_context():
            from flask import session

            session["company_id"] = "test-company-id"

            # When calling with all filters as empty strings
            get_audit_log_page(
                limit=20,
                offset=0,
                entity_type="",
                operation="",
                acting_user_id="",
                date_from="",
                date_to="",
            )

        # Then all filters are passed as None (empty strings coerced to None)
        mock_svc.get_audit_log_page.assert_called_once_with(
            "test-company-id",
            limit=20,
            offset=0,
            acting_user_id=None,
            user_id=None,
            campaign_id=None,
            book_id=None,
            chapter_id=None,
            character_id=None,
            entity_type=None,
            operation=None,
            date_from=None,
            date_to=None,
        )


class TestResolveEntities:
    """Tests for resolve_entities helper function."""

    def test_resolve_known_user(self, app: Flask, mock_global_context: GlobalContext) -> None:
        """Verify a known user_id resolves to username and profile URL."""
        # Given an audit log with a user_id matching a context user
        user = mock_global_context.users[0]
        log = AuditLogFactory.build(
            user_id=user.id,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then the user is resolved with a profile URL
        assert len(result) == 1
        label, name, url = result[0]
        assert label == "User"
        assert name == user.username
        assert url is not None
        assert user.id in url

    def test_resolve_known_campaign(self, app: Flask, mock_global_context: GlobalContext) -> None:
        """Verify a known campaign_id resolves to campaign name and URL."""
        # Given an audit log with a campaign_id matching a context campaign
        campaign = mock_global_context.campaigns[0]
        log = AuditLogFactory.build(
            user_id=None,
            campaign_id=campaign.id,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then the campaign is resolved with a URL
        assert len(result) == 1
        label, name, url = result[0]
        assert label == "Campaign"
        assert name == campaign.name
        assert url is not None
        assert campaign.id in url

    def test_unresolvable_id_falls_back(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify an unknown user_id falls back to raw ID with None URL."""
        # Given an audit log with a user_id not in context
        log = AuditLogFactory.build(
            user_id="unknown-user-id",
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then the raw ID is returned with no URL
        assert len(result) == 1
        label, name, url = result[0]
        assert label == "User"
        assert name == "unknown-user-id"
        assert url is None

    def test_multiple_entity_ids_resolved(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify multiple entity IDs are all resolved in order."""
        # Given a context with a character added
        user = mock_global_context.users[0]
        campaign = mock_global_context.campaigns[0]
        character = CharacterFactory.build()
        mock_global_context.characters = [character]

        log = AuditLogFactory.build(
            user_id=user.id,
            campaign_id=campaign.id,
            character_id=character.id,
            book_id=None,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then all three are resolved in order
        assert len(result) == 3
        assert result[0][0] == "User"
        assert result[0][1] == user.username
        assert result[1][0] == "Campaign"
        assert result[1][1] == campaign.name
        assert result[2][0] == "Character"
        assert result[2][1] == character.name

    def test_no_entity_ids_returns_empty(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify an audit log with no entity IDs returns an empty list."""
        # Given an audit log with no entity IDs set
        log = AuditLogFactory.build(
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then the result is empty
        assert result == []

    def test_resolve_book_with_campaign(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify a book_id resolves to name and URL when campaign_id is also present."""
        # Given a context with a book in a campaign
        campaign = mock_global_context.campaigns[0]
        book = CampaignBookFactory.build(campaign_id=campaign.id)
        mock_global_context.books_by_campaign[campaign.id] = [book]

        log = AuditLogFactory.build(
            user_id=None,
            campaign_id=campaign.id,
            character_id=None,
            book_id=book.id,
            chapter_id=None,
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then campaign and book are both resolved
        assert len(result) == 2
        assert result[0][0] == "Campaign"
        assert result[1][0] == "Book"
        assert result[1][1] == book.name
        assert result[1][2] is not None
        assert book.id in result[1][2]

    def test_chapter_id_shows_raw_id(self, app: Flask, mock_global_context: GlobalContext) -> None:
        """Verify chapter_id is shown as raw ID with no URL."""
        # Given an audit log with a chapter_id
        log = AuditLogFactory.build(
            user_id=None,
            campaign_id=None,
            character_id=None,
            book_id=None,
            chapter_id="chapter-abc",
        )

        with app.test_request_context():
            # When resolving entities
            result = resolve_entities(log, mock_global_context)

        # Then chapter shows raw ID with no URL
        assert len(result) == 1
        label, name, url = result[0]
        assert label == "Chapter"
        assert name == "chapter-abc"
        assert url is None
