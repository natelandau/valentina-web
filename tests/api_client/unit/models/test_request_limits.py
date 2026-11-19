"""Tests for request field rules that mirror the API's validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vweb.api_client.models import (
    DictionaryTermCreate,
    TraitCreate,
)
from vweb.api_client.testing import CharacterFactory


@pytest.mark.parametrize(
    ("build", "accepted"),
    [
        (lambda: DictionaryTermCreate(term="Auspex", link="https://example.com/a"), True),
        (lambda: DictionaryTermCreate(term="Auspex", link="HTTP://example.com/a"), True),
        (lambda: DictionaryTermCreate(term="Auspex", link="javascript:alert(1)"), False),
        (lambda: DictionaryTermCreate(term="Auspex", link="https://example.com/a\n"), False),
        (lambda: DictionaryTermCreate(term="Auspex", link="https://example.com/a b"), False),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["Aura"]), True),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["  "]), False),
    ],
)
def test_request_patterns_match_the_api(build, accepted) -> None:
    """Verify links must be plain http(s) URLs and synonyms must not be blank."""
    if accepted:
        build()
    else:
        with pytest.raises(ValidationError):
            build()


def test_trait_create_rejects_min_above_max() -> None:
    """Verify a custom trait whose min_value exceeds max_value fails before the request."""
    with pytest.raises(ValidationError, match="must not exceed max_value"):
        TraitCreate(name="Odd", category_id="cat", currency="NO_COST", min_value=4, max_value=3)


def test_character_response_accepts_short_optional_text() -> None:
    """Verify a character response keeps short text the API accepts from any client."""
    character = CharacterFactory.build(name_nick="Al", demeanor="Ox", nature="Ox", biography="Hi")

    assert character.name_nick == "Al"
