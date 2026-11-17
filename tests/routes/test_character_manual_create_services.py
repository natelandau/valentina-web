"""Tests for the manual character creation service layer."""

from __future__ import annotations

import logging

from flask import session

from vweb.api_client.testing import Routes
from vweb.routes.character_create.manual_services import (
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
    """Make ``route`` reject the name and the age with field errors."""
    fake_vclient.set_error(
        route,
        status_code=400,
        detail="Validation failed for one or more fields.",
        invalid_parameters=[
            {"field": "name_first", "message": "Name already taken"},
            {"field": "age", "message": "Must be at least 0."},
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
        """Verify an age error lands in the banner while a name error stays inline."""
        # Given the API rejects the name and the age
        _set_field_error(fake_vclient, Routes.CHARACTERS_CREATE)

        # When saving the temporary character
        errors = _save(app)

        # Then the name error is inline and the age error is in the banner
        assert errors == {
            "name_first": "Name already taken",
            "_general": "Validation failed for one or more fields. Age: Must be at least 0.",
        }

    def test_update_folds_unrendered_field_into_general(self, app, fake_vclient) -> None:
        """Verify edit mode folds the same way."""
        # Given the API rejects the name and the age
        _set_field_error(fake_vclient, Routes.CHARACTERS_UPDATE)

        # When updating the profile
        errors = _update(app)

        # Then the character was patched, and the age error is in the banner
        fake_vclient.assert_called(
            Routes.CHARACTERS_UPDATE,
            params={"company_id": "company-1", "character_id": "char-1"},
            times=1,
        )
        assert errors["_general"].endswith("Age: Must be at least 0.")
        assert "age" not in errors


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
