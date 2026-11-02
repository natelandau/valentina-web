"""Tests for the shared API error message helpers."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError
from vclient.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    RequestValidationError,
    ServerError,
    ValidationError,
)

from vweb.lib.api_errors import (
    USER_FACING_API_ERRORS,
    api_error_message,
    api_error_messages,
    api_field_errors,
)


class _Roll(BaseModel):
    num_dice: int = Field(le=100)


def _pydantic_error() -> PydanticValidationError:
    with pytest.raises(PydanticValidationError) as info:
        _Roll(num_dice=500)
    return info.value


def _validation_error(params: list[dict[str, str]], detail: str = "Bad input") -> ValidationError:
    return ValidationError(
        detail,
        400,
        {"detail": detail, "invalid_parameters": params} if params else {"detail": detail},
    )


def test_validation_error_lists_field_messages():
    """Validation error lists field messages."""
    error = _validation_error(
        [
            {"field": "num_dice", "message": "Input should be at most 100"},
            {"field": "difficulty", "message": "Input should be at least 1"},
        ]
    )

    assert api_error_messages(error) == [
        "Num dice: Input should be at most 100",
        "Difficulty: Input should be at least 1",
    ]


def test_validation_error_body_field_uses_message_only():
    """Validation error body field uses message only."""
    error = _validation_error([{"field": "body", "message": "One or more values are not valid."}])

    assert api_error_messages(error) == ["One or more values are not valid."]


def test_validation_error_without_params_uses_detail():
    """Validation error without params uses detail."""
    assert api_error_messages(_validation_error([], "Nope")) == ["Nope"]


def test_request_validation_error_uses_pydantic_errors():
    """Request validation error uses pydantic errors."""
    message = api_error_message(RequestValidationError(_pydantic_error()), fallback="fallback")

    assert message.startswith("Num dice: ")
    assert "None" not in message


def test_pydantic_validation_error_uses_errors():
    """Pydantic validation error uses errors."""
    assert api_error_messages(_pydantic_error())[0].startswith("Num dice: ")


@pytest.mark.parametrize("cls", [ConflictError, AuthorizationError, NotFoundError])
def test_conflict_and_authorization_use_detail(cls):
    """Conflict and authorization use detail."""
    error = cls("msg", 409, {"detail": "Already exists"})

    assert api_error_messages(error) == ["Already exists"]


def test_413_names_the_upload_limit():
    """413 names the upload limit."""
    message = api_error_message(APIError("too big", 413, None), fallback="fallback")

    assert "Upload is too large (max " in message


def test_server_error_falls_back():
    """Server error falls back."""
    error = ServerError("boom", 500, {"detail": "db exploded"})

    assert api_error_messages(error) == []
    assert (
        api_error_message(error, fallback="Roll failed - please try again.")
        == "Roll failed - please try again."
    )


def test_unclassified_api_error_never_shows_detail():
    """Unclassified api error never shows detail."""
    error = APIError("weird", 418, {"detail": "secret"})

    assert api_error_message(error, fallback="Oops") == "Oops"


def test_user_facing_tuple_covers_expected_types():
    """User facing tuple covers expected types."""
    assert ServerError not in USER_FACING_API_ERRORS
    assert ValidationError in USER_FACING_API_ERRORS
    assert PydanticValidationError in USER_FACING_API_ERRORS


def test_api_field_errors_matches_manual_create_shape():
    """Api field errors matches manual create shape."""
    error = _validation_error([{"field": "name_first", "message": "Too short"}], "Bad input")

    assert api_field_errors(error, fallback="Failed") == {
        "name_first": "Too short",
        "_general": "Bad input",
    }


def test_api_field_errors_pydantic_keys_by_field():
    """Api field errors pydantic keys by field."""
    assert "num_dice" in api_field_errors(_pydantic_error(), fallback="Failed")


def test_api_field_errors_server_error_uses_fallback():
    """Api field errors server error uses fallback."""
    error = ServerError("boom", 500, {"detail": "db exploded"})

    assert api_field_errors(error, fallback="Failed to save profile") == {
        "_general": "Failed to save profile"
    }


def test_blank_messages_are_dropped():
    """Blank params fall through to the fallback."""
    error = _validation_error(
        [{"field": "body", "message": ""}, {"field": "name", "message": "  "}], detail=" "
    )

    assert api_error_messages(error) == []
    assert api_error_message(error, fallback="Oops") == "Oops"
    assert api_field_errors(error, fallback="Oops") == {"_general": "Oops"}


def test_blank_body_message_uses_detail():
    """A blank body message yields to the detail."""
    error = _validation_error([{"field": "body", "message": ""}], detail="Bad input")

    assert api_error_messages(error) == ["Bad input"]


def test_blank_named_field_message_is_dropped_but_others_kept():
    """Only the blank entry disappears."""
    error = _validation_error(
        [{"field": "name", "message": ""}, {"field": "age", "message": "Too low"}]
    )

    assert api_error_messages(error) == ["Age: Too low"]
    assert api_field_errors(error, fallback="Oops")["age"] == "Too low"
    assert "name" not in api_field_errors(error, fallback="Oops")


def test_blank_detail_on_conflict_falls_back():
    """Whitespace-only detail is treated as unset."""
    error = ConflictError("msg", 409, {"detail": "   "})

    assert api_error_message(error, fallback="Oops") == "Oops"


def test_value_error_prefix_is_stripped():
    """Pydantic's validator prefix is removed."""

    class _M(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def _check(cls, value: str) -> str:  # noqa: ARG003
            msg = "Name must be short"
            raise ValueError(msg)

    with pytest.raises(PydanticValidationError) as info:
        _M(name="x")

    assert api_error_messages(info.value) == ["Name: Name must be short"]


def test_detail_outranks_body_message_in_field_errors():
    """The detail wins _general when a body entry also exists."""
    error = _validation_error([{"field": "body", "message": "Body msg"}], detail="Detail msg")

    assert api_field_errors(error, fallback="Oops") == {"_general": "Detail msg"}


def test_field_label_dropped_when_message_repeats_detail():
    """A field message equal to the detail reads as the plain sentence."""
    message = "Value must be less than or equal to 5"
    error = _validation_error([{"field": "value", "message": message}], detail=message)

    assert api_error_messages(error) == [message]


def test_field_label_kept_when_detail_differs():
    """A field message under a generic detail keeps its label."""
    error = _validation_error(
        [{"field": "amount", "message": "Cannot spend 3: only 1 remaining."}],
        detail="Validation failed for one or more fields.",
    )

    assert api_error_messages(error) == ["Amount: Cannot spend 3: only 1 remaining."]


def test_amount_message_equal_to_detail_is_plain():
    """The tracker rule's message is shown once, without a label."""
    message = "Cannot spend 3: only 1 remaining."
    error = _validation_error([{"field": "amount", "message": message}], detail=message)

    assert api_error_messages(error) == [message]


def test_campaign_id_message_equal_to_detail_is_plain():
    """An id field's message equal to the detail is shown without a label."""
    message = "Campaign ID is required"
    error = _validation_error([{"field": "campaign_id", "message": message}], detail=message)

    assert api_error_messages(error) == [message]
    assert api_field_errors(error, fallback="Oops") == {"campaign_id": message}


def test_field_errors_skip_general_when_detail_repeats_field_message():
    """The same text is not shown both inline and in the banner."""
    message = "Value must be less than or equal to 5"
    error = _validation_error([{"field": "value", "message": message}], detail=message)

    assert api_field_errors(error, fallback="Oops") == {"value": message}


def test_api_sentence_follows_label():
    """The API's sentence is shown as-is after the field label."""
    error = _validation_error(
        [{"field": "num_dice", "message": "Must be at most 100."}],
        detail="Validation failed for one or more fields.",
    )

    assert api_error_messages(error) == ["Num dice: Must be at most 100."]


def test_api_sentence_inline_is_unchanged():
    """An inline field message is the API's sentence, unchanged."""
    error = _validation_error(
        [{"field": "age", "message": "Must be at least 0."}], detail="Validation failed."
    )

    assert api_field_errors(error, fallback="Oops")["age"] == "Must be at least 0."


def test_required_field_message_follows_label():
    """A missing field reads as the label plus the API's sentence."""
    error = _validation_error(
        [{"field": "name", "message": "This field is required."}],
        detail="Validation failed for one or more fields.",
    )

    assert api_error_messages(error) == ["Name: This field is required."]


def test_nested_path_labels_last_segment():
    """A nested or indexed field path is labeled by its last segment."""
    error = _validation_error(
        [{"field": "[0].trait_id", "message": "Must be a valid ID."}],
        detail="Validation failed for one or more fields.",
    )

    assert api_error_messages(error) == ["Trait id: Must be a valid ID."]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("tags[2]", "Tags: Must be text."),
        ("traits[2].value", "Value: Must be text."),
        ("metadata.x", "X: Must be text."),
        ("a.", "A: Must be text."),
        ("[0]", "Must be text."),
    ],
)
def test_index_terminated_path_keeps_a_label(field, expected):
    """A path ending in an index or a dot labels by its last named segment, or drops the label."""
    error = _validation_error(
        [{"field": field, "message": "Must be text."}],
        detail="Validation failed for one or more fields.",
    )

    assert api_error_messages(error) == [expected]


def test_labels_replace_the_field_label():
    """A caller-supplied label replaces the field's name."""
    error = _validation_error(
        [{"field": "amount", "message": "Must be at most 10000."}], detail="Validation failed."
    )

    assert (
        api_error_message(error, fallback="Oops", labels={"amount": "XP"})
        == "XP: Must be at most 10000."
    )


def test_field_errors_fold_unrendered_fields_into_general():
    """Fields the form does not render are folded into the banner."""
    error = _validation_error(
        [
            {"field": "name_first", "message": "Too short"},
            {"field": "age", "message": "Must be at least 0."},
        ],
        detail="Validation failed for one or more fields.",
    )

    assert api_field_errors(error, fallback="Oops", inline_fields={"name_first"}) == {
        "name_first": "Too short",
        "_general": "Validation failed for one or more fields. Age: Must be at least 0.",
    }


def test_nested_pydantic_error_keys_by_top_level_field():
    """A nested model error is keyed by the form's top-level field."""

    class _Inner(BaseModel):
        clan_id: int

    class _Outer(BaseModel):
        vampire_attributes: _Inner

    with pytest.raises(PydanticValidationError) as info:
        _Outer(vampire_attributes={"clan_id": "abc"})

    errors = api_field_errors(info.value, fallback="Oops")
    assert list(errors) == ["vampire_attributes"]
    assert api_error_messages(info.value)[0].startswith("Clan id: ")


def test_rate_limit_with_retry_after_names_the_wait(caplog):
    """A rate limit names the wait and is not logged as an error."""
    error = RateLimitError("slow down", 429, {"detail": "Too many"}, retry_after=30)

    with caplog.at_level(logging.WARNING, logger="vweb.lib.api_errors"):
        message = api_error_message(error, fallback="Oops")

    assert message == "Too many requests. Please wait 30 seconds and try again."
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_rate_limit_with_one_second_is_singular():
    """A one second wait reads in the singular."""
    error = RateLimitError("slow down", 429, None, retry_after=1)

    assert (
        api_error_message(error, fallback="Oops")
        == "Too many requests. Please wait 1 second and try again."
    )


def test_authentication_fallback_logs_at_warning(caplog):
    """An authentication failure falls back and logs at warning."""
    error = AuthenticationError("no key", 401, {"detail": "bad key"})

    with caplog.at_level(logging.WARNING, logger="vweb.lib.api_errors"):
        message = api_error_message(error, fallback="Oops")

    assert message == "Oops"
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_server_error_fallback_logs_at_error(caplog):
    """A server error falls back and logs at error."""
    error = ServerError("boom", 500, {"detail": "db exploded"})

    with caplog.at_level(logging.WARNING, logger="vweb.lib.api_errors"):
        api_error_message(error, fallback="Oops")

    assert [r.levelno for r in caplog.records] == [logging.ERROR]


def test_field_errors_keep_body_message_beside_folded_fields():
    """A body-level message is not lost when other field messages are folded."""
    error = _validation_error(
        [
            {"field": "body", "message": "One or more fields did not pass validation."},
            {"field": "age", "message": "Must be at least 0."},
        ],
        detail=" ",
    )

    assert api_field_errors(error, fallback="Oops", inline_fields={"name_first"}) == {
        "_general": "One or more fields did not pass validation. Age: Must be at least 0."
    }


def test_field_errors_alias_maps_api_field_to_form_field():
    """An aliased API field is shown beside the form field it came from."""
    error = _validation_error(
        [{"field": "type", "message": "Not allowed"}], detail="Validation failed."
    )

    assert api_field_errors(
        error,
        fallback="Oops",
        inline_fields={"character_type"},
        aliases={"type": "character_type"},
    ) == {"character_type": "Not allowed", "_general": "Validation failed."}
