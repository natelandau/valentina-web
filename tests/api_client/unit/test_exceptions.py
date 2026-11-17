"""Tests for vweb.api_client.api.exceptions."""

import pytest
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    FieldError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    RequestValidationError,
    ServerError,
    UnprocessableEntityError,
    ValidationError,
)


class TestAPIError:
    """Tests for APIError base class."""

    def test_init_with_message_only(self):
        """Verify creating an error with just a message."""
        # When: Creating an error with message only
        error = APIError("Something went wrong")

        # Then: Message is set and defaults are applied
        assert error.message == "Something went wrong"
        assert error.status_code is None
        assert error.response_data == {}

    def test_init_with_all_params(self):
        """Verify creating an error with all parameters."""
        # When: Creating an error with all parameters
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={"detail": "Resource not found"},
        )

        # Then: All values are stored
        assert error.message == "Not found"
        assert error.status_code == 404
        assert error.response_data == {"detail": "Resource not found"}

    def test_str_with_status_code(self):
        """Verify string representation includes status code."""
        # Given: An error with status code
        error = APIError("Bad request", status_code=400)

        # When/Then: String representation includes status code
        assert str(error) == "[400] Bad request"

    def test_str_without_status_code(self):
        """Verify string representation without status code."""
        # Given: An error without status code
        error = APIError("Unknown error")

        # When/Then: String representation is just the message
        assert str(error) == "Unknown error"

    def test_is_exception(self):
        """Verify APIError is a proper exception."""
        # Given: An error message
        msg = "Test error"

        # When/Then: Error can be raised and caught
        with pytest.raises(APIError) as exc_info:
            raise APIError(msg, status_code=500)

        assert exc_info.value.status_code == 500

    def test_str_with_rfc9457_full_context(self):
        """Verify string representation includes full RFC 9457 context."""
        # Given: An error with full RFC 9457 response data
        error = APIError(
            message="Company 'abc123' not found",
            status_code=404,
            response_data={
                "status": 404,
                "title": "Not Found",
                "detail": "Company 'abc123' not found",
                "instance": "/api/v1/companies/abc123",
            },
        )

        # When/Then: String representation includes title and instance
        result = str(error)
        assert "[404] Not Found" in result
        assert "Instance: /api/v1/companies/abc123" in result

    def test_str_includes_detail_when_different_from_title(self):
        """Verify string includes detail when it differs from title."""
        # Given: An error where detail differs from title
        error = APIError(
            message="Resource not found",
            status_code=404,
            response_data={
                "title": "Not Found",
                "detail": "The company with ID 'xyz789' does not exist",
                "instance": "/api/v1/companies/xyz789",
            },
        )

        # When/Then: String includes the distinct detail
        result = str(error)
        assert "Detail: The company with ID 'xyz789' does not exist" in result

    def test_str_omits_detail_when_same_as_message(self):
        """Verify string omits detail when identical to message."""
        # Given: An error where detail equals message
        error = APIError(
            message="Resource not found",
            status_code=404,
            response_data={
                "title": "Not Found",
                "detail": "Resource not found",
            },
        )

        # When/Then: String does not repeat the detail
        result = str(error)
        assert "Detail:" not in result

    def test_str_handles_empty_response_data(self):
        """Verify string handles empty response_data gracefully."""
        # Given: An error with empty response_data
        error = APIError(message="Error occurred", status_code=500, response_data={})

        # When/Then: String uses message as fallback
        assert str(error) == "[500] Error occurred"

    def test_str_includes_request_id(self):
        """Verify string representation includes request ID when present."""
        # Given: An error with request_id in response data
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={
                "title": "Not Found",
                "detail": "Company not found",
                "instance": "/api/v1/companies/abc123",
                "request_id": "req_abc123xyz",
            },
        )

        # When/Then: String includes Request-ID
        result = str(error)
        assert "Request-ID: req_abc123xyz" in result

    def test_str_omits_request_id_when_absent(self):
        """Verify string representation omits Request-ID when not present."""
        # Given: An error without request_id
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={"title": "Not Found"},
        )

        # When/Then: String does not include Request-ID
        assert "Request-ID" not in str(error)


class TestRFC9457Properties:
    """Tests for RFC 9457 Problem Details properties on APIError."""

    def test_title_property(self):
        """Verify title property extracts from response_data."""
        # Given: An error with RFC 9457 response data
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={
                "status": 404,
                "title": "Not Found",
                "detail": "Company 'abc123' not found",
                "instance": "/api/v1/companies/abc123",
            },
        )

        # Then: Title property returns the correct value
        assert error.title == "Not Found"

    def test_detail_property(self):
        """Verify detail property extracts from response_data."""
        # Given: An error with RFC 9457 response data
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={
                "status": 404,
                "title": "Not Found",
                "detail": "Company 'abc123' not found",
                "instance": "/api/v1/companies/abc123",
            },
        )

        # Then: Detail property returns the correct value
        assert error.detail == "Company 'abc123' not found"

    def test_instance_property(self):
        """Verify instance property extracts from response_data."""
        # Given: An error with RFC 9457 response data
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={
                "status": 404,
                "title": "Not Found",
                "detail": "Company 'abc123' not found",
                "instance": "/api/v1/companies/abc123",
            },
        )

        # Then: Instance property returns the correct value
        assert error.instance == "/api/v1/companies/abc123"

    def test_properties_return_none_when_missing(self):
        """Verify RFC 9457 properties return None when not in response_data."""
        # Given: An error without RFC 9457 fields
        error = APIError(message="Error", status_code=500, response_data={})

        # Then: All RFC 9457 properties return None
        assert error.title is None
        assert error.detail is None
        assert error.instance is None

    def test_request_id_property(self):
        """Verify request_id property extracts from response_data."""
        # Given: An error with request_id in response data
        error = APIError(
            message="Not found",
            status_code=404,
            response_data={
                "status": 404,
                "title": "Not Found",
                "detail": "Company 'abc123' not found",
                "instance": "/api/v1/companies/abc123",
                "request_id": "req_7H2kB9xQ4mN1pL5w3nR2Yg",
            },
        )

        # Then: request_id property returns the correct value
        assert error.request_id == "req_7H2kB9xQ4mN1pL5w3nR2Yg"

    def test_request_id_returns_none_when_missing(self):
        """Verify request_id returns None when not in response_data."""
        # Given: An error without request_id
        error = APIError(message="Error", status_code=500, response_data={})

        # Then: request_id returns None
        assert error.request_id is None


class TestValidationError:
    """Tests for ValidationError class."""

    def test_invalid_parameters_property(self):
        """Verify invalid_parameters extracts validation errors from response_data."""
        # Given: A validation error with invalid_parameters
        error = ValidationError(
            message="Validation failed",
            status_code=400,
            response_data={
                "status": 400,
                "title": "Bad Request",
                "detail": "Validation failed for one or more fields.",
                "instance": "/api/v1/companies/abc123/users",
                "invalid_parameters": [
                    {"field": "name", "message": "Field required"},
                    {
                        "field": "role",
                        "message": "Input should be 'ADMIN', 'STORYTELLER' or 'PLAYER'",
                    },
                ],
            },
        )

        # Then: invalid_parameters property returns the list
        assert len(error.invalid_parameters) == 2
        assert error.invalid_parameters[0]["field"] == "name"
        assert error.invalid_parameters[0]["message"] == "Field required"
        assert error.invalid_parameters[1]["field"] == "role"

    def test_invalid_parameters_returns_empty_list_when_missing(self):
        """Verify invalid_parameters returns empty list when not in response_data."""
        # Given: A validation error without invalid_parameters
        error = ValidationError(
            message="Validation failed",
            status_code=400,
            response_data={"detail": "Validation failed"},
        )

        # Then: invalid_parameters returns empty list
        assert error.invalid_parameters == []

    def test_str_includes_field_errors(self):
        """Verify string representation includes validation field errors."""
        # Given: A validation error with invalid_parameters
        error = ValidationError(
            message="Validation failed",
            status_code=400,
            response_data={
                "status": 400,
                "title": "Bad Request",
                "detail": "Validation failed for one or more fields.",
                "invalid_parameters": [
                    {"field": "name", "message": "Field required"},
                    {"field": "role", "message": "Invalid value"},
                ],
            },
        )

        # When/Then: String includes field errors
        result = str(error)
        assert "[400] Bad Request" in result
        assert "Fields:" in result
        assert "name: Field required" in result
        assert "role: Invalid value" in result

    def test_str_without_invalid_parameters(self):
        """Verify string representation works without invalid_parameters."""
        # Given: A validation error without invalid_parameters
        error = ValidationError(
            message="Validation failed",
            status_code=400,
            response_data={"title": "Bad Request"},
        )

        # When/Then: String does not include Fields section
        result = str(error)
        assert "Fields:" not in result


class TestRequestValidationError:
    """Tests for RequestValidationError class."""

    def test_wraps_pydantic_error(self):
        """Verify RequestValidationError wraps Pydantic ValidationError."""

        # Given: A Pydantic model with validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)

        # When: Validation fails and we wrap the error
        try:
            TestModel(name="ab")
        except PydanticValidationError as e:
            error = RequestValidationError(e)

        # Then: The error is properly wrapped
        assert isinstance(error, RequestValidationError)
        assert isinstance(error, APIError)

    def test_errors_property_returns_pydantic_errors(self):
        """Verify errors property returns structured error list from Pydantic."""

        # Given: A Pydantic model with multiple validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)
            age: int = Field(gt=0)

        # When: Multiple validation errors occur
        try:
            TestModel(name="ab", age=-1)
        except PydanticValidationError as e:
            error = RequestValidationError(e)

        # Then: The errors property returns all Pydantic errors
        errors = error.errors
        assert len(errors) == 2
        assert any(err["loc"] == ("name",) for err in errors)
        assert any(err["loc"] == ("age",) for err in errors)

    def test_message_includes_field_details(self):
        """Verify message includes field names and error descriptions."""

        # Given: A Pydantic model with validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)
            email: str = Field(min_length=5)

        # When: Multiple validation errors occur
        try:
            TestModel(name="ab", email="a")
        except PydanticValidationError as e:
            error = RequestValidationError(e)

        # Then: The message includes field names and error details
        assert "Request validation failed" in error.message
        assert "name:" in error.message
        assert "email:" in error.message
        assert "at least 3 characters" in error.message
        assert "at least 5 characters" in error.message

    def test_inherits_from_api_error(self):
        """Verify RequestValidationError inherits from APIError."""
        # When/Then: RequestValidationError is a subclass of APIError
        assert issubclass(RequestValidationError, APIError)

    def test_no_status_code(self):
        """Verify status_code is None for client-side validation."""

        # Given: A Pydantic model with validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)

        # When: Validation fails
        try:
            TestModel(name="ab")
        except PydanticValidationError as e:
            error = RequestValidationError(e)

        # Then: status_code is None (client-side, not HTTP response)
        assert error.status_code is None

    def test_can_be_raised_and_caught(self):
        """Verify RequestValidationError can be raised and caught."""

        # Given: A Pydantic model with validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)

        # When: Creating a RequestValidationError from Pydantic error
        pydantic_error = None
        try:
            TestModel(name="ab")
        except PydanticValidationError as e:
            pydantic_error = e

        # Then: RequestValidationError can be raised and caught
        with pytest.raises(RequestValidationError) as exc_info:
            raise RequestValidationError(pydantic_error)  # ty:ignore[invalid-argument-type]

        assert "Request validation failed" in str(exc_info.value)

    def test_can_be_caught_as_api_error(self):
        """Verify RequestValidationError can be caught as APIError."""

        # Given: A Pydantic model with validation constraints
        class TestModel(BaseModel):
            name: str = Field(min_length=3)

        # When: Creating a RequestValidationError from Pydantic error
        pydantic_error = None
        try:
            TestModel(name="ab")
        except PydanticValidationError as e:
            pydantic_error = e

        # Then: RequestValidationError can be caught as APIError
        with pytest.raises(APIError):
            raise RequestValidationError(pydantic_error)  # ty:ignore[invalid-argument-type]


class TestRateLimitError:
    """Tests for RateLimitError class."""

    def test_retry_after_property(self):
        """Verify retry_after property returns the value passed to constructor."""
        # Given: A rate limit error with retry_after
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={"detail": "You are being rate limited."},
            retry_after=60,
        )

        # Then: retry_after property returns the correct value
        assert error.retry_after == 60

    def test_retry_after_is_none_when_not_provided(self):
        """Verify retry_after is None when not provided."""
        # Given: A rate limit error without retry_after
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={"detail": "You are being rate limited."},
        )

        # Then: retry_after is None
        assert error.retry_after is None

    def test_remaining_property(self):
        """Verify remaining property returns the value passed to constructor."""
        # Given: A rate limit error with remaining tokens
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={"detail": "You are being rate limited."},
            retry_after=5,
            remaining=0,
        )

        # Then: remaining property returns the correct value
        assert error.remaining == 0

    def test_remaining_is_none_when_not_provided(self):
        """Verify remaining is None when not provided."""
        # Given: A rate limit error without remaining
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={"detail": "You are being rate limited."},
        )

        # Then: remaining is None
        assert error.remaining is None

    def test_inherits_rfc9457_properties(self):
        """Verify RateLimitError inherits RFC 9457 properties from APIError."""
        # Given: A rate limit error with full RFC 9457 response
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={
                "status": 429,
                "title": "Too Many Requests",
                "detail": "You are being rate limited.",
                "instance": "/api/v1/companies",
            },
            retry_after=30,
            remaining=0,
        )

        # Then: All properties are accessible
        assert error.title == "Too Many Requests"
        assert error.detail == "You are being rate limited."
        assert error.instance == "/api/v1/companies"
        assert error.retry_after == 30
        assert error.remaining == 0

    def test_str_includes_retry_timing(self):
        """Verify string representation includes retry timing information."""
        # Given: A rate limit error with retry_after and remaining
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={
                "title": "Too Many Requests",
                "detail": "You are being rate limited.",
            },
            retry_after=60,
            remaining=0,
        )

        # When/Then: String includes retry timing
        result = str(error)
        assert "[429] Too Many Requests" in result
        assert "retry_after=60s" in result
        assert "remaining=0" in result

    def test_str_without_retry_info(self):
        """Verify string representation works without retry info."""
        # Given: A rate limit error without retry_after/remaining
        error = RateLimitError(
            message="Too many requests",
            status_code=429,
            response_data={"title": "Too Many Requests"},
        )

        # When/Then: String does not include retry timing section
        result = str(error)
        assert "retry_after=" not in result
        assert "remaining=" not in result


class TestSpecificErrors:
    """Tests for specific error subclasses."""

    @pytest.mark.parametrize(
        ("error_class", "expected_parent"),
        [
            (AuthenticationError, APIError),
            (AuthorizationError, APIError),
            (NotFoundError, APIError),
            (ConflictError, APIError),
            (ValidationError, APIError),
            (RequestValidationError, APIError),
            (RateLimitError, APIError),
            (ServerError, APIError),
        ],
    )
    def test_inheritance(self, error_class, expected_parent):
        """Verify all error classes inherit from APIError."""
        # When/Then: Error class is a subclass of expected parent
        assert issubclass(error_class, expected_parent)

    @pytest.mark.parametrize(
        ("error_class", "message"),
        [
            (AuthenticationError, "Invalid API key"),
            (AuthorizationError, "Permission denied"),
            (NotFoundError, "Resource not found"),
            (ConflictError, "Idempotency key conflict"),
            (ValidationError, "Invalid input"),
            (ServerError, "Internal server error"),
        ],
    )
    def test_can_raise_and_catch(self, error_class, message):
        """Verify specific errors can be raised and caught."""
        # When/Then: Specific error can be raised and caught
        with pytest.raises(error_class) as exc_info:
            raise error_class(message, status_code=400)

        assert message in str(exc_info.value)

    def test_can_raise_and_catch_rate_limit_error(self):
        """Verify RateLimitError can be raised and caught with retry_after."""
        # Given: Error message and parameters
        msg = "Too many requests"

        # When/Then: RateLimitError can be raised with retry_after
        with pytest.raises(RateLimitError) as exc_info:
            raise RateLimitError(msg, status_code=429, retry_after=60)

        assert msg in str(exc_info.value)
        assert exc_info.value.retry_after == 60

    def test_catch_specific_error_as_api_error(self):
        """Verify specific errors can be caught as APIError."""
        # Given: A specific error type
        msg = "Not found"

        # When/Then: Specific error can be caught as base APIError
        with pytest.raises(APIError):
            raise NotFoundError(msg, status_code=404)


class TestUnprocessableEntityError:
    """Tests for UnprocessableEntityError."""

    def test_init_with_response_data(self):
        """Verify creating a 422 error exposes the machine-readable code."""
        # When: Creating an error from a 422 problem-details response
        error = UnprocessableEntityError(
            message="Provider token failed verification",
            status_code=422,
            response_data={
                "detail": "Provider token failed verification",
                "code": "TOKEN_VERIFICATION_FAILED",
            },
        )

        # Then: Status code and code extension are exposed
        assert error.status_code == 422
        assert error.code == "TOKEN_VERIFICATION_FAILED"
        assert isinstance(error, APIError)


class TestAPIErrorCodeProperty:
    """Tests for the APIError.code extension property."""

    def test_code_present(self):
        """Verify code returns the machine-readable extension when present."""
        # When: Creating an error whose response includes a code extension
        error = ConflictError(
            message="Identity already linked",
            status_code=409,
            response_data={"code": "IDENTITY_ALREADY_LINKED"},
        )

        # Then: The code is exposed
        assert error.code == "IDENTITY_ALREADY_LINKED"

    def test_code_absent(self):
        """Verify code returns None when the response has no code extension."""
        # When: Creating an error without a code extension
        error = APIError("Something went wrong", status_code=500, response_data={})

        # Then: The code is None
        assert error.code is None

    def test_str_includes_code(self):
        """Verify the string representation includes the code when present."""
        # When: Formatting an error that carries a code
        error = UnprocessableEntityError(
            message="bad token",
            status_code=422,
            response_data={"detail": "bad token", "code": "TOKEN_VERIFICATION_FAILED"},
        )

        # Then: The code appears in the string output
        assert "Code: TOKEN_VERIFICATION_FAILED" in str(error)


class TestAPIConnectionError:
    """Tests for APIConnectionError."""

    def test_is_an_api_error_without_status(self):
        """Verify a connection error is caught as APIError and reads as its message."""
        # When: Creating a connection error
        error = APIConnectionError("Could not reach the API: Connection refused")

        # Then: It is an APIError with no HTTP status or response body
        assert isinstance(error, APIError)
        assert error.status_code is None
        assert error.response_data == {}
        assert error.detail is None

        # Then: Its text is the message alone
        assert str(error) == "Could not reach the API: Connection refused"


class TestFieldErrors:
    """Tests for the field_errors view on validation exceptions."""

    def test_validation_error_field_errors_from_invalid_parameters(self):
        """Verify server validation parameters become FieldError items."""
        # Given: A 400 with invalid parameters, including blank and missing values
        error = ValidationError(
            "Bad input",
            400,
            {
                "invalid_parameters": [
                    {"field": "[0].trait_id", "message": "  Not found  "},
                    {"field": "name", "message": ""},
                    {"message": "Body is malformed"},
                ]
            },
        )

        # When/Then: Each parameter maps to one field error, field text kept as sent
        assert error.field_errors == [
            FieldError(field="[0].trait_id", message="Not found"),
            FieldError(field="name", message=""),
            FieldError(field="", message="Body is malformed"),
        ]

    def test_validation_error_without_parameters_has_no_field_errors(self):
        """Verify a 400 without invalid parameters has an empty list."""
        # Given/When/Then: A bare validation error has no field errors
        assert ValidationError("Bad input", 400, {}).field_errors == []

    def test_request_validation_error_joins_named_location_parts(self):
        """Verify a nested pydantic location becomes a dotted path without list indexes."""

        # Given: A model with a nested list field and a custom validator
        class Item(BaseModel):
            trait_id: str = Field(min_length=3)

        class Payload(BaseModel):
            items: list[Item]
            name: str

            @field_validator("name")
            @classmethod
            def _no_admin(cls, value: str) -> str:
                if value == "admin":
                    msg = "Name is reserved."
                    raise ValueError(msg)
                return value

        with pytest.raises(PydanticValidationError) as exc_info:
            Payload(items=[{"trait_id": "x"}], name="admin")

        # When: Wrapping the pydantic error
        error = RequestValidationError(exc_info.value)

        # Then: Paths skip list indexes and the validator prefix is removed
        fields = {fe.field: fe.message for fe in error.field_errors}
        assert fields["items.trait_id"].startswith("String should have at least 3 characters")
        assert fields["name"] == "Name is reserved."


class TestPayloadTooLargeError:
    """Tests for PayloadTooLargeError."""

    def test_is_an_api_error(self):
        """Verify a 413 error is an APIError carrying its status."""
        # When: Creating the error
        error = PayloadTooLargeError("Request body too large", 413, {})

        # Then: It is an APIError with the 413 status
        assert isinstance(error, APIError)
        assert error.status_code == 413
