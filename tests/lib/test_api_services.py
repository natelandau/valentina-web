"""Tests for the request-scoped API service accessors."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import session

from tests.helpers import seed_session
from vweb.lib import api_services
from vweb.lib.api_services import NoRequestScopeError

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

    from vweb.api_client.services.base import BaseService

USER_SCOPED: list[tuple[str, Callable[[], BaseService], dict[str, str]]] = [
    ("users", api_services.users, {}),
    ("campaigns", api_services.campaigns, {}),
    ("books", lambda: api_services.books("camp-1"), {"campaign_id": "camp-1"}),
    (
        "chapters",
        lambda: api_services.chapters("camp-1", "book-1"),
        {"campaign_id": "camp-1", "book_id": "book-1"},
    ),
    ("characters", api_services.characters, {}),
    (
        "character_traits",
        lambda: api_services.character_traits("char-1"),
        {"character_id": "char-1"},
    ),
    ("dicerolls", api_services.dicerolls, {}),
    ("character_autogen", api_services.character_autogen, {}),
]

COMPANY_SCOPED: list[tuple[str, Callable[[], BaseService]]] = [
    ("character_blueprint", api_services.character_blueprint),
    ("dictionary", api_services.dictionary),
    ("options", api_services.options),
]


@pytest.mark.parametrize(
    ("build", "scope"), [s[1:] for s in USER_SCOPED], ids=[s[0] for s in USER_SCOPED]
)
def test_user_scoped_service_uses_session_company_and_user(
    app: Flask,
    fake_vclient,
    build: Callable[[], BaseService],
    scope: dict[str, str],
) -> None:
    """Verify each user-scoped accessor acts as the session user in the session company."""
    with app.test_request_context():
        seed_session(user_id="u-1", company_id="co-1")

        svc = build()

    assert svc._on_behalf_of == "u-1"
    assert svc._scope == {"company_id": "co-1", **scope}


@pytest.mark.parametrize(
    "build", [s[1] for s in COMPANY_SCOPED], ids=[s[0] for s in COMPANY_SCOPED]
)
def test_company_scoped_service_sends_no_on_behalf_of(
    app: Flask,
    fake_vclient,
    build: Callable[[], BaseService],
) -> None:
    """Verify company-wide accessors use the session company and send no On-Behalf-Of user."""
    with app.test_request_context():
        seed_session(user_id="u-1", company_id="co-1")

        svc = build()

    assert svc._on_behalf_of is None
    assert svc._scope == {"company_id": "co-1"}


@pytest.mark.parametrize("build", [s[1] for s in USER_SCOPED], ids=[s[0] for s in USER_SCOPED])
def test_user_scoped_service_raises_without_signed_in_user(
    app: Flask,
    fake_vclient,
    build: Callable[[], BaseService],
) -> None:
    """Verify a user-scoped accessor refuses to build a service with no session user."""
    with app.test_request_context():
        session["company_id"] = "co-1"

        with pytest.raises(NoRequestScopeError, match="signed-in user"):
            build()


@pytest.mark.parametrize(
    "build",
    [s[1] for s in USER_SCOPED] + [s[1] for s in COMPANY_SCOPED],
    ids=[s[0] for s in USER_SCOPED] + [s[0] for s in COMPANY_SCOPED],
)
def test_service_raises_without_company(
    app: Flask,
    fake_vclient,
    build: Callable[[], BaseService],
) -> None:
    """Verify every accessor refuses to build a service with no session company."""
    with app.test_request_context():
        session["user_id"] = "u-1"

        with pytest.raises(NoRequestScopeError, match="No company"):
            build()
