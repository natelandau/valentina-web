"""Tests for the shared audit log helpers in vweb.routes.fragments_shared_cards.audit_log."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from flask import session

from vweb.api_client.testing import (
    AuditLogFactory,
    CampaignBookFactory,
    CampaignChapterFactory,
    CharacterFactory,
    Routes,
)
from vweb.routes.fragments_shared_cards.audit_log import (
    format_change_value,
    get_audit_log_page,
    resolve_acting_user,
    resolve_entities,
    split_changes,
)

if TYPE_CHECKING:
    from flask import Flask

    from vweb.api_client.models.audit_logs import AuditLog
    from vweb.lib.cache.global_context import GlobalContext


class TestFormatChangeValue:
    """Tests for format_change_value."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "—"),
            (True, "Yes"),
            (False, "No"),
            ("plain", "plain"),
            (0, "0"),
            (42, "42"),
            (3.14, "3.14"),
        ],
    )
    def test_scalars_render_readable_text(self, value: object, expected: str) -> None:
        """Verify scalar values render as readable text."""
        assert expected in str(format_change_value(value))

    @pytest.mark.parametrize(
        "value",
        ["<script>alert(1)</script>", ["<script>alert(1)</script>"]],
        ids=["string", "list"],
    )
    def test_html_is_escaped(self, value: object) -> None:
        """Verify HTML inside a value is escaped, whether scalar or nested in a collection."""
        html = str(format_change_value(value))

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.parametrize(
        ("value", "expected_parts"),
        [
            (["a", "b", "c"], ['"a"', '"b"', '"c"']),
            ({"name": "Alice", "age": 30}, ['"name"', '"Alice"', '"age"', "30"]),
            ([datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)], ["2026-04-23"]),
        ],
        ids=["list", "dict", "datetime-in-list"],
    )
    def test_collections_render_as_preformatted_json(
        self, value: object, expected_parts: list[str]
    ) -> None:
        """Verify lists and dicts render as JSON in a preformatted block, stringifying datetimes."""
        html = str(format_change_value(value))

        assert html.startswith("<pre")
        for part in expected_parts:
            assert part in html


class TestSplitChanges:
    """Tests for split_changes."""

    @pytest.mark.parametrize("changes", [None, {}])
    def test_empty_input_returns_empty_lists(self, changes: dict | None) -> None:
        """Verify missing or empty changes yield no diffs and no other entries."""
        assert split_changes(changes) == ([], [])

    def test_sorts_canonical_and_off_shape_entries(self) -> None:
        """Verify {old, new} entries become diffs and everything else is kept as other entries."""
        # Given canonical entries (one with an extra key) and off-shape entries
        changes = {
            "name": {"old": "Alice", "new": "Bob"},
            "role": {"old": "PLAYER", "new": "ADMIN", "by": "user-1"},
            "meta": {"version": 3, "hash": "abc"},
            "deleted_by": "user-1",
        }

        # When splitting
        diffs, others = split_changes(changes)

        # Then canonical entries are diffs with their values, and nothing is dropped
        assert [d.field for d in diffs] == ["name", "role"]
        assert "Alice" in str(diffs[0].old)
        assert "Bob" in str(diffs[0].new)
        assert {e.key for e in others} == {"meta", "deleted_by"}
        assert "user-1" in str(next(e.value for e in others if e.key == "deleted_by"))


class TestResolveActingUser:
    """Tests for resolve_acting_user."""

    def test_empty_id_returns_empty_strings(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify an empty acting_user_id returns no name and no URL."""
        with app.test_request_context():
            assert resolve_acting_user("", mock_global_context) == ("", "")

    def test_known_user_returns_username_and_url(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify a known acting_user_id returns (username, profile_url)."""
        user = mock_global_context.users[0]

        with app.test_request_context():
            name, url = resolve_acting_user(user.id, mock_global_context)

        assert name == user.username
        assert user.id in url

    def test_unresolvable_id_returns_deleted_sentinel(
        self, app: Flask, mock_global_context: GlobalContext
    ) -> None:
        """Verify an unknown acting_user_id falls back to ('[deleted]', '')."""
        with app.test_request_context():
            assert resolve_acting_user("unknown-user", mock_global_context) == ("[deleted]", "")


class TestResolveEntities:
    """Tests for resolve_entities."""

    @pytest.fixture
    def entity_context(
        self, mock_global_context: GlobalContext, mocker
    ) -> dict[str, tuple[str, str]]:
        """Put one known user, campaign, character, book, and chapter where the resolver looks."""
        character = CharacterFactory.build(id="char-known", name="Known Character")
        mock_global_context.characters = [character]
        book = CampaignBookFactory.build(id="book-known", name="Known Book")
        chapter = CampaignChapterFactory.build(id="chapter-known", name="Known Chapter")
        mocker.patch("vweb.lib.cache.campaign_content.books", return_value=[book])
        mocker.patch("vweb.lib.cache.campaign_content.chapters", return_value=[chapter])
        user = mock_global_context.users[0]
        campaign = mock_global_context.campaigns[0]
        return {
            "User": (user.id, user.username),
            "Campaign": (campaign.id, campaign.name),
            "Character": (character.id, character.name),
            "Book": (book.id, book.name),
            "Chapter": (chapter.id, chapter.name),
        }

    @staticmethod
    def _log_for(
        label: str, entity_id: str, campaign_id: str | None, book_id: str | None
    ) -> AuditLog:
        """Build an audit log that carries only the entity under test plus its scoping ids."""
        ids: dict[str, str | None] = {
            "user_id": None,
            "campaign_id": campaign_id,
            "character_id": None,
            "book_id": book_id,
            "chapter_id": None,
        }
        ids[f"{label.lower()}_id"] = entity_id
        return AuditLogFactory.build(**ids)  # ty:ignore[invalid-argument-type]

    @pytest.mark.parametrize("label", ["User", "Campaign", "Character", "Book", "Chapter"])
    def test_known_entity_resolves_to_name_and_url(
        self,
        app: Flask,
        mock_global_context: GlobalContext,
        entity_context: dict[str, tuple[str, str]],
        label: str,
    ) -> None:
        """Verify each entity type found in context or cache resolves to its name and a link."""
        # Given a log pointing at a known entity
        entity_id, expected_name = entity_context[label]
        campaign_id = mock_global_context.campaigns[0].id
        log = self._log_for(label, entity_id, campaign_id, "book-known")

        # When resolving
        with app.test_request_context():
            result = {
                lbl: (name, url) for lbl, name, url in resolve_entities(log, mock_global_context)
            }

        # Then the entity shows its name with a link to it
        name, url = result[label]
        assert name == expected_name
        assert url is not None
        assert entity_id in url

    @pytest.mark.parametrize(
        ("label", "campaign_id", "book_id"),
        [
            ("User", None, None),
            ("Campaign", None, None),
            ("Character", None, None),
            ("Book", "campaign-1", None),
            ("Book", None, None),
            ("Chapter", "campaign-1", "book-known"),
            ("Chapter", "campaign-1", None),
        ],
        ids=[
            "user-unknown",
            "campaign-unknown",
            "character-unknown",
            "book-unknown",
            "book-without-campaign",
            "chapter-unknown",
            "chapter-without-book",
        ],
    )
    def test_unresolvable_entity_shows_deleted_without_link(
        self,
        app: Flask,
        mock_global_context: GlobalContext,
        entity_context: dict[str, tuple[str, str]],
        label: str,
        campaign_id: str | None,
        book_id: str | None,
    ) -> None:
        """Verify an entity missing from context, cache, or its scoping ids shows as deleted."""
        # Given a log pointing at an entity that cannot be found
        log = self._log_for(label, "missing-id", campaign_id, book_id)

        # When resolving
        with app.test_request_context():
            result = {
                lbl: (name, url) for lbl, name, url in resolve_entities(log, mock_global_context)
            }

        # Then the entity is listed as deleted with no link
        assert result[label] == ("[deleted]", None)

    @pytest.mark.parametrize(
        ("skip", "expected_labels"),
        [
            (None, ["User", "Campaign", "Character"]),
            ({"User"}, ["Campaign", "Character"]),
            ({"User", "Character"}, ["Campaign"]),
        ],
        ids=["no-skip", "skip-one", "skip-many"],
    )
    def test_skip_ids_omits_matching_entities(
        self,
        app: Flask,
        mock_global_context: GlobalContext,
        entity_context: dict[str, tuple[str, str]],
        skip: set[str] | None,
        expected_labels: list[str],
    ) -> None:
        """Verify entities whose ids are in skip_ids are left out of the result."""
        # Given a log with a user, campaign, and character
        log = AuditLogFactory.build(
            user_id=entity_context["User"][0],
            campaign_id=entity_context["Campaign"][0],
            character_id=entity_context["Character"][0],
            book_id=None,
            chapter_id=None,
        )
        skip_ids = {entity_context[label][0] for label in skip} if skip else None

        # When resolving with skip_ids
        with app.test_request_context():
            result = resolve_entities(log, mock_global_context, skip_ids=skip_ids)

        # Then only the entities not skipped remain
        assert [label for label, _, _ in result] == expected_labels


class TestGetAuditLogPage:
    """Tests for the canonical API wrapper."""

    def test_all_filters_forwarded(self, app: Flask, fake_vclient) -> None:
        """Verify all non-empty filters are forwarded with dates parsed."""
        with app.test_request_context():
            session["company_id"] = "test-company-id"

            # When calling with every filter populated
            get_audit_log_page(
                limit=25,
                offset=50,
                acting_user_id="u-1",
                user_id="u-2",
                campaign_id="c-1",
                book_id="b-1",
                chapter_id="ch-1",
                character_id="char-1",
                entity_type="CAMPAIGN",
                operation="UPDATE",
                date_from="2026-01-01",
                date_to="2026-01-31",
            )

        # Then the API receives every filter, with dates as ISO datetimes
        (request,) = fake_vclient.assert_called(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            params={"company_id": "test-company-id"},
            times=1,
        )
        assert request.query == {
            "limit": "25",
            "offset": "50",
            "acting_user_id": "u-1",
            "user_id": "u-2",
            "campaign_id": "c-1",
            "book_id": "b-1",
            "chapter_id": "ch-1",
            "character_id": "char-1",
            "entity_type": "CAMPAIGN",
            "operation": "UPDATE",
            "date_from": "2026-01-01T00:00:00",
            "date_to": "2026-01-31T00:00:00",
        }

    def test_empty_filters_are_left_out(self, app: Flask, fake_vclient) -> None:
        """Verify empty-string filters are left out of the API call."""
        with app.test_request_context():
            session["company_id"] = "test-company-id"

            get_audit_log_page(limit=10, offset=0)

        (request,) = fake_vclient.assert_called(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            params={"company_id": "test-company-id"},
            times=1,
        )
        assert request.query == {"limit": "10", "offset": "0"}

    def test_identical_queries_hit_api_once(self, app: Flask, fake_vclient) -> None:
        """Verify repeated identical audit-log queries are served from the cache."""
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            from vweb.extensions import cache

            cache.clear()
            fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

            get_audit_log_page(limit=10, offset=0, campaign_id="camp-1")
            get_audit_log_page(limit=10, offset=0, campaign_id="camp-1")

        fake_vclient.assert_called(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            params={"company_id": "comp-1"},
            query={"campaign_id": "camp-1"},
            times=1,
        )

    def test_distinct_filters_are_cached_separately(self, app: Flask, fake_vclient) -> None:
        """Verify differing filter args miss the cache and hit the API each time."""
        with app.test_request_context("/"):
            session["company_id"] = "comp-1"
            from vweb.extensions import cache

            cache.clear()
            fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

            get_audit_log_page(limit=10, offset=0)
            get_audit_log_page(limit=10, offset=10)

        fake_vclient.assert_called(Routes.COMPANIES_AUDIT_LOGS_LIST, query={"offset": 0}, times=1)
        fake_vclient.assert_called(Routes.COMPANIES_AUDIT_LOGS_LIST, query={"offset": 10}, times=1)
