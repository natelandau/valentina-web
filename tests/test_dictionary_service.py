"""Tests for dictionary service functions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models import DictionaryTermCreate, DictionaryTermUpdate

from vweb.routes.dictionary.services import (
    create_term,
    delete_term,
    parse_synonyms,
    update_term,
    validate_term,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestParseSynonyms:
    """Tests for parse_synonyms."""

    def test_splits_comma_separated_values(self) -> None:
        """Verify comma-separated input is split into a list."""
        assert parse_synonyms("vamp, leech, nosferatu") == ["vamp", "leech", "nosferatu"]

    def test_strips_whitespace(self) -> None:
        """Verify leading and trailing whitespace is stripped from each synonym."""
        assert parse_synonyms("  vamp ,  leech  ") == ["vamp", "leech"]

    def test_filters_empty_strings(self) -> None:
        """Verify empty entries from trailing commas are removed."""
        assert parse_synonyms("vamp,,leech,") == ["vamp", "leech"]

    def test_empty_input(self) -> None:
        """Verify empty string returns empty list."""
        assert parse_synonyms("") == []

    def test_whitespace_only(self) -> None:
        """Verify whitespace-only input returns empty list."""
        assert parse_synonyms("   ") == []


class TestValidateTerm:
    """Tests for validate_term."""

    def test_valid_term(self) -> None:
        """Verify valid form data returns no errors."""
        form_data = {"term": "Auspex", "definition": "A discipline", "link": "", "synonyms": ""}
        assert validate_term(form_data) == []

    def test_missing_term(self) -> None:
        """Verify missing term name returns error."""
        errors = validate_term({"term": "", "definition": "", "link": "", "synonyms": ""})
        assert any("required" in e.lower() for e in errors)

    def test_term_too_short(self) -> None:
        """Verify term under 3 characters returns error."""
        errors = validate_term({"term": "ab", "definition": "", "link": "", "synonyms": ""})
        assert any("3" in e for e in errors)

    def test_term_too_long(self) -> None:
        """Verify term over 50 characters returns error."""
        errors = validate_term({"term": "a" * 51, "definition": "", "link": "", "synonyms": ""})
        assert any("50" in e for e in errors)

    def test_invalid_link(self) -> None:
        """Verify non-URL link returns error."""
        errors = validate_term(
            {"term": "Auspex", "definition": "", "link": "not-a-url", "synonyms": ""}
        )
        assert any("url" in e.lower() for e in errors)

    def test_valid_link(self) -> None:
        """Verify valid URL link returns no errors."""
        errors = validate_term(
            {"term": "Auspex", "definition": "", "link": "https://example.com", "synonyms": ""}
        )
        assert errors == []

    def test_empty_link_is_valid(self) -> None:
        """Verify empty link field is accepted."""
        errors = validate_term({"term": "Auspex", "definition": "", "link": "", "synonyms": ""})
        assert errors == []


@pytest.fixture
def mock_svc(mocker: MockerFixture) -> MagicMock:
    """Patch sync_dictionary_service and return the mock service instance."""
    svc = MagicMock()
    mocker.patch("vweb.routes.dictionary.services.sync_dictionary_service", return_value=svc)
    return svc


class TestCreateTerm:
    """Tests for create_term."""

    def test_creates_term_via_api(self, app, mock_svc: MagicMock) -> None:
        """Verify create_term calls the API with parsed form data."""
        form_data = {
            "term": "Auspex",
            "definition": "A vampiric discipline.",
            "link": "https://example.com",
            "synonyms": "sight, vision",
        }
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            create_term(form_data)

        mock_svc.create.assert_called_once()
        call_arg = mock_svc.create.call_args[1]["request"]
        assert isinstance(call_arg, DictionaryTermCreate)
        assert call_arg.term == "Auspex"
        assert call_arg.definition == "A vampiric discipline."
        assert call_arg.link == "https://example.com"
        assert call_arg.synonyms == ["sight", "vision"]

    def test_empty_optional_fields(self, app, mock_svc: MagicMock) -> None:
        """Verify empty optional fields are passed as None."""
        form_data = {"term": "Auspex", "definition": "", "link": "", "synonyms": ""}
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            create_term(form_data)

        call_arg = mock_svc.create.call_args[1]["request"]
        assert call_arg.definition is None
        assert call_arg.link is None
        assert call_arg.synonyms == []


class TestUpdateTerm:
    """Tests for update_term."""

    def test_updates_term_via_api(self, app, mock_svc: MagicMock) -> None:
        """Verify update_term calls the API with parsed form data."""
        form_data = {"term": "Auspex", "definition": "Updated.", "link": "", "synonyms": "a, b"}
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            update_term("term-1", form_data)

        mock_svc.update.assert_called_once()
        args = mock_svc.update.call_args
        assert args[0][0] == "term-1"
        call_arg = args[1]["request"]
        assert isinstance(call_arg, DictionaryTermUpdate)
        assert call_arg.term == "Auspex"
        assert call_arg.synonyms == ["a", "b"]


class TestDeleteTerm:
    """Tests for delete_term."""

    def test_deletes_term_via_api(self, app, mock_svc: MagicMock) -> None:
        """Verify delete_term calls the API."""
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            delete_term("term-1")

        mock_svc.delete.assert_called_once_with("term-1")
