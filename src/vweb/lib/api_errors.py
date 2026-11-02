"""Turn vclient and validation errors into text that is safe to show users.

Only errors whose text the API or pydantic wrote for end users are surfaced. Server
errors and unclassified API errors can carry internals, so they yield no messages and
callers show a generic fallback instead.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import ValidationError as PydanticValidationError
from vclient.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    RequestValidationError,
    ValidationError,
)

from vweb.constants import MAX_IMAGE_SIZE_MB

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping

logger = logging.getLogger(__name__)

# NotFoundError is included so a stale page acting on an already-deleted object
# surfaces a message instead of a 500.
USER_FACING_API_ERRORS: tuple[type[Exception], ...] = (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
    RequestValidationError,
    PydanticValidationError,
)

_PAYLOAD_FIELDS = frozenset({"body", ""})
_HTTP_PAYLOAD_TOO_LARGE = 413
_GENERAL = "_general"
_PATH_SEGMENT = re.compile(r"[.\[\]]+")


class _Entry(NamedTuple):
    """One field message: ``key`` names the form field, ``name`` the field shown in its label."""

    key: str
    name: str
    message: str


def _text(message: object) -> str:
    return str(message or "").strip()


def _detail(error: APIError) -> str:
    return _text(error.detail)


def _label(field: str) -> str:
    # A nested path such as "[0].trait_id" or "tags[2]" reads best as its innermost
    # named field; list indexes name no field.
    names = [part for part in _PATH_SEGMENT.split(field) if part and not part.isdigit()]
    text = names[-1].replace("_", " ") if names else ""
    return text[:1].upper() + text[1:]


def _field_entries(error: Exception) -> list[_Entry]:
    """Return the field messages of a validation-style error, dropping blank messages."""
    entries: list[_Entry]
    if isinstance(error, ValidationError):
        entries = []
        for param in error.invalid_parameters:
            field = str(param.get("field") or "")
            entries.append(_Entry(field, field, _text(param.get("message"))))
    else:
        details: Iterable[Any] = (
            error.errors if isinstance(error, RequestValidationError) else error.errors()  # ty:ignore[unresolved-attribute]
        )
        entries = []
        for d in details:
            loc = [str(part) for part in d.get("loc") or () if isinstance(part, str)]
            # Pydantic prefixes validator failures with "Value error, ", which is noise to users.
            message = _text(d.get("msg")).removeprefix("Value error, ").strip()
            # Forms submit top-level fields, so a nested error belongs to its outer field,
            # while the innermost name reads best in a label.
            entries.append(_Entry(loc[0] if loc else "", loc[-1] if loc else "", message))
    return [entry for entry in entries if entry.message]


def _format_entry(
    entry: _Entry, *, detail: str = "", labels: Mapping[str, str] | None = None
) -> str:
    """Join a field message to its label.

    The label is dropped for a request-body message and for a message that repeats the
    error's detail, since the API already wrote that sentence for users.
    """
    message = entry.message
    if entry.key in _PAYLOAD_FIELDS or message == detail:
        return message
    label = (labels or {}).get(entry.key) or _label(entry.name)
    return f"{label}: {message}" if label else message


def _rate_limit_message(error: RateLimitError) -> str | None:
    seconds = error.retry_after
    if seconds is None:
        return None
    unit = "second" if seconds == 1 else "seconds"
    return f"Too many requests. Please wait {seconds} {unit} and try again."


def api_error_messages(error: Exception, *, labels: Mapping[str, str] | None = None) -> list[str]:
    """List the messages from an error that are safe to show to a user.

    Args:
        error: The exception raised by a vclient call or pydantic validation.
        labels: Labels that replace the default label for the named fields.

    Returns:
        User-facing messages, empty when the error has nothing safe to show.
    """
    if isinstance(error, (ValidationError, RequestValidationError, PydanticValidationError)):
        detail = _detail(error) if isinstance(error, ValidationError) else ""
        messages = [
            _format_entry(entry, detail=detail, labels=labels) for entry in _field_entries(error)
        ]
        if not messages and detail:
            return [detail]
        return messages
    if isinstance(error, (AuthorizationError, ConflictError, NotFoundError)):
        detail = _detail(error)
        return [detail] if detail else []
    if isinstance(error, RateLimitError):
        message = _rate_limit_message(error)
        return [message] if message else []
    if isinstance(error, APIError) and error.status_code == _HTTP_PAYLOAD_TOO_LARGE:
        return [f"Upload is too large (max {MAX_IMAGE_SIZE_MB} MB)."]
    return []


def api_error_message(
    error: Exception, *, fallback: str, labels: Mapping[str, str] | None = None
) -> str:
    """Join an error's user-facing messages into one string.

    Args:
        error: The exception raised by a vclient call or pydantic validation.
        fallback: Text to show when the error has nothing safe to show.
        labels: Labels that replace the default label for the named fields.

    Returns:
        The messages joined with a space, or ``fallback`` (the error is logged).
    """
    messages = api_error_messages(error, labels=labels)
    if messages:
        return " ".join(messages)
    # Rejected credentials and rate limits are expected operating conditions, not bugs.
    level = (
        logging.WARNING
        if isinstance(error, (AuthenticationError, RateLimitError))
        else logging.ERROR
    )
    logger.log(level, "API error shown as fallback", exc_info=error)
    return fallback


def api_field_errors(
    error: Exception,
    *,
    fallback: str,
    inline_fields: Collection[str] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Map an error to form field messages.

    Args:
        error: The exception raised by a vclient call or pydantic validation.
        fallback: Text for ``_general`` when the error has nothing safe to show.
        inline_fields: The fields the form shows messages beside. Messages for other
            fields are folded, labeled, into ``_general``. None keeps every field.
        aliases: API field names mapped to the form field that submitted them, applied
            before the inline check.

    Returns:
        Field name to message, with ``_general`` for a detail, folded messages, or the
        fallback.
    """
    if not isinstance(error, (ValidationError, RequestValidationError, PydanticValidationError)):
        return {_GENERAL: api_error_message(error, fallback=fallback)}

    entries = _field_entries(error)
    detail = _detail(error) if isinstance(error, ValidationError) else ""
    errors: dict[str, str] = {}
    folded: list[str] = []
    body_message: str | None = None
    for entry in entries:
        key = (aliases or {}).get(entry.key, entry.key)
        if key in _PAYLOAD_FIELDS:
            body_message = body_message or entry.message
        elif inline_fields is None or key in inline_fields:
            errors.setdefault(key, entry.message)
        else:
            folded.append(_format_entry(entry, detail=detail))

    # A detail outranks a body-level message, and one that repeats a field message would
    # show the same text twice.
    if detail and all(entry.message != detail for entry in entries):
        general = [detail, *folded]
    elif body_message:
        general = [body_message, *folded]
    else:
        general = folded
    if general:
        errors[_GENERAL] = " ".join(general)
    return errors or {_GENERAL: api_error_message(error, fallback=fallback)}
