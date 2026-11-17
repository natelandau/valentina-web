"""Form checks shared by the book, chapter, campaign, and character views."""

from __future__ import annotations

from datetime import date

from vweb.api_client.constants import MAX_NAME_LENGTH

NAME_MAX_LENGTH = MAX_NAME_LENGTH
CAMPAIGN_NAME_MIN_LENGTH = 3


def name_errors(name: str, *, min_length: int = 1, max_length: int = NAME_MAX_LENGTH) -> list[str]:
    """Check a submitted name against the API's length limits.

    Use it before a create or update call so an invalid name re-renders the form with a
    readable message instead of failing in the API client.

    Args:
        name: The submitted name, stripped.
        min_length: The shortest name the API accepts.
        max_length: The longest name the API accepts.

    Returns:
        One message when the name is invalid, empty when it is valid.
    """
    if not name:
        return ["Name is required"]
    if len(name) < min_length:
        return [f"Name must be at least {min_length} characters"]
    if len(name) > max_length:
        return [f"Name must be {max_length} characters or fewer"]
    return []


def position_number(submitted: str, current: int) -> tuple[int, str | None]:
    """Parse a submitted book or chapter number, keeping the current one when blank.

    Use it before renumbering so a value the API would reject shows as a form error
    instead of failing after other fields were already saved.

    Args:
        submitted: The submitted number, stripped.
        current: The saved number.

    Returns:
        The number to save and an error message, or None when the number is valid.
    """
    if not submitted:
        return current, None
    try:
        number = int(submitted)
    except ValueError:
        return current, "Number must be a valid integer"
    if number < 1:
        return current, "Number must be 1 or greater"
    return number, None


def parse_form_date(value: str) -> date | None:
    """Parse a date input's ``YYYY-MM-DD`` value.

    Args:
        value: The submitted text, stripped.

    Returns:
        The date, or None when the text is blank or not a valid calendar date.
    """
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
