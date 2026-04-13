"""Service-layer helpers for the admin user-management page.

Thin wrappers around `sync_users_service()` that the views call. Mutating helpers
clear the global context cache after success because `GlobalContext.users` is cached
at the company level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import session
from vclient import sync_users_service

from vweb.lib.global_context import clear_global_context_cache

if TYPE_CHECKING:
    from vclient.models import User


def list_pending_and_approved(
    requesting_user_id: str,
) -> tuple[list[User], list[User]]:
    """Return pending and approved users for the current company.

    Excludes the requesting admin from both lists so the user-management UI never
    presents an admin's own row (the admin cannot demote or merge themselves).
    The admin-only unapproved endpoint requires ``requesting_user_id`` for its
    permission gate.
    """
    svc = sync_users_service(company_id=session["company_id"])
    pending = [u for u in svc.list_all_unapproved(requesting_user_id) if u.id != requesting_user_id]
    approved = [u for u in svc.list_all() if u.id != requesting_user_id]
    return pending, approved


def pending_user_count(requesting_user_id: str) -> int:
    """Return the number of pending (UNAPPROVED) users for the current company.

    Drives the warning badge on the settings tabs. Uncached because admin-page
    traffic is low; if that changes, add a short-TTL cache key.
    """
    return len(
        sync_users_service(company_id=session["company_id"]).list_all_unapproved(requesting_user_id)
    )


def approve(user_id: str, role: str, requesting_user_id: str) -> User:
    """Approve a pending user and assign them a real role.

    Reject UNAPPROVED so the UI cannot accidentally re-pend a user via this code path.
    """
    if role == "UNAPPROVED":
        msg = "Cannot approve with role UNAPPROVED."
        raise ValueError(msg)
    user = sync_users_service(company_id=session["company_id"]).approve_user(
        user_id,
        role,  # ty:ignore[invalid-argument-type]
        requesting_user_id,
    )
    clear_global_context_cache(session["company_id"], session["user_id"])
    return user


def change_role(user_id: str, role: str, requesting_user_id: str) -> User:
    """Change an approved user's role.

    Refuse UNAPPROVED so this code path cannot accidentally deactivate a user.
    Deactivation is intentionally out of scope until the API exposes a real
    DEACTIVATED state.
    """
    if role == "UNAPPROVED":
        msg = "Cannot change role to UNAPPROVED."
        raise ValueError(msg)
    user = sync_users_service(company_id=session["company_id"]).update(
        user_id, requesting_user_id=requesting_user_id, role=role
    )
    clear_global_context_cache(session["company_id"], session["user_id"])
    return user


def deny(user_id: str, requesting_user_id: str) -> None:
    """Deny a pending user so they can no longer access the company."""
    sync_users_service(company_id=session["company_id"]).deny_user(user_id, requesting_user_id)
    clear_global_context_cache(session["company_id"], session["user_id"])


def merge(
    primary_user_id: str,
    secondary_user_id: str,
    requesting_user_id: str,
) -> User:
    """Merge a pending user into an existing primary user via users_svc.merge."""
    user = sync_users_service(company_id=session["company_id"]).merge(
        primary_user_id=primary_user_id,
        secondary_user_id=secondary_user_id,
        requesting_user_id=requesting_user_id,
    )
    clear_global_context_cache(session["company_id"], session["user_id"])
    return user
