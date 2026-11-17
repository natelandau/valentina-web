"""Service for interacting with the Character Blueprint API."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_REFERENCE_PAGE_LIMIT,
    BlueprintTraitOrderBy,
    CharacterClass,
    GameVersion,
)
from vweb.api_client.models import (
    CharacterConcept,
    PaginatedResponse,
    SheetSection,
    Trait,
    TraitCategory,
    TraitSubcategory,
    VampireClan,
    WerewolfAuspice,
    WerewolfTribe,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class CharacterBlueprintService(BaseService):
    """Service for interacting with the Character Blueprint API."""

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str | None = None) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client, on_behalf_of=on_behalf_of, company_id=company_id)

    # Character Sheet Sections

    def get_sections_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
    ) -> PaginatedResponse[SheetSection]:
        """Get a paginated page of character blueprint sections."""
        return self._page(
            Routes.BLUEPRINT_SECTIONS_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version, character_class=character_class),
        )

    def list_all_sections(
        self,
        *,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
    ) -> list[SheetSection]:
        """List all character blueprint sections."""
        return self._list_all(
            Routes.BLUEPRINT_SECTIONS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version, character_class=character_class),
        )

    def iter_all_sections(
        self,
        *,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[SheetSection]:
        """Iterate through all character blueprint sections."""
        yield from self._iter(
            Routes.BLUEPRINT_SECTIONS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version, character_class=character_class),
        )

    def get_section(self, *, section_id: str) -> SheetSection:
        """Get a character blueprint section by ID."""
        return self._call(Routes.BLUEPRINT_SECTIONS_GET, section_id=section_id)

    # Character Sheet Categories

    def get_categories_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
        section_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> PaginatedResponse[TraitCategory]:
        """Get a paginated page of character blueprint categories."""
        return self._page(
            Routes.BLUEPRINT_CATEGORIES_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                section_id=section_id,
                character_class=character_class,
            ),
        )

    def list_all_categories(
        self,
        *,
        game_version: GameVersion | None = None,
        section_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> list[TraitCategory]:
        """List all character blueprint categories."""
        return self._list_all(
            Routes.BLUEPRINT_CATEGORIES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                section_id=section_id,
                character_class=character_class,
            ),
        )

    def iter_all_categories(
        self,
        *,
        game_version: GameVersion | None = None,
        section_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[TraitCategory]:
        """Iterate through all character blueprint categories."""
        yield from self._iter(
            Routes.BLUEPRINT_CATEGORIES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                section_id=section_id,
                character_class=character_class,
            ),
        )

    def get_category(self, *, category_id: str) -> TraitCategory:
        """Get a character blueprint category by ID."""
        return self._call(Routes.BLUEPRINT_CATEGORIES_GET, category_id=category_id)

    # Character Sheet Subcategories

    def get_subcategories_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
        category_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> PaginatedResponse[TraitSubcategory]:
        """Get a paginated page of character blueprint subcategories."""
        return self._page(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                category_id=category_id,
                character_class=character_class,
            ),
        )

    def list_all_subcategories(
        self,
        *,
        game_version: GameVersion | None = None,
        category_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> list[TraitSubcategory]:
        """List all character blueprint subcategories."""
        return self._list_all(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                category_id=category_id,
                character_class=character_class,
            ),
        )

    def iter_all_subcategories(
        self,
        *,
        game_version: GameVersion | None = None,
        category_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[TraitSubcategory]:
        """Iterate through all character blueprint subcategories."""
        yield from self._iter(
            Routes.BLUEPRINT_SUBCATEGORIES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                category_id=category_id,
                character_class=character_class,
            ),
        )

    def get_subcategory(self, *, subcategory_id: str) -> TraitSubcategory:
        """Get a character blueprint subcategory by ID."""
        return self._call(Routes.BLUEPRINT_SUBCATEGORIES_GET, subcategory_id=subcategory_id)

    # Character Traits

    def get_traits_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
        category_id: str | None = None,
        subcategory_id: str | None = None,
        is_rollable: bool | None = None,
        order_by: BlueprintTraitOrderBy | None = None,
        exclude_subcategory_traits: bool = False,
    ) -> PaginatedResponse[Trait]:
        """Get a paginated page of character blueprint traits."""
        return self._page(
            Routes.BLUEPRINT_TRAITS_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                character_class=character_class,
                category_id=category_id,
                subcategory_id=subcategory_id,
                is_rollable=is_rollable,
                order_by=order_by,
                game_version=game_version,
                exclude_subcategory_traits=exclude_subcategory_traits or None,
            ),
        )

    def list_all_traits(
        self,
        *,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
        category_id: str | None = None,
        subcategory_id: str | None = None,
        is_rollable: bool | None = None,
        order_by: BlueprintTraitOrderBy | None = None,
        exclude_subcategory_traits: bool = False,
    ) -> list[Trait]:
        """List all character blueprint traits."""
        return self._list_all(
            Routes.BLUEPRINT_TRAITS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                character_class=character_class,
                category_id=category_id,
                subcategory_id=subcategory_id,
                is_rollable=is_rollable,
                order_by=order_by,
                game_version=game_version,
                exclude_subcategory_traits=exclude_subcategory_traits or None,
            ),
        )

    def iter_all_traits(
        self,
        *,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
        category_id: str | None = None,
        subcategory_id: str | None = None,
        is_rollable: bool | None = None,
        order_by: BlueprintTraitOrderBy | None = None,
        exclude_subcategory_traits: bool = False,
    ) -> Iterator[Trait]:
        """Iterate through all character blueprint traits."""
        yield from self._iter(
            Routes.BLUEPRINT_TRAITS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                character_class=character_class,
                category_id=category_id,
                subcategory_id=subcategory_id,
                is_rollable=is_rollable,
                order_by=order_by,
                game_version=game_version,
                exclude_subcategory_traits=exclude_subcategory_traits or None,
            ),
        )

    def get_trait(self, *, trait_id: str) -> Trait:
        """Get a character blueprint trait by ID."""
        return self._call(Routes.BLUEPRINT_TRAITS_GET, trait_id=trait_id)

    # Character Concepts

    def get_concepts_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[CharacterConcept]:
        """Get a paginated page of character concepts."""
        return self._page(
            Routes.BLUEPRINT_CONCEPTS_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
        )

    def list_all_concepts(self) -> list[CharacterConcept]:
        """List all character concepts."""
        return self._list_all(
            Routes.BLUEPRINT_CONCEPTS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
        )

    def iter_all_concepts(self) -> Iterator[CharacterConcept]:
        """Iterate through all character concepts."""
        yield from self._iter(
            Routes.BLUEPRINT_CONCEPTS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
        )

    def get_concept(self, *, concept_id: str) -> CharacterConcept:
        """Get a character concept by ID."""
        return self._call(Routes.BLUEPRINT_CONCEPTS_GET, concept_id=concept_id)

    # -----------------------------------------------------------------------------
    # Vampire Clans
    # -----------------------------------------------------------------------------
    def get_vampire_clans_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
    ) -> PaginatedResponse[VampireClan]:
        """Get a paginated page of vampire clans."""
        return self._page(
            Routes.BLUEPRINT_VAMPIRE_CLANS_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_vampire_clans(
        self, *, game_version: GameVersion | None = None
    ) -> list[VampireClan]:
        """List all vampire clans."""
        return self._list_all(
            Routes.BLUEPRINT_VAMPIRE_CLANS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def iter_all_vampire_clans(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[VampireClan]:
        """Iterate through all vampire clans."""
        yield from self._iter(
            Routes.BLUEPRINT_VAMPIRE_CLANS_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def get_vampire_clan(self, *, vampire_clan_id: str) -> VampireClan:
        """Get a vampire clan by ID."""
        return self._call(Routes.BLUEPRINT_VAMPIRE_CLANS_GET, vampire_clan_id=vampire_clan_id)

    # -----------------------------------------------------------------------------
    # Werewolf Auspices
    # -----------------------------------------------------------------------------
    def get_werewolf_auspices_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
    ) -> PaginatedResponse[WerewolfAuspice]:
        """Get a paginated page of werewolf auspices."""
        return self._page(
            Routes.BLUEPRINT_WEREWOLF_AUSPICES_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_werewolf_auspices(
        self, *, game_version: GameVersion | None = None
    ) -> list[WerewolfAuspice]:
        """List all werewolf auspices."""
        return self._list_all(
            Routes.BLUEPRINT_WEREWOLF_AUSPICES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def iter_all_werewolf_auspices(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[WerewolfAuspice]:
        """Iterate through all werewolf auspices."""
        yield from self._iter(
            Routes.BLUEPRINT_WEREWOLF_AUSPICES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def get_werewolf_auspice(self, *, werewolf_auspice_id: str) -> WerewolfAuspice:
        """Get a werewolf auspice by ID."""
        return self._call(
            Routes.BLUEPRINT_WEREWOLF_AUSPICES_GET, werewolf_auspice_id=werewolf_auspice_id
        )

    # -----------------------------------------------------------------------------
    # Werewolf Tribes
    # -----------------------------------------------------------------------------
    def get_werewolf_tribes_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        game_version: GameVersion | None = None,
    ) -> PaginatedResponse[WerewolfTribe]:
        """Get a paginated page of werewolf tribes."""
        return self._page(
            Routes.BLUEPRINT_WEREWOLF_TRIBES_LIST,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_werewolf_tribes(
        self, *, game_version: GameVersion | None = None
    ) -> list[WerewolfTribe]:
        """List all werewolf tribes."""
        return self._list_all(
            Routes.BLUEPRINT_WEREWOLF_TRIBES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def iter_all_werewolf_tribes(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[WerewolfTribe]:
        """Iterate through all werewolf tribes."""
        yield from self._iter(
            Routes.BLUEPRINT_WEREWOLF_TRIBES_LIST,
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def get_werewolf_tribe(self, *, werewolf_tribe_id: str) -> WerewolfTribe:
        """Get a werewolf tribe by ID."""
        return self._call(Routes.BLUEPRINT_WEREWOLF_TRIBES_GET, werewolf_tribe_id=werewolf_tribe_id)
