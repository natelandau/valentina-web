"""Service for interacting with the Characters API."""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import (
    DEFAULT_PAGE_LIMIT,
    CharacterClass,
    CharacterInclude,
    CharacterStatus,
    CharacterType,
    TrackerAction,
)
from vweb.api_client.models import (
    Character,
    CharacterCreate,
    CharacterDetail,
    CharacterFullSheet,
    CharacterUpdate,
    FullSheetTraitCategory,
    Health,
    HealthStateSet,
    InventoryItem,
    InventoryItemCreate,
    InventoryItemUpdate,
    PaginatedResponse,
    RollStatistics,
    _TrackerAction,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services._assets import AssetRoutes, AssetsMixin
from vweb.api_client.services._notes import NoteRoutes, NotesMixin

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class CharactersService(NotesMixin, AssetsMixin):
    """Service for managing characters within a company in the Valentina API.

    This service is scoped to a specific company at initialization time.
    All methods operate within that context.

    Provides methods to create, retrieve, update, and delete characters.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            characters = client.characters("company_id")
            all_characters = characters.list_all()
            character = characters.get("character_id")
    """

    _parent_id_param = "character_id"
    _note_routes = NoteRoutes(
        page=Routes.CHARACTERS_NOTES_LIST,
        get=Routes.CHARACTERS_NOTES_GET,
        create=Routes.CHARACTERS_NOTES_CREATE,
        update=Routes.CHARACTERS_NOTES_UPDATE,
        delete=Routes.CHARACTERS_NOTES_DELETE,
    )
    _asset_routes = AssetRoutes(
        page=Routes.CHARACTERS_ASSETS_LIST,
        get=Routes.CHARACTERS_ASSETS_GET,
        delete=Routes.CHARACTERS_ASSETS_DELETE,
        upload=Routes.CHARACTERS_ASSETS_UPLOAD,
    )

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str) -> None:
        """Initialize the service scoped to a specific company.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client, on_behalf_of=on_behalf_of, company_id=company_id)

    # Character CRUD Methods

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        campaign_id: str | None = None,
        user_player_id: str | None = None,
        user_creator_id: str | None = None,
        character_class: CharacterClass | None = None,
        character_type: CharacterType | None = None,
        status: CharacterStatus | None = None,
        is_temporary: bool = False,
    ) -> PaginatedResponse[Character]:
        """Retrieve a paginated page of characters.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).
            campaign_id: Filter by campaign ID.
            user_player_id: Filter by player user ID.
            user_creator_id: Filter by creator user ID.
            character_class: Filter by character class.
            character_type: Filter by character type.
            status: Filter by character status.
            is_temporary: Filter for temporary characters.

        Returns:
            A PaginatedResponse containing Character objects and pagination metadata.
        """
        return self._page(
            Routes.CHARACTERS_LIST,
            limit=limit,
            offset=offset,
            params=self._build_params(
                campaign_id=campaign_id,
                user_player_id=user_player_id,
                user_creator_id=user_creator_id,
                character_class=character_class,
                character_type=character_type,
                status=status,
                is_temporary=is_temporary,
            ),
        )

    def list_all(
        self,
        *,
        campaign_id: str | None = None,
        user_player_id: str | None = None,
        user_creator_id: str | None = None,
        character_class: CharacterClass | None = None,
        character_type: CharacterType | None = None,
        status: CharacterStatus | None = None,
        is_temporary: bool = False,
    ) -> list[Character]:
        """Retrieve all characters.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Args:
            campaign_id: Filter by campaign ID.
            user_player_id: Filter by player user ID.
            user_creator_id: Filter by creator user ID.
            character_class: Filter by character class.
            character_type: Filter by character type.
            status: Filter by character status.
            is_temporary: Filter for temporary characters.

        Returns:
            A list of all Character objects.
        """
        return list(
            self.iter_all(
                campaign_id=campaign_id,
                user_player_id=user_player_id,
                user_creator_id=user_creator_id,
                character_class=character_class,
                character_type=character_type,
                status=status,
                is_temporary=is_temporary,
            )
        )

    def iter_all(
        self,
        *,
        limit: int = 100,
        campaign_id: str | None = None,
        user_player_id: str | None = None,
        user_creator_id: str | None = None,
        character_class: CharacterClass | None = None,
        character_type: CharacterType | None = None,
        status: CharacterStatus | None = None,
        is_temporary: bool = False,
    ) -> Iterator[Character]:
        """Iterate through all characters.

        Yields individual characters, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            limit: Items per page (default 100 for efficiency).
            campaign_id: Filter by campaign ID.
            user_player_id: Filter by player user ID.
            user_creator_id: Filter by creator user ID.
            character_class: Filter by character class.
            character_type: Filter by character type.
            status: Filter by character status.
            is_temporary: Whether to filter for temporary characters.

        Yields:
            Individual Character objects.

        Example:
            for character in characters.iter_all():
                print(character.name)
        """
        yield from self._iter(
            Routes.CHARACTERS_LIST,
            limit=limit,
            params=self._build_params(
                campaign_id=campaign_id,
                user_player_id=user_player_id,
                user_creator_id=user_creator_id,
                character_class=character_class,
                character_type=character_type,
                status=status,
                is_temporary=is_temporary,
            ),
        )

    def get(
        self,
        character_id: str,
        *,
        include: Sequence[CharacterInclude] | None = None,
    ) -> CharacterDetail:
        """Retrieve detailed information about a specific character.

        Fetches the character including traits, status, and biographical data.
        Optionally embed child resources directly in the response.

        Args:
            character_id: The ID of the character to retrieve.
            include: Child resources to embed in the response. Valid values are
                ``"traits"``, ``"inventory"``, ``"notes"``, and ``"assets"``.

        Returns:
            The CharacterDetail object with full details and any requested embeds.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            Routes.CHARACTERS_GET,
            params=self._build_params(include=list(include) if include else None),
            character_id=character_id,
        )

    def create(
        self,
        request: CharacterCreate | None = None,
        **kwargs,
    ) -> Character:
        """Create a new character within the campaign.

        The character is associated with both a creator user (who made the character)
        and a player user (who controls the character). If no player is specified,
        the creator becomes the player.

        Args:
            request: A CharacterCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CharacterCreate if request is not provided.
                Required: campaign_id (str), character_class (CharacterClass),
                game_version (GameVersion), name_first (str), name_last (str).
                Optional: type (CharacterType), name_nick (str), age (int),
                date_of_birth (datetime.date | None, ISO 8601 calendar date),
                biography (str), demeanor (str), nature (str), concept_id (str),
                user_player_id (str), traits (list), vampire_attributes, etc.

        Returns:
            The newly created Character object.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            AuthorizationError: If you don't have appropriate access.
        """
        body = request if request is not None else self._validate_request(CharacterCreate, **kwargs)
        return self._call(
            Routes.CHARACTERS_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

    def update(
        self,
        character_id: str,
        request: CharacterUpdate | None = None,
        **kwargs,
    ) -> Character:
        """Modify a character's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.
        Use trait-specific endpoints to modify character traits.

        Note: Only the character's player or a storyteller can update the character.

        Args:
            character_id: The ID of the character to update.
            request: A CharacterUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for CharacterUpdate if request is not provided.
                All fields are optional: character_class, type, game_version, status,
                name_first, name_last, name_nick, age, date_of_birth (datetime.date | None,
                ISO 8601 calendar date; pass None to clear it), biography, demeanor, nature,
                concept_id, user_player_id, vampire_attributes, werewolf_attributes, etc.

        Returns:
            The updated Character object.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(CharacterUpdate, **kwargs)
        payload = body.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        # The API distinguishes an omitted key (leave unchanged) from an explicit null (clear).
        # exclude_none drops None, so re-add date_of_birth when the caller set it to None to clear it.
        if "date_of_birth" in body.model_fields_set and body.date_of_birth is None:
            payload["date_of_birth"] = None
        return self._call(Routes.CHARACTERS_UPDATE, json=payload, character_id=character_id)

    def delete(self, character_id: str) -> None:
        """Remove a character from the campaign.

        The character will no longer be accessible. This action cannot be undone.

        Note: Only the character's player or a storyteller can delete the character.

        Args:
            character_id: The ID of the character to delete.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._send(Routes.CHARACTERS_DELETE, character_id=character_id)

    def get_statistics(
        self,
        character_id: str,
        *,
        num_top_traits: int = 5,
    ) -> RollStatistics:
        """Retrieve aggregated dice roll statistics for a specific character.

        Includes success rates, critical frequencies, most-used traits, etc.

        Args:
            character_id: The ID of the character to get statistics for.
            num_top_traits: Number of top traits to include (default 5).

        Returns:
            RollStatistics object with aggregated statistics.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            Routes.CHARACTERS_STATISTICS,
            params={"num_top_traits": num_top_traits},
            character_id=character_id,
        )

    def get_full_sheet(
        self,
        character_id: str,
        *,
        include_available_traits: bool = False,
    ) -> CharacterFullSheet:
        """Retrieve the full character sheet with all traits organized hierarchically.

        Returns the character data along with the complete trait hierarchy organized as
        sections > categories > subcategories > character traits. Optionally include
        available traits the character could add.

        Args:
            character_id: The ID of the character to get the full sheet for.
            include_available_traits: Include unassigned standard traits in each
                category and subcategory. Defaults to False.

        Returns:
            CharacterFullSheet with nested trait hierarchy.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have access.
        """
        params = self._build_params(
            include_available_traits=include_available_traits or None,
        )
        return self._call(Routes.CHARACTERS_FULL_SHEET, params=params, character_id=character_id)

    def get_full_sheet_category(
        self,
        character_id: str,
        category_id: str,
        *,
        include_available_traits: bool = False,
    ) -> FullSheetTraitCategory:
        """Retrieve a single category slice of the character's full sheet.

        Fetch one category with its subcategories and traits, enabling efficient
        UI refreshes after a trait edit without rebuilding the entire sheet.

        Args:
            character_id: The ID of the character.
            category_id: The ID of the trait category to retrieve.
            include_available_traits: Include unassigned standard traits in the
                category and its subcategories. Defaults to False.

        Returns:
            FullSheetTraitCategory with nested subcategories and traits.

        Raises:
            NotFoundError: If the character or category does not exist.
            AuthorizationError: If you don't have access.
        """
        params = self._build_params(
            include_available_traits=include_available_traits or None,
        )
        return self._call(
            Routes.CHARACTERS_FULL_SHEET_CATEGORY,
            params=params,
            character_id=character_id,
            category_id=category_id,
        )

    # Character Inventory Methods

    def get_inventory_page(
        self,
        character_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[InventoryItem]:
        """Retrieve a paginated page of inventory items for a character.

        Args:
            character_id: The ID of the character whose inventory items to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing InventoryItem objects and pagination metadata.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._page(
            Routes.CHARACTERS_INVENTORY_LIST, limit=limit, offset=offset, character_id=character_id
        )

    def list_all_inventory(
        self,
        character_id: str,
    ) -> list[InventoryItem]:
        """Retrieve all notes for a character.

        Automatically paginates through all results. Use `get_inventory_page()` for paginated
        access or `iter_all_inventory()` for memory-efficient streaming of large datasets.

        Args:
            character_id: The ID of the character whose inventory items to list.

        Returns:
            A list of all InventoryItem objects.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have access.
        """
        return list(self.iter_all_inventory(character_id))

    def iter_all_inventory(
        self,
        character_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[InventoryItem]:
        """Iterate through all inventory items for a character.

        Yields individual inventory items, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            character_id: The ID of the character whose inventory items to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual InventoryItem objects.

        Example:
            for item in characters.iter_all_inventory("character_id"):
                print(item.name)
        """
        yield from self._iter(
            Routes.CHARACTERS_INVENTORY_LIST, limit=limit, character_id=character_id
        )

    def get_inventory_item(
        self,
        character_id: str,
        item_id: str,
    ) -> InventoryItem:
        """Retrieve a specific inventory item including its content and metadata.

        Args:
            character_id: The ID of the character that owns the inventory item.
            item_id: The ID of the inventory item to retrieve.

        Returns:
            The InventoryItem object with full details.

        Raises:
            NotFoundError: If the inventory item does not exist.
            AuthorizationError: If you don't have access.
        """
        return self._call(
            Routes.CHARACTERS_INVENTORY_GET, character_id=character_id, item_id=item_id
        )

    def create_inventory_item(
        self,
        character_id: str,
        request: InventoryItemCreate | None = None,
        **kwargs,
    ) -> InventoryItem:
        """Create a new inventory item for a character.

        Args:
            character_id: The ID of the character to create the inventory item for.
            request: An InventoryItemCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for InventoryItemCreate if request is not provided.
                Accepts: name (str, required), type (CharacterInventoryType, required),
                description (str | None).

        Returns:
            The newly created InventoryItem object.

        Raises:
            NotFoundError: If the character does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = (
            request
            if request is not None
            else self._validate_request(InventoryItemCreate, **kwargs)
        )
        return self._call(
            Routes.CHARACTERS_INVENTORY_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            character_id=character_id,
        )

    def update_inventory_item(
        self,
        character_id: str,
        item_id: str,
        request: InventoryItemUpdate | None = None,
        **kwargs,
    ) -> InventoryItem:
        """Modify an inventory item's content.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            character_id: The ID of the character that owns the inventory item.
            item_id: The ID of the inventory item to update.
            request: An InventoryItemUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for InventoryItemUpdate if request is not provided.
                Accepts: name (str | None), type (CharacterInventoryType | None),
                description (str | None).

        Returns:
            The updated InventoryItem object.

        Raises:
            NotFoundError: If the inventory item does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = (
            request
            if request is not None
            else self._validate_request(InventoryItemUpdate, **kwargs)
        )
        return self._call(
            Routes.CHARACTERS_INVENTORY_UPDATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
            character_id=character_id,
            item_id=item_id,
        )

    def delete_inventory_item(
        self,
        character_id: str,
        item_id: str,
    ) -> None:
        """Remove an inventory item from a character.

        This action cannot be undone.

        Args:
            character_id: The ID of the character that owns the inventory item.
            item_id: The ID of the inventory item to delete.

        Raises:
            NotFoundError: If the inventory item does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._send(Routes.CHARACTERS_INVENTORY_DELETE, character_id=character_id, item_id=item_id)

    # -------------------------------------------------------------------------
    # Health Methods
    # -------------------------------------------------------------------------

    def get_health(self, character_id: str) -> Health:
        """Get a character's health track.

        The same object appears as ``Character.health``. Re-fetch it after changing V5
        Stamina, which sets the track size.

        Args:
            character_id: The ID of the character.

        Returns:
            The character's Health.

        Raises:
            NotFoundError: If the character does not exist or has no health track.
            AuthorizationError: If you don't have access to the character.
        """
        return self._call(Routes.CHARACTERS_HEALTH_GET, character_id=character_id)

    def set_health(
        self,
        character_id: str,
        request: HealthStateSet | None = None,
        **kwargs,
    ) -> Health:
        """Replace a character's full health state, such as to correct a mistake.

        Every field is sent, so omitted fields reset to 0. Use ``apply_health_action`` for
        in-play changes.

        Args:
            character_id: The ID of the character.
            request: A HealthStateSet model, OR pass fields as keyword arguments.
            **kwargs: Fields for HealthStateSet if request is not provided.
                Accepts: extra_levels, damage (int >= 0).

        Returns:
            The updated Health.

        Raises:
            NotFoundError: If the character does not exist or has no health track.
            AuthorizationError: If you are not the character's player or a storyteller.
            RequestValidationError: If a value is negative or a field is unknown.
            ValidationError: If the damage exceeds the track size.
        """
        body = request if request is not None else self._validate_request(HealthStateSet, **kwargs)
        return self._call(
            Routes.CHARACTERS_HEALTH_SET,
            json=body.model_dump(mode="json"),
            character_id=character_id,
        )

    def apply_health_action(
        self,
        character_id: str,
        action: TrackerAction,
        *,
        amount: int = 1,
    ) -> Health:
        """Apply one in-play action to a character's health, such as taking damage.

        Health accepts ``damage``, ``heal``, and ``reset``. Damage past a full track and
        healing past 0 are dropped.

        Args:
            character_id: The ID of the character.
            action: The action to apply.
            amount: How many points to apply. Must be at least 1.

        Returns:
            The updated Health.

        Raises:
            NotFoundError: If the character does not exist or has no health track.
            AuthorizationError: If you are not the character's player or a storyteller.
            RequestValidationError: If ``amount`` is less than 1.
            ValidationError: If the action does not apply to health.
        """
        body = self._validate_request(_TrackerAction, action=action, amount=amount)
        return self._call(
            Routes.CHARACTERS_HEALTH_ACTION,
            json=body.model_dump(exclude_none=True, mode="json"),
            character_id=character_id,
        )
