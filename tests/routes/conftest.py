"""Fixtures shared by the route tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vweb.api_client.testing import CampaignFactory, CharacterFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from vweb.api_client.models import Campaign, Character
    from vweb.lib.cache.global_context import GlobalContext


@pytest.fixture
def set_role(
    use_context: Callable[..., GlobalContext], mock_campaign: Campaign
) -> Callable[..., GlobalContext]:
    """Return a function that signs the session user in with a role in `mock_campaign`."""

    def _set(role: str, *, characters: list[Character] | None = None) -> GlobalContext:
        return use_context(user_role=role, campaign=mock_campaign, characters=characters)

    return _set


@pytest.fixture
def admin_context(use_context: Callable[..., GlobalContext]) -> GlobalContext:
    """Sign the session user in as a company admin and return the context."""
    return use_context(user_role="ADMIN")


@pytest.fixture
def storyteller(set_role: Callable[..., GlobalContext], mock_campaign: Campaign) -> Campaign:
    """Sign the session user in as a storyteller of `mock_campaign` and return the campaign."""
    set_role("STORYTELLER")
    return mock_campaign


@pytest.fixture
def set_owner(use_context: Callable[..., GlobalContext]) -> Callable[[str], None]:
    """Return a function that puts char-123 in a player's context, owned by the given user."""

    def _set(owner_id: str) -> None:
        campaign = CampaignFactory.build(id="camp-456")
        character = CharacterFactory.build(
            id="char-123", campaign_id=campaign.id, user_player_id=owner_id
        )
        use_context(user_role="PLAYER", campaign=campaign, characters=[character])

    return _set
