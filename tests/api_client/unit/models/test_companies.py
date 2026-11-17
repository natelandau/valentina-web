"""Tests for vweb.api_client.api.models.companies."""

import typing

import pytest
from pydantic import ValidationError as PydanticValidationError

from vweb.api_client.constants import ManageNPCPermission, RecoupXPPermission
from vweb.api_client.models.companies import (
    Company,
    CompanyCreate,
    CompanyPermissions,
    CompanySettings,
    CompanySettingsCreate,
    CompanySettingsUpdate,
    CompanyUpdate,
    _GrantAccess,
)


class TestCompanySettings:
    """Tests for CompanySettings response model (strict — all fields required)."""

    def _full_settings_kwargs(self) -> dict[str, int | str]:
        """Return a complete set of valid kwargs for CompanySettings."""
        return {
            "character_autogen_xp_cost": 10,
            "character_autogen_num_choices": 3,
            "character_autogen_starting_points": 15,
            "permission_manage_campaign": "UNRESTRICTED",
            "permission_manage_npc": "UNRESTRICTED",
            "permission_grant_xp": "UNRESTRICTED",
            "permission_free_trait_changes": "UNRESTRICTED",
            "permission_recoup_xp": "DENIED",
            "specialty_xp_cost_enabled": True,
            "specialty_rules": "RATING_BASED",
        }

    def test_all_fields_required(self):
        """Verify full construction with all fields succeeds."""
        # When: Constructing with all required fields
        settings = CompanySettings(**self._full_settings_kwargs())

        # Then: All values are set
        assert settings.character_autogen_xp_cost == 10
        assert settings.character_autogen_num_choices == 3
        assert settings.character_autogen_starting_points == 15
        assert settings.permission_manage_campaign == "UNRESTRICTED"
        assert settings.permission_manage_npc == "UNRESTRICTED"
        assert settings.permission_grant_xp == "UNRESTRICTED"
        assert settings.permission_free_trait_changes == "UNRESTRICTED"
        assert settings.permission_recoup_xp == "DENIED"
        assert settings.specialty_xp_cost_enabled is True
        assert settings.specialty_rules == "RATING_BASED"

    def test_specialty_xp_cost_enabled_defaults_false(self):
        """Verify specialty_xp_cost_enabled defaults to False when the server omits it."""
        # Given: Full kwargs without specialty_xp_cost_enabled
        kwargs = self._full_settings_kwargs()
        del kwargs["specialty_xp_cost_enabled"]

        # When: Constructing
        settings = CompanySettings(**kwargs)

        # Then: The setting matches the server default
        assert settings.specialty_xp_cost_enabled is False

    def test_specialty_rules_defaults_fixed_cost(self):
        """Verify specialty_rules defaults to FIXED_COST when the server omits it."""
        # Given: Full kwargs without specialty_rules
        kwargs = self._full_settings_kwargs()
        del kwargs["specialty_rules"]

        # When: Constructing
        settings = CompanySettings(**kwargs)

        # Then: The setting matches the server default
        assert settings.specialty_rules == "FIXED_COST"

    def test_specialty_rules_rejects_unknown_value(self):
        """Verify an unknown specialty_rules value fails validation."""
        # Given: Full kwargs with a value the API does not define
        kwargs = self._full_settings_kwargs()
        kwargs["specialty_rules"] = "THRESHOLD"

        # When/Then: Construction fails
        with pytest.raises(PydanticValidationError):
            CompanySettings(**kwargs)

    @pytest.mark.parametrize(
        "missing_field",
        [
            "character_autogen_xp_cost",
            "character_autogen_num_choices",
            "character_autogen_starting_points",
            "permission_manage_campaign",
            "permission_manage_npc",
            "permission_grant_xp",
            "permission_free_trait_changes",
            "permission_recoup_xp",
        ],
    )
    def test_missing_required_field_raises(self, missing_field):
        """Verify missing any field raises ValidationError."""
        # Given: A full kwargs dict with one field removed
        kwargs = self._full_settings_kwargs()
        del kwargs[missing_field]

        # When/Then: Construction raises
        with pytest.raises(PydanticValidationError):
            CompanySettings(**kwargs)

    def test_invalid_permission_rejected(self):
        """Verify invalid permission enum values are rejected."""
        # Given: Full kwargs with one invalid enum
        kwargs = self._full_settings_kwargs()
        kwargs["permission_manage_campaign"] = "INVALID"

        # When/Then: Construction raises
        with pytest.raises(PydanticValidationError):
            CompanySettings(**kwargs)

    @pytest.mark.parametrize("value", typing.get_args(RecoupXPPermission))
    def test_recoup_xp_valid_values(self, value):
        """Verify permission_recoup_xp accepts each valid enum value."""
        # Given: Full kwargs with the parametrized recoup_xp value
        kwargs = self._full_settings_kwargs()
        kwargs["permission_recoup_xp"] = value

        # When: Constructing
        settings = CompanySettings(**kwargs)

        # Then: Value round-trips
        assert settings.permission_recoup_xp == value

    @pytest.mark.parametrize("value", typing.get_args(ManageNPCPermission))
    def test_manage_npc_valid_values(self, value):
        """Verify permission_manage_npc accepts each valid enum value."""
        # Given: Full kwargs with the parametrized manage_npc value
        kwargs = self._full_settings_kwargs()
        kwargs["permission_manage_npc"] = value

        # When: Constructing
        settings = CompanySettings(**kwargs)

        # Then: Value round-trips
        assert settings.permission_manage_npc == value


class TestCompanySettingsCreate:
    """Tests for CompanySettingsCreate request model (all-optional)."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None for partial create."""
        # When: Constructing with no args
        settings = CompanySettingsCreate()

        # Then: All fields are None
        assert settings.character_autogen_xp_cost is None
        assert settings.character_autogen_num_choices is None
        assert settings.character_autogen_starting_points is None
        assert settings.permission_manage_campaign is None
        assert settings.permission_grant_xp is None
        assert settings.permission_free_trait_changes is None
        assert settings.permission_recoup_xp is None
        assert settings.specialty_xp_cost_enabled is None
        assert settings.specialty_rules is None

    def test_partial_construction(self):
        """Verify construction with only some fields set."""
        # When: Constructing with two fields
        settings = CompanySettingsCreate(
            character_autogen_xp_cost=20,
            character_autogen_starting_points=8,
        )

        # Then: Set fields have values; others are None
        assert settings.character_autogen_xp_cost == 20
        assert settings.character_autogen_starting_points == 8
        assert settings.character_autogen_num_choices is None
        assert settings.permission_manage_campaign is None

    def test_model_dump_exclude_unset(self):
        """Verify model_dump with exclude_unset yields only set fields."""
        # Given: Settings with two fields set
        settings = CompanySettingsCreate(
            character_autogen_xp_cost=15,
            permission_manage_campaign="STORYTELLER",
        )

        # When: Dumping with exclude_unset and exclude_none
        data = settings.model_dump(exclude_unset=True, exclude_none=True, mode="json")

        # Then: Only set fields appear
        assert data == {
            "character_autogen_xp_cost": 15,
            "permission_manage_campaign": "STORYTELLER",
        }

    def test_invalid_permission_rejected(self):
        """Verify invalid enum values are rejected."""
        # When/Then: Invalid permission value raises
        with pytest.raises(PydanticValidationError):
            CompanySettingsCreate(permission_manage_campaign="INVALID")


class TestCompanySettingsUpdate:
    """Tests for CompanySettingsUpdate request model (all-optional)."""

    def test_all_fields_default_to_none(self):
        """Verify all fields default to None for partial update."""
        # When: Constructing with no args
        settings = CompanySettingsUpdate()

        # Then: All fields are None
        assert settings.character_autogen_xp_cost is None
        assert settings.character_autogen_num_choices is None
        assert settings.character_autogen_starting_points is None
        assert settings.permission_manage_campaign is None
        assert settings.permission_grant_xp is None
        assert settings.permission_free_trait_changes is None
        assert settings.permission_recoup_xp is None
        assert settings.specialty_xp_cost_enabled is None

    def test_partial_construction(self):
        """Verify construction with only some fields set."""
        # When: Constructing with two fields
        settings = CompanySettingsUpdate(
            character_autogen_starting_points=12,
            permission_recoup_xp="WITHIN_SESSION",
        )

        # Then: Set fields have values; others are None
        assert settings.character_autogen_starting_points == 12
        assert settings.permission_recoup_xp == "WITHIN_SESSION"
        assert settings.character_autogen_xp_cost is None

    def test_model_dump_exclude_unset(self):
        """Verify model_dump with exclude_unset yields only set fields."""
        # Given: Settings with one field set
        settings = CompanySettingsUpdate(character_autogen_starting_points=25)

        # When: Dumping with exclude_unset and exclude_none
        data = settings.model_dump(exclude_unset=True, exclude_none=True, mode="json")

        # Then: Only the set field appears
        assert data == {"character_autogen_starting_points": 25}

    def test_model_dump_false_specialty_xp_cost_enabled(self):
        """Verify an explicit False for specialty_xp_cost_enabled is sent, not dropped."""
        # Given: Settings disabling the specialty XP cost
        settings = CompanySettingsUpdate(specialty_xp_cost_enabled=False)

        # When: Dumping with exclude_unset and exclude_none
        data = settings.model_dump(exclude_unset=True, exclude_none=True, mode="json")

        # Then: The False value is kept
        assert data == {"specialty_xp_cost_enabled": False}

    def test_invalid_permission_rejected(self):
        """Verify invalid enum values are rejected."""
        # When/Then: Invalid permission value raises
        with pytest.raises(PydanticValidationError):
            CompanySettingsUpdate(permission_recoup_xp="INVALID")


class TestCompany:
    """Tests for Company model."""

    def test_all_fields_required(self):
        """Verify all fields are required for response DTO."""
        # When: Creating company with all fields
        company = Company(
            id="507f1f77bcf86cd799439011",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Test",
            resources_modified_at="2024-01-15T10:30:00Z",
            description=None,
            email="test@example.com",
            settings=CompanySettings(
                character_autogen_xp_cost=10,
                character_autogen_num_choices=3,
                character_autogen_starting_points=5,
                permission_manage_campaign="UNRESTRICTED",
                permission_manage_npc="UNRESTRICTED",
                permission_grant_xp="UNRESTRICTED",
                permission_free_trait_changes="UNRESTRICTED",
                permission_recoup_xp="UNRESTRICTED",
            ),
        )

        # Then: Company is created correctly
        assert company.id == "507f1f77bcf86cd799439011"
        assert company.date_created is not None
        assert company.date_modified is not None
        assert company.name == "Test"
        assert company.email == "test@example.com"
        assert company.description is None
        assert company.settings is not None

    def test_full_company(self):
        """Verify creating company with all fields populated."""
        # Given: Settings with some values
        settings = CompanySettings(
            character_autogen_xp_cost=15,
            character_autogen_num_choices=3,
            character_autogen_starting_points=10,
            permission_manage_campaign="UNRESTRICTED",
            permission_manage_npc="UNRESTRICTED",
            permission_grant_xp="UNRESTRICTED",
            permission_free_trait_changes="UNRESTRICTED",
            permission_recoup_xp="DENIED",
        )

        # When: Creating company with all fields
        company = Company(
            id="507f1f77bcf86cd799439011",
            date_created="2024-01-15T10:30:00Z",
            date_modified="2024-01-15T10:30:00Z",
            name="Full Company",
            description="A complete company",
            email="full@example.com",
            resources_modified_at="2024-01-15T10:30:00Z",
            settings=settings,
        )

        # Then: All fields are set correctly
        assert company.id == "507f1f77bcf86cd799439011"
        assert company.date_created is not None
        assert company.date_modified is not None
        assert company.name == "Full Company"
        assert company.description == "A complete company"
        assert company.email == "full@example.com"
        assert company.settings is not None
        assert company.settings.character_autogen_xp_cost == 15

    def test_company_from_api_response(self):
        """Verify creating company from API response dict."""
        # Given: API response data
        data = {
            "id": "507f1f77bcf86cd799439011",
            "date_created": "2024-01-15T10:30:00Z",
            "date_modified": "2024-01-15T10:30:00Z",
            "name": "API Company",
            "description": "From API",
            "email": "api@example.com",
            "resources_modified_at": "2024-01-15T10:30:00Z",
            "settings": {
                "character_autogen_xp_cost": 10,
                "character_autogen_num_choices": 3,
                "character_autogen_starting_points": 5,
                "permission_manage_campaign": "UNRESTRICTED",
                "permission_manage_npc": "UNRESTRICTED",
                "permission_grant_xp": "PLAYER",
                "permission_free_trait_changes": "WITHIN_24_HOURS",
                "permission_recoup_xp": "UNRESTRICTED",
            },
        }

        # When: Creating company from dict
        company = Company.model_validate(data)

        # Then: Company is created correctly
        assert company.id == "507f1f77bcf86cd799439011"
        assert company.name == "API Company"
        assert company.settings is not None
        assert company.settings.permission_grant_xp == "PLAYER"

    def test_missing_required_field_raises_error(self):
        """Verify missing required fields raises ValidationError."""
        # When/Then: Missing required field raises error
        with pytest.raises(PydanticValidationError):
            Company(
                id="507f1f77bcf86cd799439011",
                date_created="2024-01-15T10:30:00Z",
                date_modified="2024-01-15T10:30:00Z",
                name="Test",
                resources_modified_at="2024-01-15T10:30:00Z",
                email="test@example.com",
                # Missing: description, settings
            )


class TestCompanyPermissions:
    """Tests for CompanyPermissions model."""

    def test_all_fields_required(self):
        """Verify all fields are required for response DTO."""
        # When: Creating permissions with all fields
        perms = CompanyPermissions(
            company_id="company123",
            name=None,
            permission="USER",
        )

        # Then: Permissions are created correctly
        assert perms.company_id == "company123"
        assert perms.permission == "USER"
        assert perms.name is None

    def test_full_permissions(self):
        """Verify creating permissions with all fields."""
        # When: Creating permissions with all fields
        perms = CompanyPermissions(
            company_id="company123",
            name="Test Company",
            permission="ADMIN",
        )

        # Then: All fields are set correctly
        assert perms.company_id == "company123"
        assert perms.name == "Test Company"
        assert perms.permission == "ADMIN"

    def test_permissions_from_api_response(self):
        """Verify creating permissions from API response dict."""
        # Given: API response data
        data = {
            "company_id": "507f1f77bcf86cd799439011",
            "name": "API Company",
            "permission": "OWNER",
        }

        # When: Creating permissions from dict
        perms = CompanyPermissions.model_validate(data)

        # Then: Permissions are created correctly
        assert perms.company_id == "507f1f77bcf86cd799439011"
        assert perms.name == "API Company"
        assert perms.permission == "OWNER"

    def test_invalid_permission_rejected(self):
        """Verify invalid permission values are rejected by Pydantic."""
        # When/Then: Creating permissions with invalid permission raises error
        with pytest.raises(PydanticValidationError):
            CompanyPermissions(company_id="company123", permission="INVALID")


class TestCompanyCreate:
    """Tests for CompanyCreate model."""

    def test_minimal_request(self):
        """Verify creating request with minimal fields."""
        # When: Creating request with required fields only
        request = CompanyCreate(name="Test", email="test@example.com")

        # Then: Request is created with correct values
        assert request.name == "Test"
        assert request.email == "test@example.com"
        assert request.description is None
        assert request.settings is None

    def test_full_request(self):
        """Verify creating request with all fields."""
        # Given: Settings with some values
        settings = CompanySettingsCreate(character_autogen_xp_cost=20)

        # When: Creating request with all fields
        request = CompanyCreate(
            name="Full Company",
            email="full@example.com",
            description="A complete company",
            settings=settings,
        )

        # Then: All fields are set correctly
        assert request.name == "Full Company"
        assert request.email == "full@example.com"
        assert request.description == "A complete company"
        assert request.settings is not None
        assert request.settings.character_autogen_xp_cost == 20

    def test_model_dump_excludes_unset(self):
        """Verify model_dump with exclude_unset excludes unset fields."""
        # Given: Request with only required fields
        request = CompanyCreate(name="Test", email="test@example.com")

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only set fields are included
        assert data == {"name": "Test", "email": "test@example.com"}

    def test_model_dump_with_settings(self):
        """Verify model_dump includes settings correctly."""
        # Given: Request with partial settings
        settings = CompanySettingsCreate(
            character_autogen_xp_cost=15,
            permission_manage_campaign="STORYTELLER",
        )
        request = CompanyCreate(
            name="Test",
            email="test@example.com",
            settings=settings,
        )

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Settings are included with correct values
        assert data["settings"]["character_autogen_xp_cost"] == 15
        assert data["settings"]["permission_manage_campaign"] == "STORYTELLER"

    def test_name_validation(self):
        """Verify name validation is enforced."""
        # When/Then: Creating request with invalid name raises error
        with pytest.raises(PydanticValidationError):
            CompanyCreate(name="AB", email="test@example.com")


class TestCompanyUpdate:
    """Tests for CompanyUpdate model."""

    def test_empty_request(self):
        """Verify creating empty update request."""
        # When: Creating request with no fields
        request = CompanyUpdate()

        # Then: All fields are None
        assert request.name is None
        assert request.email is None
        assert request.description is None
        assert request.settings is None

    def test_partial_update(self):
        """Verify creating request with only some fields."""
        # When: Creating request with only name
        request = CompanyUpdate(name="Updated Name")

        # Then: Only name is set
        assert request.name == "Updated Name"
        assert request.email is None

    def test_model_dump_excludes_unset(self):
        """Verify model_dump with exclude_unset only includes set fields."""
        # Given: Request with only name set
        request = CompanyUpdate(name="Updated Name")

        # When: Dumping with exclude_none and exclude_unset
        data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")

        # Then: Only name is in the output
        assert data == {"name": "Updated Name"}

    def test_update_explicit_none_for_constrained_fields(self):
        """Verify explicitly passing None for constrained optional fields does not raise."""
        # When: Creating an update request with None for constrained fields
        request = CompanyUpdate(name=None, description=None)

        # Then: Fields are None without validation errors
        assert request.name is None
        assert request.description is None

    def test_update_constrained_fields_still_validate_non_none(self):
        """Verify constraints still apply when a non-None value is provided."""
        with pytest.raises(PydanticValidationError):
            CompanyUpdate(name="ab")

        with pytest.raises(PydanticValidationError):
            CompanyUpdate(description="ab")

    def test_update_with_settings(self):
        """Verify CompanyUpdate accepts and serializes a CompanySettingsUpdate."""
        # Given: A partial settings update
        settings = CompanySettingsUpdate(
            character_autogen_starting_points=25,
            permission_recoup_xp="WITHIN_SESSION",
        )

        # When: Wrapping in a CompanyUpdate and dumping
        request = CompanyUpdate(settings=settings)
        data = request.model_dump(exclude_unset=True, exclude_none=True, mode="json")

        # Then: Only set settings fields appear
        assert data == {
            "settings": {
                "character_autogen_starting_points": 25,
                "permission_recoup_xp": "WITHIN_SESSION",
            }
        }


class TestCompanyCreateConstraints:
    """Tests for CompanyCreate optional field constraint handling."""

    def test_create_explicit_none_for_optional_constrained_fields(self):
        """Verify explicitly passing None for optional constrained fields does not raise."""
        # When: Creating a request with None for optional description
        request = CompanyCreate(name="Test", email="test@example.com", description=None)

        # Then: Description is None without validation errors
        assert request.description is None


class TestGrantAccess:
    """Tests for _GrantAccess model."""

    def test_create_request(self):
        """Verify creating grant access request."""
        # When: Creating request
        request = _GrantAccess(
            developer_id="dev123",
            permission="ADMIN",
        )

        # Then: Fields are set correctly
        assert request.developer_id == "dev123"
        assert request.permission == "ADMIN"

    def test_model_dump_serializes_correctly(self):
        """Verify model_dump serializes permission to string."""
        # Given: Request with permission
        request = _GrantAccess(
            developer_id="dev123",
            permission="OWNER",
        )

        # When: Dumping with mode="json"
        data = request.model_dump(mode="json")

        # Then: Permission is serialized as string
        assert data["permission"] == "OWNER"

    def test_invalid_permission_rejected(self):
        """Verify invalid permission values are rejected by Pydantic."""
        # When/Then: Creating request with invalid permission raises error
        with pytest.raises(PydanticValidationError):
            _GrantAccess(developer_id="dev123", permission="INVALID")
