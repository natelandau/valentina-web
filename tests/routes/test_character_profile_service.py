"""Tests for routes/character_create/profile_form.py."""

from __future__ import annotations

from datetime import date

import pytest

from tests.helpers import seed_session
from vweb.api_client.models.characters import (
    HunterAttributes,
    MageAttributes,
    VampireAttributes,
    WerewolfAttributes,
)
from vweb.api_client.testing import CharacterFactory
from vweb.routes.character_create.profile_form import (
    build_class_attrs,
    character_to_form_data,
    validate_profile,
)

_VALID_MORTAL = {
    "name_first": "Alice",
    "name_last": "Smith",
    "game_version": "V5",
    "character_class": "MORTAL",
}


def _validate(app, **fields: str) -> dict[str, str]:
    with app.test_request_context():
        seed_session()
        return validate_profile({**_VALID_MORTAL, **fields})


class TestValidateProfile:
    """Tests for validate_profile()."""

    @pytest.mark.parametrize(
        "fields",
        [
            {},
            {"age": "0"},
            {"age": "100000"},
            {"date_of_birth": "1960-03-15"},
            {"character_class": "VAMPIRE", "vampire_clan_id": "clan-1"},
            {"character_class": "WEREWOLF", "werewolf_tribe_id": "t", "werewolf_auspice_id": "a"},
            {"character_class": "HUNTER", "creed": "Faithful"},
        ],
        ids=["mortal", "age-zero", "age-max", "date-of-birth", "vampire", "werewolf", "hunter"],
    )
    def test_accepts_valid_profile(self, app, fields: dict[str, str]) -> None:
        """Verify a complete profile with at most one valid age or birth date passes."""
        assert _validate(app, **fields) == {}

    @pytest.mark.parametrize(
        ("fields", "error_field"),
        [
            ({"name_first": ""}, "name_first"),
            ({"name_first": "Al"}, "name_first"),
            ({"name_last": "Sm"}, "name_last"),
            ({"game_version": "INVALID"}, "game_version"),
            ({"character_class": "INVALID"}, "character_class"),
            ({"character_class": "VAMPIRE"}, "vampire_clan_id"),
            ({"character_class": "GHOUL"}, "vampire_clan_id"),
            ({"character_class": "WEREWOLF", "werewolf_auspice_id": "a"}, "werewolf_tribe_id"),
            ({"character_class": "WEREWOLF", "werewolf_tribe_id": "t"}, "werewolf_auspice_id"),
            ({"character_class": "HUNTER"}, "creed"),
            ({"age": "100001"}, "age"),
            ({"age": "-1"}, "age"),
            ({"age": "old"}, "age"),
            ({"age": "1_000"}, "age"),
            ({"age": "+5"}, "age"),
            ({"date_of_birth": "1960-02-31"}, "date_of_birth"),
            ({"age": "30", "date_of_birth": "1960-03-15"}, "date_of_birth"),
        ],
        ids=[
            "missing-first-name",
            "short-first-name",
            "short-last-name",
            "invalid-game-version",
            "invalid-class",
            "vampire-without-clan",
            "ghoul-without-clan",
            "werewolf-without-tribe",
            "werewolf-without-auspice",
            "hunter-without-creed",
            "age-too-large",
            "age-negative",
            "age-not-a-number",
            "age-underscore",
            "age-signed",
            "invalid-date",
            "age-and-date",
        ],
    )
    def test_rejects_invalid_field(self, app, fields: dict[str, str], error_field: str) -> None:
        """Verify each invalid or missing value is reported on its own field."""
        assert set(_validate(app, **fields)) == {error_field}


class TestCharacterToFormData:
    """Tests for character_to_form_data()."""

    @pytest.mark.parametrize(
        ("character_kwargs", "expected"),
        [
            (
                {
                    "name_first": "Alice",
                    "name_last": "Smith",
                    "game_version": "V5",
                    "character_class": "MORTAL",
                    "type": "NPC",
                    "name_nick": "Ali",
                    "age": 25,
                    "date_of_birth": None,
                    "biography": "A brave soul.",
                    "demeanor": "Caregiver",
                    "nature": "Visionary",
                },
                {
                    "name_first": "Alice",
                    "name_last": "Smith",
                    "game_version": "V5",
                    "character_class": "MORTAL",
                    "character_type": "NPC",
                    "name_nick": "Ali",
                    "age": "25",
                    "biography": "A brave soul.",
                    "demeanor": "Caregiver",
                    "nature": "Visionary",
                },
            ),
            (
                {"date_of_birth": date(1960, 3, 15), "age": 58},
                {"date_of_birth": "1960-03-15"},
            ),
            (
                {"vampire_attributes": VampireAttributes(clan_id="clan-1")},
                {"vampire_clan_id": "clan-1"},
            ),
            (
                {"werewolf_attributes": WerewolfAttributes(tribe_id="t-1", auspice_id="a-1")},
                {"werewolf_tribe_id": "t-1", "werewolf_auspice_id": "a-1"},
            ),
            (
                {"hunter_attributes": HunterAttributes(creed="Faithful")},
                {"creed": "Faithful"},
            ),
            (
                {"mage_attributes": MageAttributes(sphere="Forces", tradition="Akashic")},
                {"sphere": "Forces", "tradition": "Akashic"},
            ),
        ],
        ids=["profile-fields", "date-of-birth-wins", "vampire", "werewolf", "hunter", "mage"],
    )
    def test_fills_form_fields(self, character_kwargs: dict, expected: dict[str, str]) -> None:
        """Verify the character's stored values pre-fill the matching form fields."""
        # When converting a character to form data
        data = character_to_form_data(CharacterFactory.build(**character_kwargs))

        # Then each stored value fills its field
        assert data | expected == data
        if "date_of_birth" in expected:
            assert "age" not in data

    def test_omits_unset_fields(self) -> None:
        """Verify unset optional and class fields are left out of the form data."""
        # Given a character with no optional or class-specific values
        character = CharacterFactory.build(
            name_nick=None,
            age=None,
            date_of_birth=None,
            biography=None,
            demeanor=None,
            nature=None,
            concept_id=None,
            vampire_attributes=VampireAttributes(),
            werewolf_attributes=WerewolfAttributes(),
            hunter_attributes=HunterAttributes(),
            mage_attributes=MageAttributes(),
        )

        # When converting to form data
        data = character_to_form_data(character)

        # Then only the required fields are present
        assert set(data) == {
            "name_first",
            "name_last",
            "game_version",
            "character_class",
            "character_type",
        }


class TestBuildClassAttrs:
    """Tests for build_class_attrs()."""

    @pytest.mark.parametrize(
        ("character_class", "form_data", "slot", "expected"),
        [
            ("VAMPIRE", {"vampire_clan_id": "clan-1"}, 0, {"clan_id": "clan-1"}),
            ("GHOUL", {"vampire_clan_id": "clan-1"}, 0, {"clan_id": "clan-1"}),
            (
                "WEREWOLF",
                {"werewolf_tribe_id": "t-1", "werewolf_auspice_id": "a-1"},
                1,
                {"tribe_id": "t-1", "auspice_id": "a-1"},
            ),
            ("HUNTER", {"creed": "Faithful"}, 2, {"creed": "Faithful"}),
            (
                "MAGE",
                {"sphere": "Forces", "tradition": ""},
                3,
                {"sphere": "Forces", "tradition": None},
            ),
            ("MORTAL", {}, None, None),
        ],
        ids=["vampire", "ghoul", "werewolf", "hunter", "mage", "mortal"],
    )
    def test_builds_only_the_class_attributes(
        self, character_class: str, form_data: dict, slot: int | None, expected: dict | None
    ) -> None:
        """Verify only the character's class gets attributes, for both create and update."""
        # When building class attrs
        create_attrs, update_attrs = build_class_attrs(character_class, form_data)

        # Then only the class's slot is filled, with the form's values
        for attrs in (create_attrs, update_attrs):
            for index, attr in enumerate(attrs):
                if index == slot:
                    assert attr is not None
                    assert attr.model_dump(exclude_unset=True) == expected
                else:
                    assert attr is None
