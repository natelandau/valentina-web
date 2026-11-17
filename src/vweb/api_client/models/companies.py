"""Pydantic models for Company API responses."""

from datetime import datetime

from pydantic import BaseModel

from vweb.api_client.constants import (
    DEFAULT_CUSTOM_FLAW_XP_COST,
    FreeTraitChangesPermission,
    GrantXPPermission,
    ManageCampaignPermission,
    ManageNPCPermission,
    PermissionLevel,
    RecoupXPPermission,
)
from vweb.api_client.models.request_types import CustomFlawXPCost, LongText3, Name3to50
from vweb.api_client.models.users import User


class CompanySettings(BaseModel):
    """Company configuration settings as returned by the API.

    Strict response model — every field is always populated by the server.
    For partial create/update payloads, use CompanySettingsCreate or
    CompanySettingsUpdate instead.
    """

    character_autogen_xp_cost: int
    character_autogen_num_choices: int
    character_autogen_starting_points: int
    permission_manage_campaign: ManageCampaignPermission
    permission_manage_npc: ManageNPCPermission
    permission_grant_xp: GrantXPPermission
    permission_free_trait_changes: FreeTraitChangesPermission
    permission_recoup_xp: RecoupXPPermission
    specialty_xp_cost_enabled: bool = False
    custom_flaw_xp_cost: int = DEFAULT_CUSTOM_FLAW_XP_COST


class CompanySettingsCreate(BaseModel):
    """Partial CompanySettings payload for POST /companies.

    All fields optional — the server applies defaults for anything omitted.
    """

    character_autogen_xp_cost: int | None = None
    character_autogen_num_choices: int | None = None
    character_autogen_starting_points: int | None = None
    permission_manage_campaign: ManageCampaignPermission | None = None
    permission_manage_npc: ManageNPCPermission | None = None
    permission_grant_xp: GrantXPPermission | None = None
    permission_free_trait_changes: FreeTraitChangesPermission | None = None
    permission_recoup_xp: RecoupXPPermission | None = None
    specialty_xp_cost_enabled: bool | None = None
    custom_flaw_xp_cost: CustomFlawXPCost | None = None


class CompanySettingsUpdate(BaseModel):
    """Partial CompanySettings payload for PATCH /companies/{id}.

    All fields optional — omitted fields remain unchanged on the server.
    """

    character_autogen_xp_cost: int | None = None
    character_autogen_num_choices: int | None = None
    character_autogen_starting_points: int | None = None
    permission_manage_campaign: ManageCampaignPermission | None = None
    permission_manage_npc: ManageNPCPermission | None = None
    permission_grant_xp: GrantXPPermission | None = None
    permission_free_trait_changes: FreeTraitChangesPermission | None = None
    permission_recoup_xp: RecoupXPPermission | None = None
    specialty_xp_cost_enabled: bool | None = None
    custom_flaw_xp_cost: CustomFlawXPCost | None = None


class Company(BaseModel):
    """Response model for a company.

    Represents a company entity returned from the API with all its properties and settings.
    """

    id: str
    date_created: datetime
    date_modified: datetime
    name: str
    description: str | None
    email: str
    resources_modified_at: datetime
    num_campaigns: int = 0
    num_player_characters: int = 0
    num_storyteller_characters: int = 0
    num_npc_characters: int = 0
    num_users: int = 0
    settings: CompanySettings


class CompanyPermissions(BaseModel):
    """Response model for company permission grants.

    Returned when granting or modifying developer access to a company.
    """

    company_id: str
    name: str | None
    permission: PermissionLevel


class NewCompanyResponse(BaseModel):
    """Response model for creating a new company.

    Returned when a new company is created.
    """

    company: Company
    admin_user: User


# -----------------------------------------------------------------------------
# Request Body Models
# -----------------------------------------------------------------------------


class CompanyCreate(BaseModel):
    """Request body for creating a new company.

    Used to construct the JSON payload for company creation.
    """

    name: Name3to50
    email: str
    description: LongText3 | None = None
    settings: CompanySettingsCreate | None = None


class CompanyUpdate(BaseModel):
    """Request body for updating a company.

    Only include fields that need to be changed; omitted fields remain unchanged.
    """

    name: Name3to50 | None = None
    email: str | None = None
    description: LongText3 | None = None
    settings: CompanySettingsUpdate | None = None


class _GrantAccess(BaseModel):
    """Internal request body for granting developer access to a company."""

    developer_id: str
    permission: PermissionLevel


__all__ = [
    "Company",
    "CompanyCreate",
    "CompanyPermissions",
    "CompanySettings",
    "CompanySettingsCreate",
    "CompanySettingsUpdate",
    "CompanyUpdate",
    "NewCompanyResponse",
    "_GrantAccess",
]
