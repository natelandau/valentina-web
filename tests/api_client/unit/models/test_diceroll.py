"""Tests for vweb.api_client.models.diceroll."""

import pytest

from vweb.api_client.models import Diceroll, DicerollCreate


@pytest.fixture
def diceroll_payload() -> dict:
    """Return a minimal diceroll response payload."""
    return {
        "id": "diceroll123",
        "date_created": "2024-01-15T10:30:00Z",
        "date_modified": "2024-01-15T10:30:00Z",
        "dice_size": 10,
        "num_dice": 3,
        "company_id": "company123",
    }


class TestDiceroll:
    """Tests for the Diceroll response model."""

    def test_dice_modifier_defaults_to_zero(self, diceroll_payload):
        """Verify a payload without dice_modifier gives 0."""
        # When: Validating a payload with no dice_modifier
        roll = Diceroll.model_validate(diceroll_payload)

        # Then: The modifier is 0
        assert roll.dice_modifier == 0

    def test_dice_modifier_is_parsed(self, diceroll_payload):
        """Verify a negative dice_modifier is parsed."""
        # When: Validating a payload with a negative modifier
        roll = Diceroll.model_validate({**diceroll_payload, "dice_modifier": -2})

        # Then: The modifier is kept
        assert roll.dice_modifier == -2


class TestDicerollCreate:
    """Tests for the DicerollCreate request model."""

    def test_dice_modifier_defaults_to_zero(self):
        """Verify the request model defaults dice_modifier to 0."""
        assert DicerollCreate(dice_size=10, num_dice=2).dice_modifier == 0
