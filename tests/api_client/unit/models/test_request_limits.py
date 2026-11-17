"""Tests for the request field limits that mirror the API's validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vweb.api_client.models import (
    CampaignCreate,
    CharacterUpdate,
    CompanySettingsUpdate,
    DictionaryTermCreate,
    HealthStateSet,
    NoteCreate,
    TraitCreate,
    VampireAttributesCreate,
)
from vweb.api_client.testing import CharacterFactory


@pytest.mark.parametrize(
    ("build", "accepted"),
    [
        (lambda: CampaignCreate(name="Camp", description="a" * 20_000), True),
        (lambda: CampaignCreate(name="Camp", description="a" * 20_001), False),
        (lambda: NoteCreate(title="Note", content="a" * 20_001), False),
        (lambda: DictionaryTermCreate(term="Auspex", link="https://example.com/a"), True),
        (lambda: DictionaryTermCreate(term="Auspex", link="javascript:alert(1)"), False),
        (lambda: DictionaryTermCreate(term="Auspex", link="https://example.com/a\n"), False),
        (lambda: DictionaryTermCreate(term="Auspex", link="https://x.co/" + "a" * 2048), False),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["a"] * 50), True),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["a"] * 51), False),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["  "]), False),
        (lambda: DictionaryTermCreate(term="Auspex", synonyms=["a" * 51]), False),
        (lambda: VampireAttributesCreate(clan_id="c1", generation=16), True),
        (lambda: VampireAttributesCreate(clan_id="c1", generation=0), False),
        (lambda: VampireAttributesCreate(clan_id="c1", generation=17), False),
        (lambda: HealthStateSet(extra_levels=20), True),
        (lambda: HealthStateSet(extra_levels=21), False),
        (lambda: CompanySettingsUpdate(custom_flaw_xp_cost=100), True),
        (lambda: CompanySettingsUpdate(custom_flaw_xp_cost=101), False),
        (lambda: CompanySettingsUpdate(custom_flaw_xp_cost=-1), False),
        (lambda: CharacterUpdate(name_first="a" * 51), False),
        (lambda: CharacterUpdate(biography="a" * 20_001), False),
        (lambda: TraitCreate(name="a" * 51, category_id="cat", currency="NO_COST"), False),
    ],
)
def test_request_limits_match_the_api(build, accepted) -> None:
    """Verify request models accept values in the API's range and reject the rest."""
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
