"""Integration tests for CharacterBlueprintService."""

from collections.abc import Callable
from typing import Any

import pytest
import respx
from pydantic import BaseModel
from respx import MockResponse

from tests.api_client.payloads import endpoint_url, page, sent_params, wire
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    CharacterConcept,
    SheetSection,
    Trait,
    TraitCategory,
    TraitSubcategory,
    VampireClan,
    WerewolfAuspice,
    WerewolfTribe,
)
from vweb.api_client.testing import (
    CharacterConceptFactory,
    SheetSectionFactory,
    TraitCategoryFactory,
    TraitFactory,
    TraitSubcategoryFactory,
    VampireClanFactory,
    WerewolfAuspiceFactory,
    WerewolfTribeFactory,
)

COMPANY_ID = "company123"

# resource -> (factory, model, list endpoint, detail endpoint, get method, id kwarg)
RESOURCES: dict[str, tuple[Any, type[BaseModel], str, str, str, str]] = {
    "sections": (
        SheetSectionFactory,
        SheetSection,
        Endpoints.BLUEPRINT_SECTIONS,
        Endpoints.BLUEPRINT_SECTION_DETAIL,
        "get_section",
        "section_id",
    ),
    "categories": (
        TraitCategoryFactory,
        TraitCategory,
        Endpoints.BLUEPRINT_CATEGORIES,
        Endpoints.BLUEPRINT_CATEGORY_DETAIL,
        "get_category",
        "category_id",
    ),
    "subcategories": (
        TraitSubcategoryFactory,
        TraitSubcategory,
        Endpoints.BLUEPRINT_SUBCATEGORIES,
        Endpoints.BLUEPRINT_SUBCATEGORY_DETAIL,
        "get_subcategory",
        "subcategory_id",
    ),
    "traits": (
        TraitFactory,
        Trait,
        Endpoints.BLUEPRINT_TRAITS,
        Endpoints.BLUEPRINT_TRAIT_DETAIL,
        "get_trait",
        "trait_id",
    ),
    "concepts": (
        CharacterConceptFactory,
        CharacterConcept,
        Endpoints.CONCEPTS,
        Endpoints.CONCEPT_DETAIL,
        "get_concept",
        "concept_id",
    ),
    "vampire_clans": (
        VampireClanFactory,
        VampireClan,
        Endpoints.VAMPIRE_CLANS,
        Endpoints.VAMPIRE_CLAN_DETAIL,
        "get_vampire_clan",
        "vampire_clan_id",
    ),
    "werewolf_auspices": (
        WerewolfAuspiceFactory,
        WerewolfAuspice,
        Endpoints.WEREWOLF_AUSPICES,
        Endpoints.WEREWOLF_AUSPICE_DETAIL,
        "get_werewolf_auspice",
        "werewolf_auspice_id",
    ),
    "werewolf_tribes": (
        WerewolfTribeFactory,
        WerewolfTribe,
        Endpoints.WEREWOLF_TRIBES,
        Endpoints.WEREWOLF_TRIBE_DETAIL,
        "get_werewolf_tribe",
        "werewolf_tribe_id",
    ),
}

ALL_TRAIT_FILTERS = {
    "game_version": "V5",
    "character_class": "VAMPIRE",
    "category_id": "category123",
    "subcategory_id": "subcat123",
    "is_rollable": True,
    "order_by": "NAME",
    "exclude_subcategory_traits": True,
}
ALL_TRAIT_QUERY = {
    "game_version": "V5",
    "character_class": "VAMPIRE",
    "category_id": "category123",
    "subcategory_id": "subcat123",
    "is_rollable": "true",
    "order_by": "NAME",
    "exclude_subcategory_traits": "true",
}
PAGE = {"limit": "10", "offset": "0"}
REFERENCE_PAGE = {"limit": "1000", "offset": "0"}


def _consume(result: Any) -> list:
    """Return the items of a page, list, or iterator so every call is fully sent."""
    return result.items if hasattr(result, "items") else list(result)


@pytest.fixture
def service(vclient):
    """Return a CharacterBlueprintService scoped to the test company."""
    return vclient.character_blueprint("on-behalf-of-user", company_id=COMPANY_ID)


@pytest.mark.parametrize("resource", list(RESOURCES))
@respx.mock
def test_get_by_id(service, base_url, resource) -> None:
    """Verify each get method requests the resource by ID and parses it into its model."""
    # Given: A detail endpoint for the resource
    factory, model, _, detail_endpoint, method, id_kwarg = RESOURCES[resource]
    payload = wire(factory.build(id="item123"))
    respx.get(
        endpoint_url(base_url, detail_endpoint, company_id=COMPANY_ID, **{id_kwarg: "item123"})
    ).mock(return_value=MockResponse(200, json=payload))

    # When: Getting the resource by ID
    result = getattr(service, method)(**{id_kwarg: "item123"})

    # Then: The response parses into the resource's model
    assert result == model.model_validate(payload)


# (resource, call, expected query)
LIST_CASES: list[tuple[str, Callable[[Any], Any], dict[str, str]]] = [
    ("sections", lambda s: s.get_sections_page(), PAGE),
    (
        "sections",
        lambda s: s.get_sections_page(limit=50, offset=100),
        {"limit": "50", "offset": "100"},
    ),
    ("sections", lambda s: s.get_sections_page(limit=1000), REFERENCE_PAGE),
    (
        "sections",
        lambda s: s.get_sections_page(game_version="V5", character_class="VAMPIRE"),
        {**PAGE, "game_version": "V5", "character_class": "VAMPIRE"},
    ),
    (
        "sections",
        lambda s: s.list_all_sections(game_version="V5", character_class="VAMPIRE"),
        {**REFERENCE_PAGE, "game_version": "V5", "character_class": "VAMPIRE"},
    ),
    (
        "sections",
        lambda s: s.iter_all_sections(game_version="V5", character_class="VAMPIRE"),
        {**REFERENCE_PAGE, "game_version": "V5", "character_class": "VAMPIRE"},
    ),
    (
        "categories",
        lambda s: s.get_categories_page(
            game_version="V5", section_id="section123", character_class="VAMPIRE"
        ),
        {**PAGE, "game_version": "V5", "section_id": "section123", "character_class": "VAMPIRE"},
    ),
    (
        "categories",
        lambda s: s.list_all_categories(
            game_version="V5", section_id="section123", character_class="VAMPIRE"
        ),
        {
            **REFERENCE_PAGE,
            "game_version": "V5",
            "section_id": "section123",
            "character_class": "VAMPIRE",
        },
    ),
    (
        "categories",
        lambda s: s.iter_all_categories(
            game_version="V5", section_id="section123", character_class="VAMPIRE"
        ),
        {
            **REFERENCE_PAGE,
            "game_version": "V5",
            "section_id": "section123",
            "character_class": "VAMPIRE",
        },
    ),
    (
        "subcategories",
        lambda s: s.get_subcategories_page(
            game_version="V5", category_id="category123", character_class="VAMPIRE"
        ),
        {**PAGE, "game_version": "V5", "category_id": "category123", "character_class": "VAMPIRE"},
    ),
    (
        "subcategories",
        lambda s: s.list_all_subcategories(
            game_version="V5", category_id="category123", character_class="VAMPIRE"
        ),
        {
            **REFERENCE_PAGE,
            "game_version": "V5",
            "category_id": "category123",
            "character_class": "VAMPIRE",
        },
    ),
    (
        "subcategories",
        lambda s: s.iter_all_subcategories(
            game_version="V5", category_id="category123", character_class="VAMPIRE"
        ),
        {
            **REFERENCE_PAGE,
            "game_version": "V5",
            "category_id": "category123",
            "character_class": "VAMPIRE",
        },
    ),
    # exclude_subcategory_traits=False is left off the query, not sent as "false"
    ("traits", lambda s: s.get_traits_page(exclude_subcategory_traits=False), PAGE),
    ("traits", lambda s: s.get_traits_page(**ALL_TRAIT_FILTERS), {**PAGE, **ALL_TRAIT_QUERY}),
    (
        "traits",
        lambda s: s.list_all_traits(**ALL_TRAIT_FILTERS),
        {**REFERENCE_PAGE, **ALL_TRAIT_QUERY},
    ),
    (
        "traits",
        lambda s: s.iter_all_traits(**ALL_TRAIT_FILTERS),
        {**REFERENCE_PAGE, **ALL_TRAIT_QUERY},
    ),
    ("concepts", lambda s: s.get_concepts_page(), PAGE),
    ("concepts", lambda s: s.list_all_concepts(), REFERENCE_PAGE),
    ("concepts", lambda s: s.iter_all_concepts(), REFERENCE_PAGE),
    (
        "vampire_clans",
        lambda s: s.get_vampire_clans_page(game_version="V5"),
        {**PAGE, "game_version": "V5"},
    ),
    (
        "vampire_clans",
        lambda s: s.list_all_vampire_clans(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
    (
        "vampire_clans",
        lambda s: s.iter_all_vampire_clans(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_auspices",
        lambda s: s.get_werewolf_auspices_page(game_version="V5"),
        {**PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_auspices",
        lambda s: s.list_all_werewolf_auspices(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_auspices",
        lambda s: s.iter_all_werewolf_auspices(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_tribes",
        lambda s: s.get_werewolf_tribes_page(game_version="V5"),
        {**PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_tribes",
        lambda s: s.list_all_werewolf_tribes(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
    (
        "werewolf_tribes",
        lambda s: s.iter_all_werewolf_tribes(game_version="V5"),
        {**REFERENCE_PAGE, "game_version": "V5"},
    ),
]


@pytest.mark.parametrize(
    ("resource", "call", "expected_query"),
    LIST_CASES,
    ids=[f"{case[0]}-{i}" for i, case in enumerate(LIST_CASES)],
)
@respx.mock
def test_list_methods_send_filters_and_parse_items(
    service, base_url, resource, call, expected_query
) -> None:
    """Verify each list method sends its filters and page size and parses the resource model.

    The list_all and iter_all methods page with the 1000-item reference limit, not the
    100-item limit of other endpoints.
    """
    # Given: A list endpoint for the resource
    factory, model, list_endpoint, *_ = RESOURCES[resource]
    route = respx.get(endpoint_url(base_url, list_endpoint, company_id=COMPANY_ID)).mock(
        return_value=MockResponse(200, json=page(factory.build(id="item123")))
    )

    # When: Calling the list method
    items = _consume(call(service))

    # Then: The query holds exactly the filters and paging, and items parse
    assert sent_params(route) == expected_query
    assert [type(item) for item in items] == [model]
    assert items[0].id == "item123"
