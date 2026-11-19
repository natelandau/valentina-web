"""Unit tests for character trait, tracker, and health models."""

from collections.abc import Callable

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.models import Character
from vweb.api_client.models.character_trait import (
    CharacterTrait,
    CounterTracker,
    Health,
    HealthStateSet,
    StainsTracker,
    TrackerStateSet,
)


def _character_trait_data(**overrides: object) -> dict:
    """Return a minimal valid CharacterTrait payload, without tracker fields."""
    data: dict = {
        "id": "ct123",
        "character_id": "char123",
        "value": 3,
        "trait": {
            "id": "trait123",
            "name": "Willpower",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "category_id": "cat123",
            "sheet_section_id": "section123",
        },
    }
    data.update(overrides)
    return data


def _character_data() -> dict:
    """Return a minimal valid Character payload, without health."""
    return {
        "id": "char123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "character_class": "VAMPIRE",
        "game_version": "V5",
        "name_first": "John",
        "name_last": "Doe",
        "name": "Johnny",
        "name_full": "John Doe",
        "company_id": "company123",
        "campaign_id": "campaign123",
    }


@pytest.mark.parametrize(
    ("tracker", "expected_type"),
    [
        ({"type": "COUNTER", "size": 5, "current": 3}, CounterTracker),
        ({"type": "STAINS", "humanity": 7, "stain_capacity": 3, "stains": 4}, StainsTracker),
    ],
)
def test_tracker_parses_as_the_variant_named_by_type(
    tracker: dict, expected_type: type[BaseModel]
) -> None:
    """Verify a trait's tracker parses as the model its ``type`` names."""
    ct = CharacterTrait.model_validate(_character_trait_data(tracker=tracker))

    assert isinstance(ct.tracker, expected_type)


@pytest.mark.parametrize(
    "tracker",
    [
        pytest.param(
            {"type": "DAMAGE", "size": 5, "superficial": 1, "aggravated": 0},
            id="damage-no-longer-a-trait-tracker",
        ),
        pytest.param({"type": "BOGUS", "size": 1, "current": 1}, id="unknown-type"),
    ],
)
def test_tracker_with_unknown_type_is_rejected(tracker: dict) -> None:
    """Verify a tracker type outside the known variants fails validation."""
    with pytest.raises(PydanticValidationError):
        CharacterTrait.model_validate(_character_trait_data(tracker=tracker))


@pytest.mark.parametrize(
    ("parse", "read"),
    [
        pytest.param(
            lambda: CharacterTrait.model_validate(_character_trait_data()),
            lambda ct: ct.tracker,
            id="trait-without-tracker",
        ),
        pytest.param(
            lambda: Character.model_validate(_character_data()),
            lambda character: character.health,
            id="character-without-health",
        ),
        pytest.param(
            lambda: Health.model_validate(
                {"type": "DAMAGE", "size": 5, "superficial": 1, "aggravated": 0}
            ),
            lambda health: health.damage,
            id="health-with-typed-marks-instead-of-damage",
        ),
        pytest.param(
            lambda: Health.model_validate(
                {"type": "DAMAGE", "size": 7, "levels": [{"name": "Bruised", "mark": "LETHAL"}]}
            ),
            lambda health: health.levels[0].marked,
            id="v4-level-without-marked",
        ),
    ],
)
def test_older_api_payloads_still_parse(
    parse: Callable[[], BaseModel], read: Callable[[BaseModel], object]
) -> None:
    """Verify payloads from API versions without the newer fields parse with those fields None."""
    assert read(parse()) is None


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (TrackerStateSet, "superficial"),
        (TrackerStateSet, "aggravated"),
        (TrackerStateSet, "bogus"),
        (HealthStateSet, "superficial"),
        (HealthStateSet, "aggravated"),
        (HealthStateSet, "bashing"),
        (HealthStateSet, "lethal"),
    ],
)
def test_state_set_requests_reject_unknown_fields(model: type[BaseModel], field: str) -> None:
    """Verify a stale or unknown key fails client-side instead of being dropped."""
    with pytest.raises(PydanticValidationError):
        model(**{field: 1})
