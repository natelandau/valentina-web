"""Tests for QuickrollHandler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import QuickrollFactory, Routes, TraitFactory
from vweb.routes.profile.handlers import QuickrollHandler

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture
def handler(app: Flask, fake_vclient) -> Iterator[QuickrollHandler]:
    """Build a handler for user-1 inside a signed-in request, talking to the fake API."""
    with app.test_request_context("/"):
        seed_session()
        yield QuickrollHandler("user-1")


@pytest.mark.parametrize(
    ("trait_ids", "expected_names"),
    [
        (["t1", "t2"], ("Strength", "Brawl")),
        (["t1"], ("Strength", "-")),
        ([], ("-", "-")),
        (["unknown"], ("-", "-")),
    ],
    ids=["two-traits", "one-trait", "no-traits", "unknown-trait"],
)
def test_list_items_resolves_trait_names(
    handler: QuickrollHandler,
    fake_vclient,
    mocker,
    trait_ids: list[str],
    expected_names: tuple[str, str],
) -> None:
    """Verify listed quickrolls show trait names, with a dash for a missing or unknown trait."""
    # Given a quickroll and the blueprint traits
    qr = QuickrollFactory.build(name="Attack", description="Quick attack", trait_ids=trait_ids)
    fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[qr])
    mocker.patch(
        "vweb.lib.cache.blueprint.traits",
        return_value={
            "t1": TraitFactory.build(id="t1", name="Strength"),
            "t2": TraitFactory.build(id="t2", name="Brawl"),
        },
    )

    # When listing the user's quickrolls
    (item,) = handler.list_items()

    # Then the user's quickrolls are fetched and trait names resolved
    fake_vclient.assert_called(Routes.USERS_QUICKROLLS_LIST, params={"user_id": "user-1"})
    assert (item.name, item.description) == ("Attack", "Quick attack")
    assert (item.trait_one_name, item.trait_two_name) == expected_names


@pytest.mark.parametrize(
    ("form", "expected_json"),
    [
        (
            {
                "name": "  Attack Roll  ",
                "description": "  Quick attack  ",
                "trait_one_id": "t1",
                "trait_two_id": "t2",
            },
            {"name": "Attack Roll", "description": "Quick attack", "trait_ids": ["t1", "t2"]},
        ),
        (
            {"name": "Roll", "description": "", "trait_one_id": "t1", "trait_two_id": ""},
            {"name": "Roll", "trait_ids": ["t1"]},
        ),
    ],
    ids=["full-form-stripped", "blanks-omitted"],
)
def test_create_item_sends_cleaned_form(
    handler: QuickrollHandler, fake_vclient, form: dict[str, str], expected_json: dict
) -> None:
    """Verify create strips values and leaves out a blank description and blank traits."""
    handler.create_item(form)

    fake_vclient.assert_called(
        Routes.USERS_QUICKROLLS_CREATE,
        params={"user_id": "user-1"},
        json=expected_json,
        times=1,
    )


@pytest.mark.parametrize(
    ("form", "expected_subset"),
    [
        (
            {
                "name": "Updated",
                "description": "New desc",
                "trait_one_id": "t3",
                "trait_two_id": "t4",
            },
            {"name": "Updated", "description": "New desc", "trait_ids": ["t3", "t4"]},
        ),
        (
            {"name": "Updated", "description": "   ", "trait_one_id": "t3"},
            {"description": "", "trait_ids": ["t3"]},
        ),
    ],
    ids=["full-form", "blank-description-clears"],
)
def test_update_item_sends_form(
    handler: QuickrollHandler, fake_vclient, form: dict[str, str], expected_subset: dict
) -> None:
    """Verify update sends the form to the quickroll, with a blank description clearing it."""
    handler.update_item("qr-1", form)

    fake_vclient.assert_called(
        Routes.USERS_QUICKROLLS_UPDATE,
        params={"user_id": "user-1", "quickroll_id": "qr-1"},
        json_subset=expected_subset,
        times=1,
    )


def test_get_item_fetches_users_quickroll(handler: QuickrollHandler, fake_vclient) -> None:
    """Verify get_item fetches the quickroll from the user's quickrolls."""
    handler.get_item("qr-1")

    fake_vclient.assert_called(
        Routes.USERS_QUICKROLLS_GET,
        params={"user_id": "user-1", "quickroll_id": "qr-1"},
        times=1,
    )


@pytest.mark.parametrize(
    ("form", "error_keys"),
    [
        ({"name": "Attack Roll", "trait_one_id": "trait-1"}, set()),
        ({"name": "", "trait_one_id": "t1"}, {"name"}),
        ({"name": "   ", "trait_two_id": "t2"}, {"name"}),
        ({"name": "Attack Roll"}, {"_general"}),
        ({"name": "", "trait_one_id": " "}, {"name", "_general"}),
    ],
    ids=["valid", "empty-name", "blank-name", "no-traits", "nothing"],
)
def test_validate(handler: QuickrollHandler, form: dict[str, str], error_keys: set[str]) -> None:
    """Verify a quickroll needs a name and at least one trait."""
    assert set(handler.validate(form)) == error_keys
