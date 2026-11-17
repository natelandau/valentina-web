"""Pydantic models for User Lookup API responses."""

from pydantic import BaseModel

from vweb.api_client.constants import UserRole


class UserLookupResult(BaseModel):
    """A single result from a cross-company user lookup.

    Each result represents a company where the looked-up person has a user record.
    """

    company_id: str
    company_name: str
    user_id: str
    role: UserRole


__all__ = [
    "UserLookupResult",
]
