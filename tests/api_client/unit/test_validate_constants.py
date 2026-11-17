"""Tests for vweb.api_client.validate_constants."""

import pytest

from vweb.api_client import constants
from vweb.api_client.validate_constants import (
    CONSTANT_MAP,
    ConstantMapping,
    ConstantMismatch,
    ValidationResult,
    print_report,
    validate,
)


class TestConstantMapping:
    """Tests for ConstantMapping dataclass."""

    def test_create_mapping(self):
        """Verify creating a ConstantMapping with category and option."""
        mapping = ConstantMapping(api_category="characters", api_option="CharacterClass")
        assert mapping.api_category == "characters"
        assert mapping.api_option == "CharacterClass"

    def test_mapping_is_frozen(self):
        """Verify ConstantMapping instances are immutable."""
        mapping = ConstantMapping(api_category="characters", api_option="CharacterClass")
        with pytest.raises(AttributeError):
            mapping.api_category = "other"


class TestConstantMismatch:
    """Tests for ConstantMismatch dataclass."""

    def test_create_mismatch(self):
        """Verify creating a ConstantMismatch with all fields."""
        mismatch = ConstantMismatch(
            constant_name="CharacterClass",
            api_category="characters",
            api_option="CharacterClass",
            missing_from_client={"CHANGELING"},
            extra_in_client={"MORTAL"},
        )
        assert mismatch.constant_name == "CharacterClass"
        assert mismatch.missing_from_client == {"CHANGELING"}
        assert mismatch.extra_in_client == {"MORTAL"}


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Verify creating a valid ValidationResult."""
        result = ValidationResult(is_valid=True, mismatches=[], unmapped_api_options={})
        assert result.is_valid is True
        assert result.mismatches == []
        assert result.unmapped_api_options == {}


class TestConstantMap:
    """Tests for the CONSTANT_MAP mapping table."""

    def test_all_api_constants_are_mapped(self):
        """Verify every Literal constant in constants.py has a mapping entry."""
        import typing

        from vweb.api_client import constants

        # Client-only Literal types that don't correspond to an API /options value
        client_only = {
            "AuditLogInclude",
            "BookInclude",
            "ChapterInclude",
            "CharacterInclude",
            "UserInclude",
        }

        literal_names = [
            name
            for name in dir(constants)
            if not name.startswith("_")
            and hasattr(getattr(constants, name), "__origin__")
            and getattr(constants, name).__origin__ is typing.Literal
        ]
        for name in literal_names:
            if name not in client_only:
                assert name in CONSTANT_MAP, f"Constant '{name}' is not in CONSTANT_MAP"

    def test_map_has_no_extra_entries(self):
        """Verify CONSTANT_MAP has no entries for non-existent constants."""
        from vweb.api_client import constants

        for name in CONSTANT_MAP:
            assert hasattr(constants, name), f"CONSTANT_MAP entry '{name}' has no matching constant"


class TestValidate:
    """Tests for the validate() function."""

    def test_all_constants_match(self):
        """Verify validate returns is_valid=True when all constants match API."""
        # Given: API options that exactly match local constants
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                "CharacterStatus": ["ALIVE", "DEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: Everything matches
        assert result.is_valid is True
        assert result.mismatches == []
        assert result.unmapped_api_options == {}

    def test_missing_from_client(self):
        """Verify validate detects values in API but missing from client."""
        # Given: API has an extra value for CharacterStatus
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                "CharacterStatus": ["ALIVE", "DEAD", "UNDEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: Mismatch detected
        assert result.is_valid is False
        assert len(result.mismatches) == 1
        assert result.mismatches[0].constant_name == "CharacterStatus"
        assert result.mismatches[0].missing_from_client == {"UNDEAD"}
        assert result.mismatches[0].extra_in_client == set()

    def test_extra_in_client(self):
        """Verify validate detects values in client but missing from API."""
        # Given: API is missing "MORTAL" from CharacterClass
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL"],
                "CharacterStatus": ["ALIVE", "DEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: Mismatch detected
        assert result.is_valid is False
        assert len(result.mismatches) == 1
        assert result.mismatches[0].constant_name == "CharacterClass"
        assert result.mismatches[0].extra_in_client == {"MORTAL"}
        assert result.mismatches[0].missing_from_client == set()

    def test_unmapped_api_options(self):
        """Verify validate detects API options with no local constant."""
        # Given: API has an extra option not in CONSTANT_MAP
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                "CharacterStatus": ["ALIVE", "DEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "NewOptionType": ["FOO", "BAR"],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: Unmapped option detected
        assert result.is_valid is False
        assert result.unmapped_api_options == {"characters": ["NewOptionType"]}

    def test_skips_ignored_api_options(self):
        """Verify validate ignores informational options listed in IGNORED_API_OPTIONS."""
        # Given: the autogen percentile table (an ignored option) alongside a real unmapped one
        api_options = {
            "character_autogeneration": {
                "CharacterClassPercentileChance": ["MORTAL: 0-50", "VAMPIRE: 51-60"],
                "NewOptionType": ["FOO", "BAR"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: only the genuinely unmapped option is reported
        assert result.unmapped_api_options == {"character_autogeneration": ["NewOptionType"]}

    def test_skips_related_keys(self):
        """Verify validate ignores _related keys in the API response."""
        # Given: API response includes _related metadata
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                "CharacterStatus": ["ALIVE", "DEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
                "_related": {"concepts": "https://example.com/concepts"},
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: _related is ignored, result is valid
        assert result.is_valid is True
        assert result.unmapped_api_options == {}

    def test_skips_non_list_values(self):
        """Verify validate ignores non-list values (dicts, strings) in API categories."""
        # Given: API has a dict value that should be skipped
        api_options = {
            "audit_logs": {
                "AuditEntityType": [
                    "ASSET",
                    "BOOK",
                    "CAMPAIGN",
                    "CHAPTER",
                    "CHARACTER",
                    "CHARACTER_HEALTH",
                    "CHARACTER_INVENTORY",
                    "CHARACTER_TRAIT",
                    "CHARACTER_TRAIT_SPECIALTY",
                    "CHARGEN_SESSION",
                    "COMPANY",
                    "DEVELOPER",
                    "DICTIONARY_TERM",
                    "EXPERIENCE",
                    "NOTE",
                    "QUICKROLL",
                    "USER",
                ],
                "AuditOperation": ["CREATE", "UPDATE", "DELETE"],
            },
            "characters": {
                "AbilityFocus": ["JACK_OF_ALL_TRADES", "BALANCED", "SPECIALIST"],
                "AutoGenExperienceLevel": ["NEW", "INTERMEDIATE", "ADVANCED", "ELITE"],
                "BlueprintTraitOrderBy": ["NAME", "SHEET"],
                "CharacterClass": ["VAMPIRE", "WEREWOLF", "MAGE", "HUNTER", "GHOUL", "MORTAL"],
                "CharacterStatus": ["ALIVE", "DEAD"],
                "CharacterType": ["PLAYER", "NPC", "STORYTELLER"],
                "GameVersion": ["V4", "V5"],
                "HunterCreed": [
                    "ENTREPRENEURIAL",
                    "FAITHFUL",
                    "INQUISITIVE",
                    "MARTIAL",
                    "UNDERGROUND",
                ],
                "HunterEdgeType": ["ASSETS", "APTITUDES", "ENDOWMENTS"],
                "InventoryItemType": [
                    "BOOK",
                    "CONSUMABLE",
                    "ENCHANTED",
                    "EQUIPMENT",
                    "OTHER",
                    "WEAPON",
                ],
                "SpecialtyType": ["ACTION", "OTHER", "PASSIVE", "RITUAL", "SPELL"],
                "TraitModifyCurrency": ["NO_COST", "XP", "STARTING_POINTS"],
                "TrackerAction": [
                    "spend",
                    "gain",
                    "damage",
                    "heal",
                    "add_stain",
                    "remove_stain",
                    "reset",
                ],
                "TrackerType": ["COUNTER", "DAMAGE", "STAINS"],
                "WerewolfRenown": ["GLORY", "HONOR", "WISDOM"],
                "SomeMetadata": {"key": "value"},
            },
            "companies": {
                "CompanyPermission": ["USER", "ADMIN", "OWNER", "REVOKE"],
                "PermissionManageCampaign": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionManageNPC": ["UNRESTRICTED", "STORYTELLER"],
                "PermissionsGrantXP": ["UNRESTRICTED", "PLAYER", "STORYTELLER"],
                "PermissionsFreeTraitChanges": ["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"],
                "PermissionsRecoupXP": ["UNRESTRICTED", "DENIED", "WITHIN_SESSION"],
                "SpecialtyRules": ["FIXED_COST", "RATING_BASED"],
            },
            "gameplay": {
                "DiceSize": [4, 6, 8, 10, 20, 100],
                "RollResultType": ["SUCCESS", "FAILURE", "BOTCH", "CRITICAL", "OTHER"],
            },
            "users": {
                "IdentityProvider": ["apple", "google", "discord", "github"],
                "IdentityResolution": ["matched", "linked", "created"],
                "UserRole": ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"],
            },
            "assets": {
                "AssetType": ["image", "text", "audio", "video", "document", "archive", "other"],
            },
        }

        # When: Validating
        result = validate(api_options)

        # Then: SomeMetadata (a dict, not a list) is ignored
        assert result.is_valid is True
        assert result.unmapped_api_options == {}


class TestPrintReport:
    """Tests for the print_report() function."""

    def test_valid_report_output(self, capsys):
        """Verify print_report shows success for valid result."""
        # Given: A valid result
        result = ValidationResult(is_valid=True, mismatches=[], unmapped_api_options={})

        # When: Printing the report
        print_report(result)

        # Then: Output contains success message
        captured = capsys.readouterr()
        assert "30/30 constants in sync" in captured.out

    def test_mismatch_report_output(self, capsys):
        """Verify print_report shows mismatch details."""
        # Given: A result with a mismatch
        result = ValidationResult(
            is_valid=False,
            mismatches=[
                ConstantMismatch(
                    constant_name="CharacterStatus",
                    api_category="characters",
                    api_option="CharacterStatus",
                    missing_from_client={"UNDEAD"},
                    extra_in_client=set(),
                )
            ],
            unmapped_api_options={},
        )

        # When: Printing the report
        print_report(result)

        # Then: Output contains mismatch details
        captured = capsys.readouterr()
        assert "CharacterStatus" in captured.out
        assert "UNDEAD" in captured.out

    def test_unmapped_report_output(self, capsys):
        """Verify print_report shows unmapped API options."""
        # Given: A result with unmapped options
        result = ValidationResult(
            is_valid=False,
            mismatches=[],
            unmapped_api_options={"characters": ["NewOptionType"]},
        )

        # When: Printing the report
        print_report(result)

        # Then: Output contains unmapped option
        captured = capsys.readouterr()
        assert "NewOptionType" in captured.out
        assert "characters" in captured.out


class TestTrackerConstants:
    """Tests for the tracker constants added with trait trackers and health."""

    @pytest.mark.parametrize("name", ["TrackerType", "TrackerAction"])
    def test_tracker_constants_mapped(self, name: str) -> None:
        """Verify tracker constants map to the characters options category."""
        assert CONSTANT_MAP[name] == ConstantMapping("characters", name)

    def test_tracker_rules_not_reported_unmapped(self) -> None:
        """Verify the nested TrackerRules dict is not flagged as an unmapped option."""
        options = {
            "characters": {
                "TrackerRules": {"V5": {"DAMAGE": {"actions": ["damage", "heal", "reset"]}}}
            }
        }
        assert "characters" not in validate(options).unmapped_api_options

    def test_damage_type_removed(self) -> None:
        """Verify the removed DamageType constant is neither defined nor mapped."""
        assert "DamageType" not in CONSTANT_MAP
        assert not hasattr(constants, "DamageType")
