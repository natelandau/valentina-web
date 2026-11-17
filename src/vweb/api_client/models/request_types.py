"""Annotated field types for request bodies, matching the limits the API enforces."""

from typing import Annotated

from pydantic import Field

from vweb.api_client.constants import (
    MAX_CHARACTER_AGE,
    MAX_CUSTOM_FLAW_XP_COST,
    MAX_DICTIONARY_SYNONYMS,
    MAX_EXTRA_HEALTH_LEVELS,
    MAX_LONG_TEXT_LENGTH,
    MAX_NAME_LENGTH,
    MAX_PROVIDER_TOKEN_LENGTH,
    MAX_SYNONYM_LENGTH,
    MAX_TRAIT_VALUE,
    MAX_URL_LENGTH,
    MAX_VAMPIRE_GENERATION,
    MIN_CUSTOM_FLAW_XP_COST,
    MIN_VAMPIRE_GENERATION,
)

LongText = Annotated[str, Field(max_length=MAX_LONG_TEXT_LENGTH)]
LongText3 = Annotated[str, Field(min_length=3, max_length=MAX_LONG_TEXT_LENGTH)]
NameMax50 = Annotated[str, Field(max_length=MAX_NAME_LENGTH)]
Name3to50 = Annotated[str, Field(min_length=3, max_length=MAX_NAME_LENGTH)]
# The API accepts only http(s) links so a stored link can never run script when rendered.
Url = Annotated[str, Field(pattern=r"^[Hh][Tt][Tt][Pp][Ss]?://\S+$", max_length=MAX_URL_LENGTH)]
Synonym = Annotated[str, Field(min_length=1, max_length=MAX_SYNONYM_LENGTH, pattern=r"\S")]
Synonyms = Annotated[list[Synonym], Field(max_length=MAX_DICTIONARY_SYNONYMS)]
CustomFlawXPCost = Annotated[int, Field(ge=MIN_CUSTOM_FLAW_XP_COST, le=MAX_CUSTOM_FLAW_XP_COST)]
ProviderToken = Annotated[str, Field(min_length=1, max_length=MAX_PROVIDER_TOKEN_LENGTH)]
Generation = Annotated[int, Field(ge=MIN_VAMPIRE_GENERATION, le=MAX_VAMPIRE_GENERATION)]
TraitScore = Annotated[int, Field(ge=0, le=MAX_TRAIT_VALUE)]
ExtraHealthLevels = Annotated[int, Field(ge=0, le=MAX_EXTRA_HEALTH_LEVELS)]
CharacterAge = Annotated[int, Field(ge=0, le=MAX_CHARACTER_AGE)]
