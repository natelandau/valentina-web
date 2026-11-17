"""Tests for vweb.api_client.models.user_lookup."""

import pytest
from pydantic import ValidationError

from vweb.api_client.models.user_lookup import UserLookupResult


class TestUserLookupResult:
    """Tests for UserLookupResult model."""

    def test_valid_lookup_result(self):
        """Verify parsing a valid user lookup result."""
        # Given: Valid lookup result data
        data = {
            "company_id": "507f1f77bcf86cd799439011",
            "company_name": "My Game Shop",
            "user_id": "507f1f77bcf86cd799439022",
            "role": "PLAYER",
        }

        # When: Parsing the data
        result = UserLookupResult.model_validate(data)

        # Then: All fields are correctly parsed
        assert result.company_id == "507f1f77bcf86cd799439011"
        assert result.company_name == "My Game Shop"
        assert result.user_id == "507f1f77bcf86cd799439022"
        assert result.role == "PLAYER"

    @pytest.mark.parametrize(
        "role", ["ADMIN", "STORYTELLER", "PLAYER", "UNAPPROVED", "DEACTIVATED"]
    )
    def test_valid_roles(self, role):
        """Verify all valid UserRole values are accepted."""
        # Given: Lookup result with the given role
        data = {
            "company_id": "abc",
            "company_name": "Test Co",
            "user_id": "def",
            "role": role,
        }

        # When: Parsing the data
        result = UserLookupResult.model_validate(data)

        # Then: Role is correctly parsed
        assert result.role == role

    @pytest.mark.parametrize(
        ("data", "missing_field"),
        [
            ({"company_name": "X", "user_id": "Y", "role": "PLAYER"}, "company_id"),
            ({"company_id": "X", "user_id": "Y", "role": "PLAYER"}, "company_name"),
            ({"company_id": "X", "company_name": "Y", "role": "PLAYER"}, "user_id"),
            ({"company_id": "X", "company_name": "Y", "user_id": "Z"}, "role"),
        ],
    )
    def test_missing_required_field_raises(self, data, missing_field):
        """Verify missing required fields raise ValidationError."""
        # When/Then: Parsing raises ValidationError with field name
        with pytest.raises(ValidationError) as exc_info:
            UserLookupResult.model_validate(data)

        assert missing_field in str(exc_info.value)
