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
from vweb.api_client.endpoints import Endpoints
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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BLUEPRINT_SECTIONS),
            SheetSection,
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
        return list(
            self.iter_all_sections(game_version=game_version, character_class=character_class)
        )

    def iter_all_sections(
        self,
        *,
        game_version: GameVersion | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[SheetSection]:
        """Iterate through all character blueprint sections."""
        for section in self._iter_all_pages(
            self._format_endpoint(Endpoints.BLUEPRINT_SECTIONS),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version, character_class=character_class),
        ):
            yield SheetSection.model_validate(section)

    def get_section(self, *, section_id: str) -> SheetSection:
        """Get a character blueprint section by ID."""
        response = self._get(
            self._format_endpoint(
                Endpoints.BLUEPRINT_SECTION_DETAIL,
                section_id=section_id,
            ),
        )
        return SheetSection.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BLUEPRINT_CATEGORIES),
            TraitCategory,
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
        return list(
            self.iter_all_categories(
                game_version=game_version,
                section_id=section_id,
                character_class=character_class,
            )
        )

    def iter_all_categories(
        self,
        *,
        game_version: GameVersion | None = None,
        section_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[TraitCategory]:
        """Iterate through all character blueprint categories."""
        for category in self._iter_all_pages(
            self._format_endpoint(Endpoints.BLUEPRINT_CATEGORIES),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                section_id=section_id,
                character_class=character_class,
            ),
        ):
            yield TraitCategory.model_validate(category)

    def get_category(self, *, category_id: str) -> TraitCategory:
        """Get a character blueprint category by ID."""
        response = self._get(
            self._format_endpoint(
                Endpoints.BLUEPRINT_CATEGORY_DETAIL,
                category_id=category_id,
            ),
        )
        return TraitCategory.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BLUEPRINT_SUBCATEGORIES),
            TraitSubcategory,
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
        return list(
            self.iter_all_subcategories(
                game_version=game_version,
                category_id=category_id,
                character_class=character_class,
            )
        )

    def iter_all_subcategories(
        self,
        *,
        game_version: GameVersion | None = None,
        category_id: str | None = None,
        character_class: CharacterClass | None = None,
    ) -> Iterator[TraitSubcategory]:
        """Iterate through all character blueprint subcategories."""
        for subcategory in self._iter_all_pages(
            self._format_endpoint(Endpoints.BLUEPRINT_SUBCATEGORIES),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(
                game_version=game_version,
                category_id=category_id,
                character_class=character_class,
            ),
        ):
            yield TraitSubcategory.model_validate(subcategory)

    def get_subcategory(self, *, subcategory_id: str) -> TraitSubcategory:
        """Get a character blueprint subcategory by ID."""
        response = self._get(
            self._format_endpoint(
                Endpoints.BLUEPRINT_SUBCATEGORY_DETAIL,
                subcategory_id=subcategory_id,
            ),
        )
        return TraitSubcategory.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.BLUEPRINT_TRAITS),
            Trait,
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
        return list(
            self.iter_all_traits(
                game_version=game_version,
                character_class=character_class,
                category_id=category_id,
                subcategory_id=subcategory_id,
                is_rollable=is_rollable,
                order_by=order_by,
                exclude_subcategory_traits=exclude_subcategory_traits,
            )
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
        for trait in self._iter_all_pages(
            self._format_endpoint(Endpoints.BLUEPRINT_TRAITS),
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
        ):
            yield Trait.model_validate(trait)

    def get_trait(self, *, trait_id: str) -> Trait:
        """Get a character blueprint trait by ID."""
        response = self._get(
            self._format_endpoint(Endpoints.BLUEPRINT_TRAIT_DETAIL, trait_id=trait_id),
        )
        return Trait.model_validate(response.json())

    # Character Concepts

    def get_concepts_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[CharacterConcept]:
        """Get a paginated page of character concepts."""
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CONCEPTS),
            CharacterConcept,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
        )

    def list_all_concepts(self) -> list[CharacterConcept]:
        """List all character concepts."""
        return list(self.iter_all_concepts())

    def iter_all_concepts(self) -> Iterator[CharacterConcept]:
        """Iterate through all character concepts."""
        for concept in self._iter_all_pages(
            self._format_endpoint(Endpoints.CONCEPTS),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
        ):
            yield CharacterConcept.model_validate(concept)

    def get_concept(self, *, concept_id: str) -> CharacterConcept:
        """Get a character concept by ID."""
        response = self._get(
            self._format_endpoint(Endpoints.CONCEPT_DETAIL, concept_id=concept_id),
        )
        return CharacterConcept.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.VAMPIRE_CLANS),
            VampireClan,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_vampire_clans(
        self, *, game_version: GameVersion | None = None
    ) -> list[VampireClan]:
        """List all vampire clans."""
        return list(self.iter_all_vampire_clans(game_version=game_version))

    def iter_all_vampire_clans(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[VampireClan]:
        """Iterate through all vampire clans."""
        for clan in self._iter_all_pages(
            self._format_endpoint(Endpoints.VAMPIRE_CLANS),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        ):
            yield VampireClan.model_validate(clan)

    def get_vampire_clan(self, *, vampire_clan_id: str) -> VampireClan:
        """Get a vampire clan by ID."""
        response = self._get(
            self._format_endpoint(Endpoints.VAMPIRE_CLAN_DETAIL, vampire_clan_id=vampire_clan_id),
        )
        return VampireClan.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.WEREWOLF_AUSPICES),
            WerewolfAuspice,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_werewolf_auspices(
        self, *, game_version: GameVersion | None = None
    ) -> list[WerewolfAuspice]:
        """List all werewolf auspices."""
        return list(self.iter_all_werewolf_auspices(game_version=game_version))

    def iter_all_werewolf_auspices(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[WerewolfAuspice]:
        """Iterate through all werewolf auspices."""
        for auspice in self._iter_all_pages(
            self._format_endpoint(Endpoints.WEREWOLF_AUSPICES),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        ):
            yield WerewolfAuspice.model_validate(auspice)

    def get_werewolf_auspice(self, *, werewolf_auspice_id: str) -> WerewolfAuspice:
        """Get a werewolf auspice by ID."""
        response = self._get(
            self._format_endpoint(
                Endpoints.WEREWOLF_AUSPICE_DETAIL, werewolf_auspice_id=werewolf_auspice_id
            ),
        )
        return WerewolfAuspice.model_validate(response.json())

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
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.WEREWOLF_TRIBES),
            WerewolfTribe,
            limit=limit,
            offset=offset,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        )

    def list_all_werewolf_tribes(
        self, *, game_version: GameVersion | None = None
    ) -> list[WerewolfTribe]:
        """List all werewolf tribes."""
        return list(self.iter_all_werewolf_tribes(game_version=game_version))

    def iter_all_werewolf_tribes(
        self, *, game_version: GameVersion | None = None
    ) -> Iterator[WerewolfTribe]:
        """Iterate through all werewolf tribes."""
        for tribe in self._iter_all_pages(
            self._format_endpoint(Endpoints.WEREWOLF_TRIBES),
            limit=MAX_REFERENCE_PAGE_LIMIT,
            max_limit=MAX_REFERENCE_PAGE_LIMIT,
            params=self._build_params(game_version=game_version),
        ):
            yield WerewolfTribe.model_validate(tribe)

    def get_werewolf_tribe(self, *, werewolf_tribe_id: str) -> WerewolfTribe:
        """Get a werewolf tribe by ID."""
        response = self._get(
            self._format_endpoint(
                Endpoints.WEREWOLF_TRIBE_DETAIL, werewolf_tribe_id=werewolf_tribe_id
            ),
        )
        return WerewolfTribe.model_validate(response.json())
