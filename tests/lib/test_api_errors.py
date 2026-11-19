"""Tests for the shared API error message helpers."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    RequestValidationError,
    ServerError,
    ValidationError,
)
from vweb.constants import MAX_IMAGE_SIZE_MB
from vweb.lib.api_errors import (
    USER_FACING_API_ERRORS,
    api_error_message,
    api_error_messages,
    api_field_errors,
)

_GENERIC = "Validation failed for one or more fields."


class _Roll(BaseModel):
    num_dice: int = Field(le=100)


class _Named(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _check(cls, value: str) -> str:  # noqa: ARG003
        msg = "Name must be short"
        raise ValueError(msg)


class _Inner(BaseModel):
    clan_id: int


class _Outer(BaseModel):
    vampire_attributes: _Inner


def _pydantic_error(model: type[BaseModel], **data: object) -> PydanticValidationError:
    with pytest.raises(PydanticValidationError) as info:
        model(**data)
    return info.value


def _validation_error(params: list[dict[str, str]], detail: str = "Bad input") -> ValidationError:
    return ValidationError(
        detail,
        400,
        {"detail": detail, "invalid_parameters": params} if params else {"detail": detail},
    )


def _param(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


@pytest.mark.parametrize(
    ("params", "detail", "expected"),
    [
        pytest.param(
            [_param("num_dice", "At most 100"), _param("difficulty", "At least 1")],
            "Bad input",
            ["Num dice: At most 100", "Difficulty: At least 1"],
            id="labels-each-field",
        ),
        pytest.param(
            [_param("body", "Values are not valid.")],
            "Bad input",
            ["Values are not valid."],
            id="body-message-unlabeled",
        ),
        pytest.param([], "Nope", ["Nope"], id="no-params-uses-detail"),
        pytest.param(
            [_param("body", ""), _param("name", "  ")], " ", [], id="blank-messages-dropped"
        ),
        pytest.param([_param("body", "")], "Bad input", ["Bad input"], id="blank-body-uses-detail"),
        pytest.param(
            [_param("name", ""), _param("age", "Too low")],
            "Bad input",
            ["Age: Too low"],
            id="only-blank-entry-dropped",
        ),
        pytest.param(
            [_param("amount", "Cannot spend 3.")],
            "Cannot spend 3.",
            ["Cannot spend 3."],
            id="message-equal-to-detail-unlabeled",
        ),
        pytest.param(
            [_param("amount", "Cannot spend 3.")],
            _GENERIC,
            ["Amount: Cannot spend 3."],
            id="label-kept-under-generic-detail",
        ),
        pytest.param(
            [_param("[0].trait_id", "Must be a valid ID.")],
            _GENERIC,
            ["Trait id: Must be a valid ID."],
            id="nested-path-last-segment",
        ),
        pytest.param([_param("tags[2]", "Bad.")], _GENERIC, ["Tags: Bad."], id="index-suffix"),
        pytest.param(
            [_param("traits[2].value", "Bad.")], _GENERIC, ["Value: Bad."], id="indexed-nested"
        ),
        pytest.param([_param("metadata.x", "Bad.")], _GENERIC, ["X: Bad."], id="dotted"),
        pytest.param([_param("a.", "Bad.")], _GENERIC, ["A: Bad."], id="trailing-dot"),
        pytest.param([_param("[0]", "Bad.")], _GENERIC, ["Bad."], id="index-only-no-label"),
    ],
)
def test_validation_error_messages(params, detail: str, expected: list[str]) -> None:
    """Verify field messages are labeled by their innermost field name, without repeats."""
    assert api_error_messages(_validation_error(params, detail)) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(
            RequestValidationError(_pydantic_error(_Roll, num_dice=500)),
            "Num dice: ",
            id="request-validation",
        ),
        pytest.param(_pydantic_error(_Roll, num_dice=500), "Num dice: ", id="pydantic"),
        pytest.param(
            _pydantic_error(_Outer, vampire_attributes={"clan_id": "abc"}),
            "Clan id: ",
            id="nested-pydantic",
        ),
    ],
)
def test_client_side_validation_messages(error: Exception, expected: str) -> None:
    """Verify client-side validation failures read as labeled field messages."""
    message = api_error_message(error, fallback="fallback")

    assert message.startswith(expected)
    assert "None" not in message


def test_value_error_prefix_is_stripped() -> None:
    """Verify pydantic's custom-validator prefix never reaches the user."""
    assert api_error_messages(_pydantic_error(_Named, name="x")) == ["Name: Name must be short"]


def test_labels_replace_the_field_label() -> None:
    """Verify a caller-supplied label replaces the field's name."""
    error = _validation_error([_param("amount", "Must be at most 10000.")], "Validation failed.")

    assert (
        api_error_message(error, fallback="Oops", labels={"amount": "XP"})
        == "XP: Must be at most 10000."
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(ConflictError("m", 409, {"detail": "Exists"}), "Exists", id="conflict"),
        pytest.param(AuthorizationError("m", 403, {"detail": "No"}), "No", id="authorization"),
        pytest.param(NotFoundError("m", 404, {"detail": "Gone"}), "Gone", id="not-found"),
        pytest.param(ConflictError("m", 409, {"detail": "   "}), "Oops", id="blank-detail"),
        pytest.param(ServerError("boom", 500, {"detail": "db exploded"}), "Oops", id="server"),
        pytest.param(APIError("weird", 418, {"detail": "secret"}), "Oops", id="unclassified"),
        pytest.param(APIConnectionError("Could not reach the API"), "Oops", id="connection"),
        pytest.param(RateLimitError("slow", 429, None, retry_after=None), "Oops", id="no-wait"),
    ],
)
def test_error_detail_shown_only_when_written_for_users(error: Exception, expected: str) -> None:
    """Verify user-fixable errors show the API's detail and anything else shows the fallback."""
    assert api_error_message(error, fallback="Oops") == expected


def test_413_names_the_upload_limit() -> None:
    """Verify an oversized upload names the size limit."""
    message = api_error_message(PayloadTooLargeError("too big", 413, None), fallback="fallback")

    assert f"{MAX_IMAGE_SIZE_MB} MB" in message


@pytest.mark.parametrize(
    ("seconds", "expected", "unexpected"),
    [(30, "30 seconds", None), (1, "1 second", "1 seconds")],
)
def test_rate_limit_names_the_wait(seconds: int, expected: str, unexpected: str | None) -> None:
    """Verify a rate limit tells the user how long to wait, in the right number."""
    error = RateLimitError("slow down", 429, {"detail": "Too many"}, retry_after=seconds)

    message = api_error_message(error, fallback="Oops")

    assert expected in message
    if unexpected:
        assert unexpected not in message


@pytest.mark.parametrize(
    ("error", "levels"),
    [
        pytest.param(APIConnectionError("down"), [logging.ERROR], id="connection"),
        pytest.param(ServerError("boom", 500, {"detail": "x"}), [logging.ERROR], id="server"),
        pytest.param(AuthenticationError("no", 401, {"detail": "x"}), [logging.WARNING], id="auth"),
        pytest.param(RateLimitError("slow", 429, None, retry_after=30), [], id="rate-limit"),
    ],
)
def test_fallback_log_level(caplog, error: Exception, levels: list[int]) -> None:
    """Verify fallbacks log as errors, except expected conditions such as rejected credentials."""
    with caplog.at_level(logging.WARNING, logger="vweb.lib.api_errors"):
        api_error_message(error, fallback="Oops")

    assert [r.levelno for r in caplog.records] == levels


@pytest.mark.parametrize(
    ("cls", "user_facing"),
    [
        (ValidationError, True),
        (PydanticValidationError, True),
        (NotFoundError, True),
        (ServerError, False),
        (APIConnectionError, False),
    ],
)
def test_user_facing_error_classes(cls: type[Exception], *, user_facing: bool) -> None:
    """Verify only errors a user can fix are caught as user-facing."""
    assert issubclass(cls, USER_FACING_API_ERRORS) is user_facing


@pytest.mark.parametrize(
    ("params", "detail", "kwargs", "expected"),
    [
        pytest.param(
            [_param("name_first", "Too short")],
            "Bad input",
            {},
            {"name_first": "Too short", "_general": "Bad input"},
            id="field-and-detail",
        ),
        pytest.param(
            [_param("body", ""), _param("name", "  ")], " ", {}, {"_general": "Oops"}, id="blank"
        ),
        pytest.param(
            [_param("name", ""), _param("age", "Too low")],
            "Bad input",
            {},
            {"age": "Too low", "_general": "Bad input"},
            id="blank-field-dropped",
        ),
        pytest.param(
            [_param("body", "Body msg")],
            "Detail msg",
            {},
            {"_general": "Detail msg"},
            id="detail-outranks-body",
        ),
        pytest.param(
            [_param("value", "At most 5")],
            "At most 5",
            {},
            {"value": "At most 5"},
            id="detail-repeating-field-not-shown-twice",
        ),
        pytest.param(
            [_param("name_first", "Too short"), _param("age", "Must be at least 0.")],
            _GENERIC,
            {"inline_fields": {"name_first"}},
            {"name_first": "Too short", "_general": f"{_GENERIC} Age: Must be at least 0."},
            id="fold-unrendered-fields",
        ),
        pytest.param(
            [_param("body", "Did not pass."), _param("age", "Must be at least 0.")],
            " ",
            {"inline_fields": {"name_first"}},
            {"_general": "Did not pass. Age: Must be at least 0."},
            id="body-beside-folded",
        ),
        pytest.param(
            [_param("type", "Not allowed")],
            "Validation failed.",
            {"inline_fields": {"character_type"}, "aliases": {"type": "character_type"}},
            {"character_type": "Not allowed", "_general": "Validation failed."},
            id="alias",
        ),
    ],
)
def test_api_field_errors(params, detail: str, kwargs: dict, expected: dict[str, str]) -> None:
    """Verify validation errors map to inline field messages plus a general banner."""
    assert (
        api_field_errors(_validation_error(params, detail), fallback="Oops", **kwargs) == expected
    )


@pytest.mark.parametrize(
    ("error", "expected_keys"),
    [
        pytest.param(_pydantic_error(_Roll, num_dice=500), ["num_dice"], id="pydantic"),
        pytest.param(
            _pydantic_error(_Outer, vampire_attributes={"clan_id": "abc"}),
            ["vampire_attributes"],
            id="nested-keys-by-top-level-field",
        ),
    ],
)
def test_api_field_errors_for_client_side_validation(
    error: Exception, expected_keys: list[str]
) -> None:
    """Verify client-side validation errors key by the form's top-level field."""
    assert list(api_field_errors(error, fallback="Oops")) == expected_keys


def test_api_field_errors_server_error_uses_fallback() -> None:
    """Verify a server error shows only the fallback in the general banner."""
    error = ServerError("boom", 500, {"detail": "db exploded"})

    assert api_field_errors(error, fallback="Failed to save") == {"_general": "Failed to save"}
