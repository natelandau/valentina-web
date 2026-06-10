"""Dictionary term service functions.

Stateless functions for validating and mutating dictionary terms
via the vclient API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from flask import session
from vclient import sync_dictionary_service
from vclient.models import DictionaryTermCreate, DictionaryTermUpdate

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm

TERM_MIN_LENGTH = 3
TERM_MAX_LENGTH = 50


def parse_synonyms(raw: str) -> list[str]:
    """Split a comma-separated string into a list of trimmed, non-empty synonyms.

    Args:
        raw: Comma-separated synonym string from form input.

    Returns:
        List of cleaned synonym strings.
    """
    if not raw or not raw.strip():
        return []

    return [s.strip() for s in raw.split(",") if s.strip()]


def validate_term(form_data: dict[str, str]) -> dict[str, str]:
    """Validate dictionary term form data.

    Args:
        form_data: Form field values keyed by field name.

    Returns:
        Errors keyed by field name (empty if valid).
    """
    errors: dict[str, str] = {}

    term = form_data.get("term", "").strip()
    if not term:
        errors["term"] = "Term name is required"
    elif len(term) < TERM_MIN_LENGTH:
        errors["term"] = f"Term name must be at least {TERM_MIN_LENGTH} characters"
    elif len(term) > TERM_MAX_LENGTH:
        errors["term"] = f"Term name must be {TERM_MAX_LENGTH} characters or fewer"

    link = form_data.get("link", "").strip()
    if link:
        parsed = urlparse(link)
        if not parsed.scheme or not parsed.netloc:
            errors["link"] = "Link must be a valid URL (e.g. https://example.com)"

    return errors


def create_term(form_data: dict[str, str]) -> DictionaryTerm:
    """Create a new dictionary term from form data.

    Args:
        form_data: Form field values keyed by field name.

    Returns:
        The created DictionaryTerm.
    """
    request_body = DictionaryTermCreate(
        term=form_data["term"].strip(),
        definition=form_data.get("definition", "").strip() or None,
        link=form_data.get("link", "").strip() or None,
        synonyms=parse_synonyms(form_data.get("synonyms", "")),
    )
    return sync_dictionary_service(company_id=session["company_id"]).create(request=request_body)


def update_term(term_id: str, form_data: dict[str, str]) -> DictionaryTerm:
    """Update an existing dictionary term from form data.

    Args:
        term_id: The ID of the term to update.
        form_data: Form field values keyed by field name.

    Returns:
        The updated DictionaryTerm.
    """
    request_body = DictionaryTermUpdate(
        term=form_data["term"].strip(),
        definition=form_data.get("definition", "").strip() or None,
        link=form_data.get("link", "").strip() or None,
        synonyms=parse_synonyms(form_data.get("synonyms", "")),
    )
    return sync_dictionary_service(company_id=session["company_id"]).update(
        term_id, request=request_body
    )


def delete_term(term_id: str) -> None:
    """Delete a dictionary term.

    Args:
        term_id: The ID of the term to delete.
    """
    sync_dictionary_service(company_id=session["company_id"]).delete(term_id)
