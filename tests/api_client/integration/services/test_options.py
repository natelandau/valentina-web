"""Integration tests for OptionsService."""

import pytest
import respx

from tests.api_client.payloads import endpoint_url
from vweb.api_client.endpoints import Endpoints


@pytest.fixture
def options_response_data() -> dict:
    """Return sample options response data."""
    return {
        "companies": {
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
            "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
            "InventoryItemType": [
                "BOOK",
                "CONSUMABLE",
                "ENCHANTED",
                "EQUIPMENT",
                "OTHER",
                "WEAPON",
            ],
            "_related": {
                "concepts": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/concepts",
                "traits": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/traits",
                "trait_sections": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/{game_version}/sections",
                "trait_categories": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/{game_version}/sections/{section_id}/categories",
                "vampire_clans": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/vampire-clans",
                "werewolf_tribes": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/werewolf-tribes",
                "werewolf_auspices": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/werewolf-auspices",
                "vampire_clan_detail": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/vampire-clans/{vampire_clan_id}",
                "werewolf_auspice_detail": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/werewolf-auspices/{werewolf_auspice_id}",
                "werewolf_tribe_detail": "https://127.0.0.1:8000/api/v1/companies/{company_id}/characterblueprint/werewolf-tribes/{werewolf_tribe_id}",
            },
        },
        "character_autogeneration": {
            "CharacterClassPercentileChance": [
                "MORTAL: 0-59",
                "VAMPIRE: 60-68",
                "WEREWOLF: 69-77",
                "MAGE: 78-86",
                "HUNTER: 87-95",
                "GHOUL: 96-100",
            ]
        },
        "users": {"UserRole": ["ADMIN", "STORYTELLER", "PLAYER"]},
        "gameplay": {
            "DiceSize": ["D4", "D6", "D8", "D10", "D20", "D100"],
            "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
        },
    }


class TestOptionsServiceGetOptions:
    """Tests for OptionsService.get_options method."""

    @respx.mock
    def test_get_options(self, vclient, base_url, options_response_data):
        """Verify get_options returns the correct options."""
        # Given: A mocked options endpoint
        company_id = "company123"
        route = respx.get(endpoint_url(base_url, Endpoints.OPTIONS, company_id=company_id)).respond(
            200, json=options_response_data
        )

        # When: Calling get_options
        result = vclient.options("on-behalf-of-user", company_id=company_id).get_options()

        # Then: Returns the correct options
        assert route.called
        assert result == options_response_data
