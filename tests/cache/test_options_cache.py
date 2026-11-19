"""Tests for global API options cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import session

from vweb.api_client.testing import FakeResponse, Routes
from vweb.lib.cache.options import clear, get, tracker_actions_for

if TYPE_CHECKING:
    from flask import Flask

    from vweb.api_client.testing import FakeVClient

SAMPLE_RAW: dict = {
    "companies": {
        "CompanyPermission": ["USER", "ADMIN", "OWNER"],
        "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
        "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
        "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
    },
    "characters": {
        "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
        "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
        "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
        "CharacterStatus": ["ALIVE", "DEAD"],
        "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
        "GameVersion": ["V4", "V5"],
        "HunterCreed": ["ENTREPRENEURIAL", "FAITHFUL"],
        "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
        "InventoryItemType": ["BOOK", "CONSUMABLE", "ENCHANTED", "EQUIPMENT", "OTHER", "WEAPON"],
        "SpecialtyType": ["ACTION", "OTHER"],
        "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
        "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
        "_related": {"traits": "http://example.com/traits"},
    },
    "users": {
        "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED"],
    },
    "gameplay": {
        "DiceSize": [4, 6, 8, 10, 20, 100],
        "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
    },
}


@pytest.fixture
def fake_options(real_cache_services, fake_vclient: FakeVClient) -> FakeVClient:
    """Serve SAMPLE_RAW from the fake API and route the options cache through it."""
    fake_vclient.set_response(Routes.OPTIONS_GET, model=SAMPLE_RAW)
    return fake_vclient


def _get_for(company_id: str = "test-company-id"):  # noqa: ANN202
    session["company_id"] = company_id
    return get()


def test_get_fetches_once_and_maps_enumerations(
    app: Flask, mock_cache_store: dict, fake_options: FakeVClient
) -> None:
    """Verify the company's options are fetched once and exposed by category."""
    with app.test_request_context("/"):
        first = _get_for()
        second = _get_for()

    assert second is first
    assert first.companies.company_permission == ["USER", "ADMIN", "OWNER"]
    assert first.characters.character_type == ["PLAYER", "NPC", "STORYTELLER"]
    assert first.users.user_role == ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED"]
    assert first.gameplay.dice_size == [4, 6, 8, 10, 20, 100]
    fake_options.assert_called(
        Routes.OPTIONS_GET, params={"company_id": "test-company-id"}, times=1
    )


def test_options_cached_per_company(
    app: Flask, mock_cache_store: dict, fake_options: FakeVClient
) -> None:
    """Verify each company gets its own options."""
    with app.test_request_context("/"):
        _get_for("co-1")
        _get_for("co-2")

    fake_options.assert_called(Routes.OPTIONS_GET, params={"company_id": "co-1"}, times=1)
    fake_options.assert_called(Routes.OPTIONS_GET, params={"company_id": "co-2"}, times=1)


@pytest.mark.parametrize(
    "raw", [{}, {"characters": {"TrackerRules": None}}], ids=["empty", "null-tracker-rules"]
)
def test_missing_sections_read_as_empty(
    app: Flask, mock_cache_store: dict, fake_options: FakeVClient, raw: dict
) -> None:
    """Verify a sparse options payload yields empty choices instead of failing."""
    fake_options.set_response(Routes.OPTIONS_GET, model=raw)

    with app.test_request_context("/"):
        options = _get_for()
        actions = tracker_actions_for("V4", "DAMAGE")

    assert options.characters.character_class == []
    assert options.gameplay.dice_size == []
    assert actions == []


def test_clear_forces_refetch(
    app: Flask, mock_cache_store: dict, fake_options: FakeVClient
) -> None:
    """Verify clear forces a fresh API fetch on next access."""
    raw_v2 = {
        **SAMPLE_RAW,
        "characters": {**SAMPLE_RAW["characters"], "CharacterClass": ["VAMPIRE"]},
    }
    fake_options.set_responses(
        Routes.OPTIONS_GET, [FakeResponse(model=SAMPLE_RAW), FakeResponse(model=raw_v2)]
    )

    with app.test_request_context("/"):
        assert len(_get_for().characters.character_class) == 6

        clear()

        assert _get_for().characters.character_class == ["VAMPIRE"]

    fake_options.assert_called(Routes.OPTIONS_GET, times=2)


@pytest.mark.parametrize(
    ("version", "tracker", "expected"),
    [
        ("V4", "DAMAGE", ["damage", "heal", "reset"]),
        ("V4", "NOT_A_TRACKER", []),
        ("V9", "DAMAGE", []),
    ],
)
def test_tracker_actions_for(
    app: Flask,
    mock_cache_store: dict,
    fake_options: FakeVClient,
    version: str,
    tracker: str,
    expected: list[str],
) -> None:
    """Verify tracker actions come from the API's rules, empty for unknown types or versions."""
    fake_options.set_response(
        Routes.OPTIONS_GET,
        model={
            "characters": {
                "TrackerRules": {"V4": {"DAMAGE": {"actions": ["damage", "heal", "reset"]}}},
            },
        },
    )

    with app.test_request_context("/"):
        session["company_id"] = "test-company-id"
        result = tracker_actions_for(version, tracker)

    assert result == expected
