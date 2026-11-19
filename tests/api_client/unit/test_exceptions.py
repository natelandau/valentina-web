"""Tests for vweb.api_client.exceptions."""

import pytest
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.constants import IDEMPOTENCY_IN_PROGRESS_CODE
from vweb.api_client.exceptions import (
    APIError,
    ConflictError,
    FieldError,
    RateLimitError,
    RequestValidationError,
    ValidationError,
)

_FULL_PROBLEM = {
    "status": 404,
    "title": "Not Found",
    "detail": "Company 'abc123' not found",
    "instance": "/api/v1/companies/abc123",
    "code": "COMPANY_MISSING",
    "request_id": "req_abc123",
}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(APIError("Unknown error"), "Unknown error", id="message-only"),
        pytest.param(APIError("Bad request", status_code=400), "[400] Bad request", id="status"),
        pytest.param(APIError("", status_code=500), "[500]", id="status-without-message"),
        pytest.param(APIError(""), "Unknown API error", id="empty"),
        pytest.param(
            APIError("Not found", status_code=404, response_data=_FULL_PROBLEM),
            "[404] Not Found | Detail: Company 'abc123' not found | Code: COMPANY_MISSING"
            " | Instance: /api/v1/companies/abc123 | Request-ID: req_abc123",
            id="full-problem-details",
        ),
        pytest.param(
            APIError(
                "Resource not found",
                status_code=404,
                response_data={"title": "Not Found", "detail": "Resource not found"},
            ),
            "[404] Not Found",
            id="detail-same-as-message-omitted",
        ),
        pytest.param(
            ValidationError(
                "Validation failed",
                status_code=400,
                response_data={
                    "title": "Bad Request",
                    "invalid_parameters": [
                        {"field": "name", "message": "Field required"},
                        {"field": "role", "message": "Invalid value"},
                    ],
                },
            ),
            "[400] Bad Request | Fields: name: Field required; role: Invalid value",
            id="validation-fields",
        ),
        pytest.param(
            ValidationError("Validation failed", status_code=400, response_data={}),
            "[400] Validation failed",
            id="validation-without-fields",
        ),
        pytest.param(
            RateLimitError(
                "Too many requests",
                status_code=429,
                response_data={"title": "Too Many Requests"},
                retry_after=60,
                remaining=0,
            ),
            "[429] Too Many Requests | retry_after=60s, remaining=0",
            id="rate-limit-timing",
        ),
        pytest.param(
            RateLimitError("Too many requests", status_code=429),
            "[429] Too many requests",
            id="rate-limit-without-timing",
        ),
    ],
)
def test_str_formats_problem_details(error: APIError, expected: str) -> None:
    """Verify the string form carries the problem details fields that are present."""
    assert str(error) == expected


@pytest.mark.parametrize(
    ("attribute", "key"),
    [
        ("title", "title"),
        ("detail", "detail"),
        ("instance", "instance"),
        ("code", "code"),
        ("request_id", "request_id"),
    ],
)
def test_problem_details_properties_read_the_response(attribute: str, key: str) -> None:
    """Verify each RFC 9457 property reads its response key, and is None when it is missing."""
    assert getattr(APIError("x", 404, _FULL_PROBLEM), attribute) == _FULL_PROBLEM[key]
    assert getattr(APIError("x", 404, {}), attribute) is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [(IDEMPOTENCY_IN_PROGRESS_CODE, True), ("IDENTITY_ALREADY_LINKED", False), (None, False)],
)
def test_conflict_detects_idempotency_in_progress(
    code: str | None,
    expected: bool,  # noqa: FBT001
) -> None:
    """Verify only the in-progress code marks a conflict as an idempotent request still running."""
    error = ConflictError("Conflict", 409, {"code": code} if code else {}, retry_after=2)

    assert error.is_idempotency_in_progress is expected


@pytest.mark.parametrize(
    ("response_data", "expected"),
    [
        pytest.param(
            {
                "invalid_parameters": [
                    {"field": "[0].trait_id", "message": "  Not found  "},
                    {"field": "name", "message": ""},
                    {"message": "Body is malformed"},
                ]
            },
            [
                FieldError(field="[0].trait_id", message="Not found"),
                FieldError(field="name", message=""),
                FieldError(field="", message="Body is malformed"),
            ],
            id="parameters",
        ),
        pytest.param({}, [], id="no-parameters"),
    ],
)
def test_validation_error_field_errors(response_data: dict, expected: list[FieldError]) -> None:
    """Verify each server invalid parameter becomes one FieldError, field text kept as sent."""
    assert ValidationError("Bad input", 400, response_data).field_errors == expected


class _Item(BaseModel):
    trait_id: str = Field(min_length=3)


class _Payload(BaseModel):
    items: list[_Item]
    name: str

    @field_validator("name")
    @classmethod
    def _no_admin(cls, value: str) -> str:
        if value == "admin":
            msg = "Name is reserved."
            raise ValueError(msg)
        return value


def _request_validation_error() -> RequestValidationError:
    with pytest.raises(PydanticValidationError) as exc_info:
        _Payload(items=[{"trait_id": "x"}], name="admin")
    return RequestValidationError(exc_info.value)


def test_request_validation_error_message_names_each_field() -> None:
    """Verify the message lists every failing location with its reason."""
    error = _request_validation_error()

    assert error.message.startswith("Request validation failed: ")
    assert "items.0.trait_id: String should have at least 3 characters" in error.message
    assert "name: Value error, Name is reserved." in error.message


def test_request_validation_error_field_errors() -> None:
    """Verify a nested location becomes a dotted path without list indexes or validator prefix."""
    fields = {fe.field: fe.message for fe in _request_validation_error().field_errors}

    assert fields["items.trait_id"].startswith("String should have at least 3 characters")
    assert fields["name"] == "Name is reserved."
