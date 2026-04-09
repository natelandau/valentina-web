"""Tests for the dice roll service layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from vclient.testing import (
    CampaignFactory,
    CharacterFactory,
    CharacterTraitFactory,
    DicerollFactory,
    QuickrollFactory,
    Routes,
    TraitFactory,
    UserFactory,
)

from tests.conftest import make_dice_roll_result

if TYPE_CHECKING:
    from flask import Flask


# ===== RollContext Tests =====


class TestRollContext:
    """Tests for the RollContext dataclass."""

    def test_roll_context_defaults(self) -> None:
        """Verify RollContext initializes with correct default values."""
        from vweb.routes.diceroll.services import RollContext

        # Given character traits and quickrolls
        traits = CharacterTraitFactory.batch(2)
        quickrolls = QuickrollFactory.batch(1)

        # When creating a RollContext without explicit desperation
        ctx = RollContext(character_traits=traits, quickrolls=quickrolls)

        # Then desperation defaults to 0
        assert ctx.character_traits == traits
        assert ctx.quickrolls == quickrolls
        assert ctx.campaign_desperation == 0

    def test_roll_context_with_desperation(self) -> None:
        """Verify RollContext stores non-zero desperation."""
        from vweb.routes.diceroll.services import RollContext

        # Given traits and a non-zero desperation value
        traits = CharacterTraitFactory.batch(3)
        quickrolls = []

        # When creating a RollContext with desperation=2
        ctx = RollContext(character_traits=traits, quickrolls=quickrolls, campaign_desperation=2)

        # Then desperation is stored correctly
        assert ctx.campaign_desperation == 2


# ===== get_roll_context Tests =====


class TestGetRollContext:
    """Tests for the get_roll_context function."""

    def test_fetches_traits_and_quickrolls(self, app: Flask, fake_vclient) -> None:
        """Verify get_roll_context fetches traits and quickrolls and combines them."""
        from flask import g

        from vweb.routes.diceroll.services import get_roll_context

        # Given a character and campaign with known desperation
        character = CharacterFactory.build()
        campaign = CampaignFactory.build(desperation=3)
        user = UserFactory.build(id="test-user-id")
        traits = CharacterTraitFactory.batch(4)
        quickrolls = QuickrollFactory.batch(2)

        fake_vclient.set_response(Routes.CHARACTER_TRAITS_LIST, items=traits)
        fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=quickrolls)

        # When get_roll_context is called inside a request context
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            g.requesting_user = user
            result = get_roll_context(character=character, campaign=campaign)

        # Then the returned context contains all expected data
        assert result.character_traits == traits
        assert result.quickrolls == quickrolls
        assert result.campaign_desperation == 3

    def test_desperation_zero_when_zero(self, app: Flask, fake_vclient) -> None:
        """Verify get_roll_context passes through zero desperation correctly."""
        from flask import g

        from vweb.routes.diceroll.services import get_roll_context

        # Given a campaign with desperation=0
        character = CharacterFactory.build()
        campaign = CampaignFactory.build(desperation=0)
        user = UserFactory.build(id="test-user-id")

        fake_vclient.set_response(Routes.CHARACTER_TRAITS_LIST, items=[])
        fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[])

        # When get_roll_context is called
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            session["user_id"] = "test-user-id"
            g.requesting_user = user
            result = get_roll_context(character=character, campaign=campaign)

        # Then desperation is 0
        assert result.campaign_desperation == 0


# ===== perform_custom_roll Tests =====


class TestPerformCustomRoll:
    """Tests for the perform_custom_roll function."""

    def test_creates_custom_diceroll(self, app: Flask, fake_vclient) -> None:
        """Verify perform_custom_roll calls the API with correct parameters."""
        from flask import g

        from vweb.routes.diceroll.services import perform_custom_roll

        # Given a character and campaign
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        fake_vclient.set_response(Routes.DICEROLLS_CREATE, model=diceroll)

        # When perform_custom_roll is called
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_custom_roll(
                character=character,
                campaign=campaign,
                dice_size=10,
                num_dice=5,
                difficulty=6,
                comment="test roll",
            )

        # Then the returned Diceroll is the one from the API
        assert result.id == diceroll.id

    def test_custom_roll_without_comment(self, app: Flask, fake_vclient) -> None:
        """Verify perform_custom_roll works when comment is None."""
        from flask import g

        from vweb.routes.diceroll.services import perform_custom_roll

        # Given no comment is provided
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        fake_vclient.set_response(Routes.DICEROLLS_CREATE, model=diceroll)

        # When perform_custom_roll is called without a comment
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_custom_roll(
                character=character,
                campaign=campaign,
                dice_size=6,
                num_dice=3,
                difficulty=7,
            )

        # Then the call succeeds and returns the diceroll
        assert result.id == diceroll.id


# ===== perform_trait_roll Tests =====


class TestPerformTraitRoll:
    """Tests for the perform_trait_roll function."""

    def test_single_trait_roll(self, app: Flask, fake_vclient) -> None:
        """Verify perform_trait_roll sums one trait value and calls the API."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given a character with a known trait value
        trait = TraitFactory.build(id="trait-strength")
        char_trait = CharacterTraitFactory.build(value=4, trait=trait)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(result=make_dice_roll_result(total_result=2))

        fake_vclient.set_response(Routes.DICEROLLS_CREATE, model=diceroll)

        # When perform_trait_roll is called with one trait
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_trait_roll(
                character=character,
                campaign=campaign,
                character_traits=[char_trait],
                trait_one_id="trait-strength",
                difficulty=6,
            )

        # Then the diceroll is returned
        assert result.id == diceroll.id

    def test_two_trait_roll(self, app: Flask, fake_vclient) -> None:
        """Verify perform_trait_roll sums two trait values for the dice pool."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given two traits with known values
        trait1 = TraitFactory.build(id="trait-strength")
        trait2 = TraitFactory.build(id="trait-dexterity")
        char_trait1 = CharacterTraitFactory.build(value=3, trait=trait1)
        char_trait2 = CharacterTraitFactory.build(value=2, trait=trait2)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        fake_vclient.set_response(Routes.DICEROLLS_CREATE, model=diceroll)

        # When perform_trait_roll is called with two traits
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_trait_roll(
                character=character,
                campaign=campaign,
                character_traits=[char_trait1, char_trait2],
                trait_one_id="trait-strength",
                trait_two_id="trait-dexterity",
                difficulty=6,
            )

        # Then the diceroll is returned (pool = 3 + 2 = 5)
        assert result.id == diceroll.id

    def test_raises_if_trait_not_found(self, app: Flask, fake_vclient) -> None:
        """Verify perform_trait_roll raises ValueError when trait ID is not in character_traits."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given character_traits that do NOT include the requested trait
        trait = TraitFactory.build(id="trait-strength")
        char_trait = CharacterTraitFactory.build(value=4, trait=trait)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")

        # When perform_trait_roll is called with a non-existent trait_one_id
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            with pytest.raises(ValueError, match="trait-missing"):
                perform_trait_roll(
                    character=character,
                    campaign=campaign,
                    character_traits=[char_trait],
                    trait_one_id="trait-missing",
                    difficulty=6,
                )

    def test_raises_if_second_trait_not_found(self, app: Flask, fake_vclient) -> None:
        """Verify perform_trait_roll raises ValueError when trait_two_id is not in character_traits."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given only trait one is in character_traits
        trait1 = TraitFactory.build(id="trait-strength")
        char_trait1 = CharacterTraitFactory.build(value=3, trait=trait1)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")

        # When perform_trait_roll is called with a bad trait_two_id
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            with pytest.raises(ValueError, match="trait-missing-two"):
                perform_trait_roll(
                    character=character,
                    campaign=campaign,
                    character_traits=[char_trait1],
                    trait_one_id="trait-strength",
                    trait_two_id="trait-missing-two",
                    difficulty=6,
                )

    def test_trait_roll_always_uses_d10(self, app: Flask, fake_vclient, mocker) -> None:
        """Verify perform_trait_roll always passes dice_size=10 to the API."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given a character with a trait value of 3
        trait = TraitFactory.build(id="trait-strength")
        char_trait = CharacterTraitFactory.build(value=3, trait=trait)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(dice_size=10, result=make_dice_roll_result())

        # Mock the service to capture the request object
        mock_svc = mocker.MagicMock()
        mock_svc.create.return_value = diceroll
        mocker.patch("vweb.routes.diceroll.services.sync_dicerolls_service", return_value=mock_svc)

        # When perform_trait_roll is called
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            perform_trait_roll(
                character=character,
                campaign=campaign,
                character_traits=[char_trait],
                trait_one_id="trait-strength",
                difficulty=7,
            )

        # Then the request passed to create() has dice_size=10
        request_arg = mock_svc.create.call_args.args[0]
        assert request_arg.dice_size == 10

    def test_trait_roll_with_desperation_dice(self, app: Flask, fake_vclient, mocker) -> None:
        """Verify perform_trait_roll passes num_desperation_dice to the API."""
        from flask import g

        from vweb.routes.diceroll.services import perform_trait_roll

        # Given a character with a trait and desperation dice count
        trait = TraitFactory.build(id="trait-strength")
        char_trait = CharacterTraitFactory.build(value=3, trait=trait)
        character = CharacterFactory.build()
        campaign = CampaignFactory.build()
        user = UserFactory.build(id="test-user-id")
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        # Mock the service to capture the request object
        mock_svc = mocker.MagicMock()
        mock_svc.create.return_value = diceroll
        mocker.patch("vweb.routes.diceroll.services.sync_dicerolls_service", return_value=mock_svc)

        # When perform_trait_roll is called with desperation dice
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            perform_trait_roll(
                character=character,
                campaign=campaign,
                character_traits=[char_trait],
                trait_one_id="trait-strength",
                difficulty=6,
                num_desperation_dice=2,
            )

        # Then num_desperation_dice=2 was passed in the request
        request_arg = mock_svc.create.call_args.args[0]
        assert request_arg.num_desperation_dice == 2


# ===== perform_quickroll Tests =====


class TestPerformQuickroll:
    """Tests for the perform_quickroll function."""

    def test_creates_roll_from_quickroll(self, app: Flask, fake_vclient) -> None:
        """Verify perform_quickroll calls the API with the correct quickroll parameters."""
        from flask import g

        from vweb.routes.diceroll.services import perform_quickroll

        # Given a character and a quickroll
        character = CharacterFactory.build()
        user = UserFactory.build(id="test-user-id")
        quickroll = QuickrollFactory.build()
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        fake_vclient.set_response(Routes.DICEROLLS_QUICKROLL, model=diceroll)

        # When perform_quickroll is called
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_quickroll(
                character=character,
                quickroll_id=quickroll.id,
                difficulty=6,
            )

        # Then the returned diceroll is from the API
        assert result.id == diceroll.id

    def test_quickroll_with_desperation_and_comment(self, app: Flask, fake_vclient, mocker) -> None:
        """Verify perform_quickroll passes desperation dice and comment to the API."""
        from flask import g

        from vweb.routes.diceroll.services import perform_quickroll

        # Given a character, quickroll, desperation count, and comment
        character = CharacterFactory.build()
        user = UserFactory.build(id="test-user-id")
        quickroll = QuickrollFactory.build()
        diceroll = DicerollFactory.build(result=make_dice_roll_result())

        fake_vclient.set_response(Routes.DICEROLLS_QUICKROLL, model=diceroll)

        # Spy on create_from_quickroll to inspect kwargs
        mock_svc = mocker.MagicMock()
        mock_svc.create_from_quickroll.return_value = diceroll
        mocker.patch("vweb.routes.diceroll.services.sync_dicerolls_service", return_value=mock_svc)

        # When perform_quickroll is called with extra parameters
        with app.test_request_context("/"):
            from flask import session

            session["company_id"] = "test-company-id"
            g.requesting_user = user
            result = perform_quickroll(
                character=character,
                quickroll_id=quickroll.id,
                difficulty=7,
                num_desperation_dice=1,
                comment="boss fight",
            )

        # Then create_from_quickroll was called with the right kwargs
        mock_svc.create_from_quickroll.assert_called_once_with(
            quickroll_id=quickroll.id,
            character_id=character.id,
            difficulty=7,
            num_desperation_dice=1,
            comment="boss fight",
        )
        assert result.id == diceroll.id
