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

# The API's msgspec constraint messages, rewritten as fragments that follow a field label.
# The bound comes from the API's own message, so no limit is copied here.
_CONSTRAINT_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Expected `(?:int|float)` <= (-?[\d.]+)$"), "must be at most {}"),
    (re.compile(r"^Expected `(?:int|float)` >= (-?[\d.]+)$"), "must be at least {}"),
    (re.compile(r"^Expected `(?:int|float)` < (-?[\d.]+)$"), "must be less than {}"),
    (re.compile(r"^Expected `(?:int|float)` > (-?[\d.]+)$"), "must be greater than {}"),
    (re.compile(r"^Expected `str` of length <= (\d+)$"), "must be at most {} characters"),
    (re.compile(r"^Expected `str` of length >= (\d+)$"), "must be at least {} characters"),
    (re.compile(r"^Expected `array` of length <= (\d+)$"), "must have at most {} items"),
    (re.compile(r"^Expected `array` of length >= (\d+)$"), "must have at least {} items"),
)
_FRAGMENT_PREFIX = "must "


class _Entry(NamedTuple):
    """One field message: ``key`` names the form field, ``name`` the field shown in its label."""

    key: str
    name: str
    message: str


def _clean(message: object) -> str:
    text = str(message or "").strip()
    for pattern, template in _CONSTRAINT_REWRITES:
        if match := pattern.match(text):
            return template.format(match.group(1))
    return text.replace("`", "")


def _is_fragment(message: str) -> bool:
    return message.startswith(_FRAGMENT_PREFIX)


def _sentence(message: str) -> str:
    return message[:1].upper() + message[1:] if _is_fragment(message) else message


def _detail(error: APIError) -> str:
    return _clean(error.detail)


def _label(field: str) -> str:
    text = field.replace("_", " ")
    return text[:1].upper() + text[1:]


def _field_entries(error: Exception) -> list[_Entry]:
    """Return the field messages of a validation-style error, dropping blank messages."""
    entries: list[_Entry]
    if isinstance(error, ValidationError):
        entries = []
        for param in error.invalid_parameters:
            field = str(param.get("field") or "")
            entries.append(_Entry(field, field, _clean(param.get("message"))))
    else:
        details: Iterable[Any] = (
            error.errors if isinstance(error, RequestValidationError) else error.errors()  # ty:ignore[unresolved-attribute]
        )
        entries = []
        for d in details:
            loc = [str(part) for part in d.get("loc") or () if isinstance(part, str)]
            # Pydantic prefixes validator failures with "Value error, ", which is noise to users.
            message = _clean(d.get("msg")).removeprefix("Value error, ").strip()
            # Forms submit top-level fields, so a nested error belongs to its outer field,
            # while the innermost name reads best in a label.
            entries.append(_Entry(loc[0] if loc else "", loc[-1] if loc else "", message))
    return [entry for entry in entries if entry.message]


def _format_entry(
    entry: _Entry, *, detail: str = "", labels: Mapping[str, str] | None = None
) -> str:
    """Join a field message to its label.

    The label is dropped for a request-body message and for a full sentence that repeats
    the error's detail, since the API already wrote that sentence for users. A fragment
    such as "must be at most 5" always keeps its label so it still names the field.
    """
    message = entry.message
    if entry.key in _PAYLOAD_FIELDS or (message == detail and not _is_fragment(message)):
        return _sentence(message)
    label = (labels or {}).get(entry.key) or _label(entry.name)
    separator = " " if _is_fragment(message) else ": "
    return f"{label}{separator}{message}"


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
            return [_sentence(detail)]
        return messages
    if isinstance(error, (AuthorizationError, ConflictError, NotFoundError)):
        detail = _detail(error)
        return [_sentence(detail)] if detail else []
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
            body_message = body_message or _sentence(entry.message)
        elif inline_fields is None or key in inline_fields:
            errors.setdefault(key or "unknown", _sentence(entry.message))
        else:
            folded.append(_format_entry(entry, detail=detail))

    # A detail outranks a body-level message, and one that repeats a field message would
    # show the same text twice.
    if detail and all(entry.message != detail for entry in entries):
        general = [_sentence(detail), *folded]
    elif body_message:
        general = [body_message, *folded]
    else:
        general = folded
    if general:
        errors[_GENERAL] = " ".join(general)
    return errors or {_GENERAL: api_error_message(error, fallback=fallback)}
