"""Tests for the manual character creation service layer."""

from __future__ import annotations

import logging

from flask import session

from vweb.api_client.testing import CharacterFactory, Routes
from vweb.routes.character_create.manual_services import (
    build_trait_items,
    save_temp_character,
    update_character_profile,
)

_FORM = {
    "name_first": "Ada",
    "name_last": "Lovelace",
    "game_version": "V5",
    "character_class": "MORTAL",
}


def _set_field_error(fake_vclient, route) -> None:
    """Make ``route`` reject the name and the player with field errors."""
    fake_vclient.set_error(
        route,
        status_code=400,
        detail="Validation failed for one or more fields.",
        invalid_parameters=[
            {"field": "name_first", "message": "Name already taken"},
            {"field": "user_player_id", "message": "Unknown user."},
        ],
    )


def _save(app) -> dict[str, str]:
    with app.test_request_context():
        session["user_id"] = "u1"
        session["company_id"] = "company-1"
        return save_temp_character("camp-1", dict(_FORM))


def _update(app) -> dict[str, str]:
    with app.test_request_context():
        session["user_id"] = "u1"
        session["company_id"] = "company-1"
        return update_character_profile("char-1", dict(_FORM))


class TestUnrenderedFieldErrors:
    """API errors on fields the profile form cannot show inline still reach the user."""

    def test_save_folds_unrendered_field_into_general(self, app, fake_vclient) -> None:
        """Verify a player error lands in the banner while a name error stays inline."""
        # Given the API rejects the name and the player
        _set_field_error(fake_vclient, Routes.CHARACTERS_CREATE)

        # When saving the temporary character
        errors = _save(app)

        # Then the name error is inline and the player error is in the banner
        assert errors["name_first"] == "Name already taken"
        assert errors["_general"].startswith("Validation failed for one or more fields.")
        assert "Unknown user." in errors["_general"]

    def test_update_folds_unrendered_field_into_general(self, app, fake_vclient) -> None:
        """Verify edit mode folds the same way."""
        # Given the API rejects the name and the player
        _set_field_error(fake_vclient, Routes.CHARACTERS_UPDATE)

        # When updating the profile
        errors = _update(app)

        # Then the character was patched, and the player error is in the banner
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            params={"company_id": "company-1", "character_id": "char-1"},
            times=1,
        )
        assert errors["_general"].endswith("Unknown user.")
        assert "user_player_id" not in errors


class TestCharacterTypeError:
    """The API's ``type`` field is the form's character type."""

    def test_type_error_is_shown_beside_character_type(self, app, fake_vclient) -> None:
        """Verify an API error on type lands on the character_type field."""
        # Given the API refuses the character type
        fake_vclient.set_error(
            Routes.CHARACTERS_CREATE,
            status_code=400,
            detail="Validation failed for one or more fields.",
            invalid_parameters=[{"field": "type", "message": "Not allowed"}],
        )

        # When saving
        errors = _save(app)

        # Then the message is shown inline on the character type
        assert errors["character_type"] == "Not allowed"
        assert "Not allowed" not in errors.get("_general", "")


class TestSaveLogging:
    """Expected API refusals are not logged as errors; unexpected failures are logged once."""

    def test_validation_error_is_not_logged(self, app, fake_vclient, caplog) -> None:
        """Verify an API 400 produces no error log."""
        # Given the API rejects the submission
        _set_field_error(fake_vclient, Routes.CHARACTERS_CREATE)

        # When saving
        with caplog.at_level(logging.WARNING):
            _save(app)

        # Then nothing is logged at error
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_server_error_is_logged_once(self, app, fake_vclient, caplog) -> None:
        """Verify a server error is logged exactly once and shows the fallback."""
        # Given a save that fails server-side
        fake_vclient.set_error(Routes.CHARACTERS_CREATE, status_code=500, detail="db exploded")

        # When saving
        with caplog.at_level(logging.WARNING):
            errors = _save(app)

        # Then the request was sent once, the fallback is shown, and one error is logged
        fake_vclient.assert_called(Routes.CHARACTERS_CREATE, times=1)
        assert errors == {"_general": "Failed to save profile"}
        assert len([r for r in caplog.records if r.levelno >= logging.ERROR]) == 1


class TestBuildTraitItems:
    """Tests for build_trait_items."""

    def test_keeps_values_within_the_api_range(self) -> None:
        """Verify only integer values from 1 to 100 become trait payloads."""
        # Given a traits form with in-range, zero, oversized, and non-numeric values
        form = {
            "trait:t1": "3",
            "trait:t2": "0",
            "trait:t3": "101",
            "trait:t4": "abc",
            "trait:t5": "100",
            "name": "ignored",
        }

        # When building the payloads
        items = build_trait_items(form)

        # Then only the traits at 3 and 100 are kept
        assert [(item.trait_id, item.value) for item in items] == [("t1", 3), ("t5", 100)]


class TestAgePayload:
    """The profile form sends an age or a date of birth, and clears the other."""

    @staticmethod
    def _update(app, form: dict[str, str], *, keep_stored_age: bool = False) -> None:
        with app.test_request_context():
            session["user_id"] = "u1"
            session["company_id"] = "company-1"
            update_character_profile("char-1", {**_FORM, **form}, keep_stored_age=keep_stored_age)

    def test_create_sends_date_of_birth(self, app, fake_vclient) -> None:
        """Verify creating a character sends the date of birth and no age."""
        fake_vclient.set_response(Routes.CHARACTERS_CREATE, model=CharacterFactory.build())
        with app.test_request_context():
            session["user_id"] = "u1"
            session["company_id"] = "company-1"
            save_temp_character("camp-1", {**_FORM, "date_of_birth": "1960-03-15"})

        body = fake_vclient.requests_for(Routes.CHARACTERS_CREATE)[0].json
        assert body["date_of_birth"] == "1960-03-15"
        assert "age" not in body

    def test_update_with_date_of_birth_clears_age(self, app, fake_vclient) -> None:
        """Verify choosing a date of birth clears the stored age."""
        fake_vclient.set_response(Routes.CHARACTERS_UPDATE, model=CharacterFactory.build())
        self._update(app, {"date_of_birth": "1960-03-15"})
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            json_subset={"date_of_birth": "1960-03-15", "age": None},
            times=1,
        )

    def test_update_with_age_clears_date_of_birth(self, app, fake_vclient) -> None:
        """Verify choosing an age clears the date of birth."""
        fake_vclient.set_response(Routes.CHARACTERS_UPDATE, model=CharacterFactory.build())
        self._update(app, {"age": "3236"})
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            json_subset={"age": 3236, "date_of_birth": None},
            times=1,
        )

    def test_dead_character_keeps_age_at_death(self, app, fake_vclient) -> None:
        """Verify a dead character's stored age survives saving a date of birth."""
        fake_vclient.set_response(Routes.CHARACTERS_UPDATE, model=CharacterFactory.build())
        self._update(app, {"date_of_birth": "1960-03-15"}, keep_stored_age=True)
        body = fake_vclient.requests_for(Routes.CHARACTERS_UPDATE)[0].json
        assert body["date_of_birth"] == "1960-03-15"
        assert "age" not in body


def test_update_clears_blanked_profile_fields(app, fake_vclient) -> None:
    """Verify blank optional fields on the profile form clear the stored values."""
    # Given a profile form whose nickname, biography, demeanor, nature, and concept are blank
    fake_vclient.set_response(Routes.CHARACTERS_UPDATE, model=CharacterFactory.build())
    form = {**_FORM, "name_nick": "", "biography": "", "demeanor": "", "nature": ""}

    # When updating the profile
    with app.test_request_context():
        session["user_id"] = "u1"
        session["company_id"] = "company-1"
        update_character_profile("char-1", form)

    # Then each blank field is sent as null so the API clears it
    fake_vclient.assert_called(
        Routes.CHARACTERS_UPDATE,
        json_subset={
            "name_nick": None,
            "biography": None,
            "demeanor": None,
            "nature": None,
            "concept_id": None,
        },
        times=1,
    )
