"""Tests for the dice roll service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.conftest import make_dice_roll_result
from tests.helpers import seed_session
from vweb.api_client.testing import (
    CampaignFactory,
    CharacterFactory,
    CharacterTraitFactory,
    DicerollFactory,
    QuickrollFactory,
    Routes,
    TraitFactory,
    UserFactory,
)
from vweb.routes.diceroll.services import (
    get_roll_context,
    perform_custom_roll,
    perform_quickroll,
    perform_trait_roll,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

    from vweb.api_client.models import CharacterTrait


@pytest.fixture
def request_scope(app: Flask, fake_vclient) -> Iterator[None]:
    """Open a request context with a signed-in user and fake roll responses."""
    from flask import g

    fake_vclient.set_response(
        Routes.DICEROLLS_CREATE, model=DicerollFactory.build(result=make_dice_roll_result())
    )
    fake_vclient.set_response(
        Routes.DICEROLLS_QUICKROLL, model=DicerollFactory.build(result=make_dice_roll_result())
    )
    with app.test_request_context("/"):
        seed_session()
        g.requesting_user = UserFactory.build(id="test-user-id")
        yield


@pytest.fixture
def traits() -> list[CharacterTrait]:
    """Build a character's Strength 3 and Brawl 2."""
    return [
        CharacterTraitFactory.build(value=3, trait=TraitFactory.build(id="trait-str")),
        CharacterTraitFactory.build(value=2, trait=TraitFactory.build(id="trait-brawl")),
    ]


@pytest.mark.usefixtures("request_scope")
def test_get_roll_context_combines_traits_quickrolls_and_pools(fake_vclient, traits) -> None:
    """Verify the context carries the traits, quickrolls, desperation, and each quickroll's pool.

    A quickroll trait the character lacks counts as 0.
    """
    # Given a quickroll over Strength and a trait the character lacks
    quickroll = QuickrollFactory.build(id="qr-1", trait_ids=["trait-str", "trait-missing"])
    fake_vclient.set_response(Routes.CHARACTER_TRAITS_LIST, items=traits)
    fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[quickroll])

    # When building the roll context
    result = get_roll_context(
        character=CharacterFactory.build(), campaign=CampaignFactory.build(desperation=3)
    )

    # Then it carries everything the roll modal needs
    assert result.character_traits == traits
    assert result.quickrolls == [quickroll]
    assert result.campaign_desperation == 3
    assert result.quickroll_pools == {"qr-1": 3}


@pytest.mark.usefixtures("request_scope")
def test_custom_roll_sends_requested_pool(fake_vclient) -> None:
    """Verify a custom roll sends the chosen die size, pool, difficulty, and comment."""
    character = CharacterFactory.build()
    campaign = CampaignFactory.build()

    perform_custom_roll(
        character=character,
        campaign=campaign,
        dice_size=6,
        num_dice=5,
        difficulty=7,
        comment="test roll",
    )

    fake_vclient.assert_called(
        Routes.DICEROLLS_CREATE,
        json_subset={
            "dice_size": 6,
            "num_dice": 5,
            "difficulty": 7,
            "comment": "test roll",
            "character_id": character.id,
            "campaign_id": campaign.id,
        },
        times=1,
    )


@pytest.mark.parametrize(
    ("trait_two_id", "expected_pool", "expected_trait_ids"),
    [(None, 3, ["trait-str"]), ("trait-brawl", 5, ["trait-str", "trait-brawl"])],
    ids=["one-trait", "two-traits"],
)
@pytest.mark.usefixtures("request_scope")
def test_trait_roll_sends_d10_pool_from_stored_trait_values(
    fake_vclient, traits, trait_two_id, expected_pool, expected_trait_ids
) -> None:
    """Verify the pool is the stored trait values summed, rolled on d10s, with extras forwarded."""
    perform_trait_roll(
        character=CharacterFactory.build(),
        campaign=CampaignFactory.build(),
        character_traits=traits,
        trait_one_id="trait-str",
        trait_two_id=trait_two_id,
        difficulty=7,
        num_desperation_dice=2,
        dice_modifier=1,
    )

    fake_vclient.assert_called(
        Routes.DICEROLLS_CREATE,
        json_subset={
            "dice_size": 10,
            "num_dice": expected_pool,
            "difficulty": 7,
            "num_desperation_dice": 2,
            "dice_modifier": 1,
            "trait_ids": expected_trait_ids,
        },
        times=1,
    )


@pytest.mark.parametrize(
    ("trait_one_id", "trait_two_id"),
    [("trait-missing", None), ("trait-str", "trait-missing")],
    ids=["first-trait", "second-trait"],
)
@pytest.mark.usefixtures("request_scope")
def test_trait_roll_rejects_trait_the_character_lacks(
    fake_vclient, traits, trait_one_id, trait_two_id
) -> None:
    """Verify a trait the character does not have raises and nothing is rolled."""
    with pytest.raises(ValueError, match="trait-missing"):
        perform_trait_roll(
            character=CharacterFactory.build(),
            campaign=CampaignFactory.build(),
            character_traits=traits,
            trait_one_id=trait_one_id,
            trait_two_id=trait_two_id,
            difficulty=6,
        )

    fake_vclient.assert_not_called(Routes.DICEROLLS_CREATE)


@pytest.mark.parametrize(
    ("extras", "expected_extras"),
    [
        (
            {"num_desperation_dice": 1, "comment": "boss fight"},
            {"num_desperation_dice": 1, "dice_modifier": 0, "comment": "boss fight"},
        ),
        ({"dice_modifier": -2}, {"num_desperation_dice": 0, "dice_modifier": -2}),
    ],
    ids=["desperation-and-comment", "modifier-without-comment"],
)
@pytest.mark.usefixtures("request_scope")
def test_quickroll_sends_template_and_extras(fake_vclient, extras, expected_extras) -> None:
    """Verify a quickroll sends the template, character, difficulty, and optional extras."""
    character = CharacterFactory.build()

    perform_quickroll(character=character, quickroll_id="qr-1", difficulty=7, **extras)

    fake_vclient.assert_called(
        Routes.DICEROLLS_QUICKROLL,
        json={
            "quickroll_id": "qr-1",
            "character_id": character.id,
            "difficulty": 7,
            **expected_extras,
        },
        times=1,
    )
