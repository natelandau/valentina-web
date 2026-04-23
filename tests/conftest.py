"""Shared test fixtures."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from vclient.models.companies import CompanySettings
from vclient.models.diceroll import DiceRollResultSchema
from vclient.testing import (
    CampaignFactory,
    CompanyFactory,
    SyncFakeVClient,
    UserFactory,
)

from vweb.config import APISettings, RedisSettings, Settings
from vweb.lib.global_context import GlobalContext

# Polyfactory randomizes CompanySettings, including permission fields. When it rolls
# "UNRESTRICTED" for permission_manage_campaign, PLAYER-role tests flake because
# can_manage_campaign() returns True from the company rather than the user's role.
# Force a deterministic, permission-locked CompanySettings unless the caller passes one.
_original_company_build = CompanyFactory.build

_TEST_COMPANY_SETTINGS = CompanySettings(
    character_autogen_xp_cost=0,
    character_autogen_num_choices=3,
    character_autogen_starting_points=0,
    permission_manage_campaign="STORYTELLER",
    permission_grant_xp="STORYTELLER",
    permission_free_trait_changes="STORYTELLER",
    permission_recoup_xp="DENIED",
)


def _build_company_with_settings(**kwargs):  # noqa: ANN202
    kwargs.setdefault("settings", _TEST_COMPANY_SETTINGS)
    return _original_company_build(**kwargs)


CompanyFactory.build = staticmethod(_build_company_with_settings)  # type: ignore[method-assign]  # ty:ignore[invalid-assignment]

if TYPE_CHECKING:
    from flask import Flask
    from flask.testing import FlaskClient


@pytest.fixture
def test_settings() -> Settings:
    """Build test settings without requiring environment variables."""
    return Settings(
        _env_file=None,
        app_name="Test App",
        env="development",
        secret_key="test-secret-key",  # noqa: S106
        host="127.0.0.1",
        port=8089,
        redis=RedisSettings(url=""),
        api=APISettings(
            base_url="http://localhost:8080",
            api_key="test-api-key",
        ),
    )


@pytest.fixture
def app(test_settings) -> Flask:
    """Create a test application instance."""
    import vweb.config
    from vweb.app import create_app

    # Ensure get_settings() returns test_settings everywhere
    vweb.config._settings = test_settings

    app = create_app(settings_override=test_settings)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app) -> FlaskClient:
    """Create a test client with a pre-seeded multi-company session."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
        sess["company_id"] = "test-company-id"
        sess["companies"] = {
            "test-company-id": {
                "user_id": "test-user-id",
                "company_name": "Test Company",
                "role": "PLAYER",
            },
        }
    return client


@pytest.fixture
def mock_global_context() -> GlobalContext:
    """Build a minimal GlobalContext with factory-built model instances."""
    company = CompanyFactory.build(name="Test Company")
    user = UserFactory.build(
        id="test-user-id",
        name_first="Test",
        name_last="User",
        company_id="test-company-id",
    )

    campaign = CampaignFactory.build(name="Test Campaign")

    return GlobalContext(
        company=company,
        users=[user],
        campaigns=[campaign],
        books_by_campaign={campaign.id: []},
        characters_by_campaign={campaign.id: []},
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )


@pytest.fixture
def fake_vclient(app):
    """Provide a SyncFakeVClient that intercepts all vclient HTTP calls.

    Depends on `app` so the fake client registers as the default AFTER create_app()
    creates its own SyncVClient, ensuring sync_*_service() calls use the fake.
    """
    with SyncFakeVClient() as client:
        yield client


@pytest.fixture(autouse=True)
def _mock_api(mocker, mock_global_context) -> None:
    """Prevent before_request hooks and route handlers from calling the real API."""
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=mock_global_context)
    mocker.patch("vweb.lib.hooks.clear_global_context_cache")

    mock_dict_svc = mocker.patch("vweb.routes.dictionary.cache.sync_dictionary_service")
    mock_dict_svc.return_value.list_all.return_value = []

    mocker.patch(
        "vweb.lib.options_cache.sync_options_service",
        return_value=MagicMock(
            get_options=MagicMock(
                return_value={
                    "companies": {},
                    "characters": {
                        "CharacterClass": [
                            "VAMPIRE",
                            "WEREWOLF",
                            "MAGE",
                            "HUNTER",
                            "GHOUL",
                            "MORTAL",
                        ],
                        "CharacterType": ["PLAYER", "NPC", "STORYTELLER", "DEVELOPER"],
                        "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                        "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                        "InventoryItemType": [
                            "BOOK",
                            "CONSUMABLE",
                            "ENCHANTED",
                            "EQUIPMENT",
                            "OTHER",
                            "WEAPON",
                        ],
                        "GameVersion": ["V4", "V5"],
                        "HunterCreed": [
                            "JUDGE",
                            "DEFENDER",
                            "INNOCENT",
                            "MARTYR",
                            "REDEEMER",
                            "VISIONARY",
                        ],
                        "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                    },
                    "users": {"UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED"]},
                    "gameplay": {
                        "DiceSize": [4, 6, 8, 10, 20, 100],
                        "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
                    },
                    "assets": {},
                }
            )
        ),
    )


def get_csrf(client) -> str:
    """Extract a valid CSRF token from a page that renders PageLayout.

    Uses /pending-approval since it renders PageLayout without hitting any
    campaign or character API mocks that individual tests may override.
    """
    response = client.get("/pending-approval")
    body = response.get_data(as_text=True)
    match = re.search(r'X-CSRFToken":\s*"([^"]+)"', body)
    return match.group(1) if match else ""


def make_dice_roll_result(**overrides: object) -> DiceRollResultSchema:
    """Build a DiceRollResultSchema with sensible defaults."""
    defaults: dict[str, object] = {
        "total_result": 3,
        "total_result_type": "SUCCESS",
        "total_result_humanized": "3 successes",
        "total_dice_roll": [8, 7, 9, 3, 2],
        "player_roll": [8, 7, 9, 3, 2],
        "desperation_roll": [],
        "total_dice_roll_emoji": "",
        "total_dice_roll_shortcode": "",
        "player_roll_emoji": "",
        "player_roll_shortcode": "",
        "desperation_roll_emoji": "",
        "desperation_roll_shortcode": "",
    }
    defaults.update(overrides)
    return DiceRollResultSchema(**defaults)
