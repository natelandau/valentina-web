"""Tests for the request-scoped API service accessors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from flask import session

from tests.helpers import seed_session
from vweb.api_client.constants import ON_BEHALF_OF_HEADER
from vweb.lib import api_services
from vweb.lib.api_services import NoRequestScopeError

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask

    from vweb.api_client.services.base import BaseService

USER_SCOPED: list[tuple[str, Callable[[], Any], tuple[str, ...]]] = [
    ("users", api_services.users, ()),
    ("campaigns", api_services.campaigns, ()),
    ("books", lambda: api_services.books("camp-1"), ("camp-1",)),
    ("chapters", lambda: api_services.chapters("camp-1", "book-1"), ("camp-1", "book-1")),
    ("characters", api_services.characters, ()),
    ("character_traits", lambda: api_services.character_traits("char-1"), ("char-1",)),
    ("dicerolls", api_services.dicerolls, ()),
    ("character_autogen", api_services.character_autogen, ()),
]

COMPANY_SCOPED: list[tuple[str, Callable[[], BaseService], Callable[[Any], object]]] = [
    ("character_blueprint", api_services.character_blueprint, lambda svc: svc.list_all_concepts()),
    ("dictionary", api_services.dictionary, lambda svc: svc.list_all()),
    ("options", api_services.options, lambda svc: svc.get_options()),
]


@pytest.mark.parametrize(
    ("build", "path_ids"), [s[1:] for s in USER_SCOPED], ids=[s[0] for s in USER_SCOPED]
)
def test_user_scoped_service_acts_as_session_user(
    app: Flask,
    fake_vclient,
    build: Callable[[], Any],
    path_ids: tuple[str, ...],
) -> None:
    """Verify each user-scoped accessor calls the session company as the session user."""
    with app.test_request_context():
        seed_session(user_id="u-1", company_id="co-1")

        build().list_all()

    request = fake_vclient.requests[-1]
    assert request.headers.get(ON_BEHALF_OF_HEADER.lower()) == "u-1"
    for expected in ("co-1", *path_ids):
        assert f"/{expected}/" in f"{request.path}/"


@pytest.mark.parametrize(
    ("build", "call"), [s[1:] for s in COMPANY_SCOPED], ids=[s[0] for s in COMPANY_SCOPED]
)
def test_company_scoped_service_sends_no_on_behalf_of(
    app: Flask,
    fake_vclient,
    build: Callable[[], BaseService],
    call: Callable[[Any], object],
) -> None:
    """Verify company-wide accessors call the session company with no On-Behalf-Of user."""
    with app.test_request_context():
        seed_session(user_id="u-1", company_id="co-1")

        call(build())

    request = fake_vclient.requests[-1]
    assert ON_BEHALF_OF_HEADER.lower() not in request.headers
    assert "/co-1/" in request.path


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
