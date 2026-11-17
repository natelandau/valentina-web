"""Tests for routes/character_create/profile_form.py."""

from __future__ import annotations

from datetime import date

import pytest

from vweb.api_client.testing import CharacterFactory


class TestValidateProfile:
    """Tests for validate_profile()."""

    def test_valid_mortal_profile(self, app) -> None:
        """Verify valid mortal data returns an empty errors dict."""
        # Given a valid mortal form submission
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "MORTAL",
        }

        # When validating the profile
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then no errors are returned
        assert errors == {}

    def test_missing_first_name(self, app) -> None:
        """Verify empty first name returns a name_first error."""
        # Given form data with no first name
        form_data = {
            "name_first": "",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "MORTAL",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then name_first error is present
        assert "name_first" in errors

    def test_short_first_name(self, app) -> None:
        """Verify a 2-character first name returns a name_first error."""
        # Given form data with a too-short first name
        form_data = {
            "name_first": "Al",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "MORTAL",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then name_first error is present
        assert "name_first" in errors

    def test_vampire_requires_clan(self, app) -> None:
        """Verify VAMPIRE class without vampire_clan_id returns a vampire_clan_id error."""
        # Given a vampire form with no clan
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "VAMPIRE",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then vampire_clan_id error is present
        assert "vampire_clan_id" in errors

    def test_hunter_requires_creed(self, app) -> None:
        """Verify HUNTER class without creed returns a creed error."""
        # Given a hunter form with no creed
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "HUNTER",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then creed error is present
        assert "creed" in errors

    def test_werewolf_requires_tribe(self, app) -> None:
        """Verify WEREWOLF class without werewolf_tribe_id returns a werewolf_tribe_id error."""
        # Given a werewolf form with no tribe
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "WEREWOLF",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then werewolf_tribe_id error is present
        assert "werewolf_tribe_id" in errors

    def test_werewolf_requires_auspice(self, app) -> None:
        """Verify WEREWOLF class without an auspice returns a werewolf_auspice_id error."""
        # Given a werewolf form with a tribe but no auspice
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "WEREWOLF",
            "werewolf_tribe_id": "tribe-silver-fangs",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then the auspice is reported as required
        assert errors["werewolf_auspice_id"] == "Werewolf auspice is required."

    def test_invalid_game_version(self, app) -> None:
        """Verify an unrecognized game version returns a game_version error."""
        # Given form data with an invalid game version
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "INVALID",
            "character_class": "MORTAL",
        }

        # When validating
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            errors = validate_profile(form_data)

        # Then game_version error is present
        assert "game_version" in errors


class TestAgeValidation:
    """Tests for the profile form's age and date of birth fields."""

    def _validate(self, app, **fields: str) -> dict[str, str]:
        form_data = {
            "name_first": "Alice",
            "name_last": "Smith",
            "game_version": "V5",
            "character_class": "MORTAL",
            **fields,
        }
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            from vweb.routes.character_create.profile_form import validate_profile

            return validate_profile(form_data)

    @pytest.mark.parametrize(
        "fields",
        [{}, {"age": "0"}, {"age": "100000"}, {"date_of_birth": "1960-03-15"}],
    )
    def test_accepts_one_valid_value_or_none(self, app, fields: dict[str, str]) -> None:
        """Verify a blank pair, an age in range, or a valid date of birth passes."""
        assert self._validate(app, **fields) == {}

    @pytest.mark.parametrize(
        ("fields", "error_field"),
        [
            ({"age": "100001"}, "age"),
            ({"age": "-1"}, "age"),
            ({"age": "old"}, "age"),
            ({"age": "1_000"}, "age"),
            ({"age": "+5"}, "age"),
            ({"date_of_birth": "1960-02-31"}, "date_of_birth"),
            ({"age": "30", "date_of_birth": "1960-03-15"}, "date_of_birth"),
        ],
    )
    def test_rejects_invalid_or_both(self, app, fields: dict[str, str], error_field: str) -> None:
        """Verify an out-of-range age, a bad date, or both values together is rejected."""
        assert error_field in self._validate(app, **fields)


class TestCharacterToFormData:
    """Tests for character_to_form_data()."""

    def test_extracts_required_fields(self) -> None:
        """Verify required character fields appear in the returned form data."""
        from vweb.routes.character_create.profile_form import character_to_form_data

        # Given a character with known required fields
        character = CharacterFactory.build(
            name_first="Alice",
            name_last="Smith",
            game_version="V5",
            character_class="MORTAL",
        )

        # When converting to form data
        data = character_to_form_data(character)

        # Then all required fields are present
        assert data["name_first"] == "Alice"
        assert data["name_last"] == "Smith"
        assert data["game_version"] == "V5"
        assert data["character_class"] == "MORTAL"
        assert "character_type" in data

    def test_extracts_optional_fields(self) -> None:
        """Verify optional fields are included when set on the character."""
        from vweb.routes.character_create.profile_form import character_to_form_data

        # Given a character with optional fields populated
        character = CharacterFactory.build(
            name_first="Alice",
            name_last="Smith",
            name_nick="Ali",
            age=25,
            biography="A brave soul.",
            demeanor="Caregiver",
            nature="Visionary",
        )

        # When converting to form data
        data = character_to_form_data(character)

        # Then optional fields are present
        assert data["name_nick"] == "Ali"
        assert data["age"] == "25"
        assert data["biography"] == "A brave soul."
        assert data["demeanor"] == "Caregiver"
        assert data["nature"] == "Visionary"

    def test_omits_none_optional_fields(self) -> None:
        """Verify None optional fields are not included in form data."""
        from vweb.routes.character_create.profile_form import character_to_form_data

        # Given a character with None optional fields (factory defaults)
        character = CharacterFactory.build(
            name_nick=None,
            age=None,
            biography=None,
            demeanor=None,
            nature=None,
            concept_id=None,
        )

        # When converting to form data
        data = character_to_form_data(character)

        # Then None optional fields are absent
        assert "name_nick" not in data
        assert "age" not in data
        assert "biography" not in data
        assert "demeanor" not in data
        assert "nature" not in data
        assert "concept_id" not in data


class TestBuildClassAttrs:
    """Tests for build_class_attrs()."""

    def test_vampire_builds_create_and_update_attrs(self) -> None:
        """Verify VAMPIRE class builds both create and update attr tuples with clan_id."""
        from vweb.routes.character_create.profile_form import build_class_attrs

        # Given a vampire form with a clan
        form_data = {"vampire_clan_id": "clan-brujah"}

        # When building class attrs
        create_attrs, update_attrs = build_class_attrs("VAMPIRE", form_data)

        # Then vampire attrs contain the clan_id in both tuples
        vampire_c, werewolf_c, hunter_c, mage_c = create_attrs
        vampire_u, *_ = update_attrs

        assert vampire_c is not None
        assert vampire_c.clan_id == "clan-brujah"
        assert vampire_u is not None
        assert vampire_u.clan_id == "clan-brujah"
        assert werewolf_c is None
        assert hunter_c is None
        assert mage_c is None

    def test_mortal_returns_all_none(self) -> None:
        """Verify MORTAL class returns all-None attr tuples."""
        from vweb.routes.character_create.profile_form import build_class_attrs

        # Given a mortal form with no class-specific data
        form_data: dict[str, str] = {}

        # When building class attrs
        create_attrs, update_attrs = build_class_attrs("MORTAL", form_data)

        # Then all attrs are None
        assert all(a is None for a in create_attrs)
        assert all(a is None for a in update_attrs)

    def test_werewolf_builds_tribe_and_auspice(self) -> None:
        """Verify WEREWOLF class builds attrs with tribe_id and auspice_id."""
        from vweb.routes.character_create.profile_form import build_class_attrs

        # Given a werewolf form with tribe and auspice
        form_data = {
            "werewolf_tribe_id": "tribe-silver-fangs",
            "werewolf_auspice_id": "auspice-galliard",
        }

        # When building class attrs
        create_attrs, update_attrs = build_class_attrs("WEREWOLF", form_data)

        # Then werewolf attrs contain tribe and auspice
        vampire_c, werewolf_c, hunter_c, mage_c = create_attrs
        _vampire_u, werewolf_u, *_ = update_attrs

        assert werewolf_c is not None
        assert werewolf_c.tribe_id == "tribe-silver-fangs"
        assert werewolf_c.auspice_id == "auspice-galliard"
        assert werewolf_u is not None
        assert werewolf_u.tribe_id == "tribe-silver-fangs"
        assert vampire_c is None
        assert hunter_c is None
        assert mage_c is None

    def test_form_data_prefers_date_of_birth(self) -> None:
        """Verify a character with a date of birth fills only that field, not its stored age."""
        from vweb.routes.character_create.profile_form import character_to_form_data

        character = CharacterFactory.build(date_of_birth=date(1960, 3, 15), age=58)
        data = character_to_form_data(character)

        assert data["date_of_birth"] == "1960-03-15"
        assert "age" not in data
