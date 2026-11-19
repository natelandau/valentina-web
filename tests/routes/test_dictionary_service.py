"""Tests for dictionary service functions."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import Routes
from vweb.routes.dictionary.services import (
    TERM_MAX_LENGTH,
    TERM_MIN_LENGTH,
    create_term,
    parse_synonyms,
    update_term,
    validate_term,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("vamp, leech, nosferatu", ["vamp", "leech", "nosferatu"]),
        ("  vamp ,  leech  ", ["vamp", "leech"]),
        ("vamp,,leech,", ["vamp", "leech"]),
        ("", []),
        ("   ", []),
    ],
    ids=["split", "strip", "drop-empty", "empty", "whitespace-only"],
)
def test_parse_synonyms(raw, expected) -> None:
    """Verify synonyms are split on commas, trimmed, and empty entries dropped."""
    assert parse_synonyms(raw) == expected


@pytest.mark.parametrize(
    ("form", "invalid_fields"),
    [
        ({"term": "Auspex", "definition": "A discipline"}, set()),
        ({"term": "Auspex", "link": "https://example.com"}, set()),
        ({"term": "", "definition": "A discipline"}, {"term"}),
        ({"term": "a" * (TERM_MIN_LENGTH - 1), "definition": "A discipline"}, {"term"}),
        ({"term": "a" * (TERM_MAX_LENGTH + 1), "definition": "A discipline"}, {"term"}),
        ({"term": "Auspex", "definition": " ", "link": ""}, {"definition"}),
        ({"term": "Auspex", "link": "not-a-url"}, {"link"}),
        ({"term": "Auspex", "link": "javascript://x/%0aalert(1)"}, {"link"}),
        ({"term": "Auspex", "link": "data://x/text"}, {"link"}),
        ({"term": "Auspex", "link": "https://a.example/ x-data x-init=alert(1)"}, {"link"}),
        ({"term": "Auspex", "link": "https://a.example/\tpath"}, {"link"}),
    ],
    ids=[
        "definition-only",
        "link-only",
        "missing-term",
        "term-too-short",
        "term-too-long",
        "no-definition-or-link",
        "not-a-url",
        "javascript-scheme",
        "data-scheme",
        "embedded-space",
        "embedded-tab",
    ],
)
def test_validate_term(form, invalid_fields) -> None:
    """Verify the term length, an http(s) link, and a definition-or-link rule are enforced."""
    assert set(validate_term(form)) == invalid_fields


@pytest.mark.parametrize(
    ("form", "expected_body"),
    [
        (
            {
                "term": " Auspex ",
                "definition": "A vampiric discipline.",
                "link": "https://example.com",
                "synonyms": "sight, vision",
            },
            {
                "term": "Auspex",
                "definition": "A vampiric discipline.",
                "link": "https://example.com",
                "synonyms": ["sight", "vision"],
            },
        ),
        (
            {"term": "Auspex", "definition": "", "link": "", "synonyms": ""},
            {"term": "Auspex", "synonyms": []},
        ),
    ],
    ids=["all-fields", "optional-fields-omitted"],
)
def test_create_term_sends_parsed_form(app, fake_vclient, form, expected_body) -> None:
    """Verify the parsed form reaches the API, leaving out empty optional fields."""
    with app.test_request_context("/"):
        seed_session()
        create_term(form)

    fake_vclient.assert_called(
        Routes.DICTIONARY_CREATE,
        params={"company_id": "test-company-id"},
        json=expected_body,
        times=1,
    )


@pytest.mark.parametrize(
    ("form", "expected_body"),
    [
        (
            {"term": "Auspex", "definition": "Updated.", "link": "", "synonyms": "a, b"},
            {"term": "Auspex", "definition": "Updated.", "link": None, "synonyms": ["a", "b"]},
        ),
        (
            {"term": "Auspex", "definition": "  ", "link": "", "synonyms": ""},
            {"term": "Auspex", "definition": None, "link": None, "synonyms": []},
        ),
    ],
    ids=["blank-link-clears", "blank-definition-clears"],
)
def test_update_term_sends_nulls_to_clear_fields(app, fake_vclient, form, expected_body) -> None:
    """Verify an update sends null for blanked fields so the API clears the stored values."""
    with app.test_request_context("/"):
        seed_session()
        update_term("term-1", form)

    fake_vclient.assert_called(
        Routes.DICTIONARY_UPDATE,
        params={"company_id": "test-company-id", "term_id": "term-1"},
        json=expected_body,
        times=1,
    )
