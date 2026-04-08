"""Tests for QuickrollHandler service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from vclient.testing import TraitFactory

from vweb.routes.profile.handlers import QuickrollDisplay, QuickrollHandler


@pytest.fixture
def mock_user_svc(mocker):
    """Mock the sync_users_service for the handler module."""
    svc = MagicMock()
    mocker.patch("vweb.routes.profile.handlers.sync_users_service", return_value=svc)
    return svc


@pytest.fixture
def mock_get_all_traits(mocker):
    """Mock the get_all_traits function from blueprint_cache."""
    return mocker.patch("vweb.routes.profile.handlers.get_all_traits")


def _make_quickroll(
    *, id: str, name: str, description: str | None = None, trait_ids: list[str]
) -> MagicMock:
    """Build a MagicMock quickroll with the given attributes."""
    qr = MagicMock()
    qr.id = id
    qr.name = name
    qr.description = description
    qr.trait_ids = trait_ids
    return qr


class TestListItems:
    """Tests for QuickrollHandler.list_items()."""

    def test_two_traits_resolved(self, app, mock_user_svc, mock_get_all_traits) -> None:
        """Verify list_items resolves both trait names from the blueprint cache."""
        with app.test_request_context():
            # Given a quickroll with two trait IDs
            qr = _make_quickroll(
                id="qr-1", name="Attack", description="Quick attack", trait_ids=["t1", "t2"]
            )
            mock_user_svc.list_all_quickrolls.return_value = [qr]

            trait1 = TraitFactory.build(id="t1", name="Strength")
            trait2 = TraitFactory.build(id="t2", name="Brawl")
            mock_get_all_traits.return_value = {"t1": trait1, "t2": trait2}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then one QuickrollDisplay is returned with both trait names
            assert len(result) == 1
            assert isinstance(result[0], QuickrollDisplay)
            assert result[0].name == "Attack"
            assert result[0].description == "Quick attack"
            assert result[0].trait_one_name == "Strength"
            assert result[0].trait_two_name == "Brawl"

    def test_one_trait_resolved(self, app, mock_user_svc, mock_get_all_traits) -> None:
        """Verify list_items handles a quickroll with only one trait."""
        with app.test_request_context():
            # Given a quickroll with one trait ID
            qr = _make_quickroll(id="qr-2", name="Dodge", trait_ids=["t1"])
            mock_user_svc.list_all_quickrolls.return_value = [qr]

            trait1 = TraitFactory.build(id="t1", name="Dexterity")
            mock_get_all_traits.return_value = {"t1": trait1}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then one trait name is resolved and the other defaults to dash
            assert result[0].trait_one_name == "Dexterity"
            assert result[0].trait_two_name == "-"

    def test_zero_traits(self, app, mock_user_svc, mock_get_all_traits) -> None:
        """Verify list_items handles a quickroll with no traits."""
        with app.test_request_context():
            # Given a quickroll with no trait IDs
            qr = _make_quickroll(id="qr-3", name="Empty", trait_ids=[])
            mock_user_svc.list_all_quickrolls.return_value = [qr]
            mock_get_all_traits.return_value = {}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then both trait names default to dash
            assert result[0].trait_one_name == "-"
            assert result[0].trait_two_name == "-"

    def test_unknown_trait_returns_dash(self, app, mock_user_svc, mock_get_all_traits) -> None:
        """Verify trait resolution falls back to dash when trait ID is not found."""
        with app.test_request_context():
            # Given a quickroll with an unknown trait ID
            qr = _make_quickroll(id="qr-5", name="Broken", trait_ids=["bad-id"])
            mock_user_svc.list_all_quickrolls.return_value = [qr]
            mock_get_all_traits.return_value = {}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then the trait name defaults to dash
            assert result[0].trait_one_name == "-"


class TestCrudOperations:
    """Tests for QuickrollHandler create, update, delete, and get_item."""

    def test_create_item_delegates_to_service(self, app, mock_user_svc) -> None:
        """Verify create_item calls the service with correct arguments."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When creating a quickroll
            handler.create_item(
                {
                    "name": "  Attack Roll  ",
                    "description": "  Quick attack  ",
                    "trait_one_id": "t1",
                    "trait_two_id": "t2",
                }
            )

            # Then the service is called with stripped values and trait IDs list
            call_args = mock_user_svc.create_quickroll.call_args
            assert call_args[0][0] == "user-1"
            request = call_args[1]["request"]
            assert request.name == "Attack Roll"
            assert request.description == "Quick attack"
            assert request.trait_ids == ["t1", "t2"]

    def test_create_item_omits_empty_description(self, app, mock_user_svc) -> None:
        """Verify create_item sets description to None when empty."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When creating with empty description
            handler.create_item({"name": "Roll", "description": "", "trait_one_id": "t1"})

            # Then description is None
            request = mock_user_svc.create_quickroll.call_args[1]["request"]
            assert request.description is None

    def test_create_item_filters_empty_trait_ids(self, app, mock_user_svc) -> None:
        """Verify create_item excludes empty trait ID strings."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When creating with one empty trait ID
            handler.create_item(
                {
                    "name": "Roll",
                    "trait_one_id": "t1",
                    "trait_two_id": "",
                }
            )

            # Then only the non-empty trait ID is included
            request = mock_user_svc.create_quickroll.call_args[1]["request"]
            assert request.trait_ids == ["t1"]

    def test_update_item_delegates_to_service(self, app, mock_user_svc) -> None:
        """Verify update_item calls the service with correct arguments."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When updating a quickroll
            handler.update_item(
                "qr-1",
                {
                    "name": "Updated",
                    "description": "New desc",
                    "trait_one_id": "t3",
                    "trait_two_id": "t4",
                },
            )

            # Then the service is called with the quickroll ID and updated data
            call_args = mock_user_svc.update_quickroll.call_args
            assert call_args[0] == ("user-1", "qr-1")
            request = call_args[1]["request"]
            assert request.name == "Updated"
            assert request.trait_ids == ["t3", "t4"]

    def test_delete_item_delegates_to_service(self, app, mock_user_svc) -> None:
        """Verify delete_item calls the service with correct IDs."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When deleting a quickroll
            handler.delete_item("qr-1")

            # Then the service is called
            mock_user_svc.delete_quickroll.assert_called_once_with("user-1", "qr-1")

    def test_get_item_delegates_to_service(self, app, mock_user_svc) -> None:
        """Verify get_item calls the service with correct IDs."""
        with app.test_request_context():
            handler = QuickrollHandler("user-1")

            # When getting a quickroll
            handler.get_item("qr-1")

            # Then the service is called
            mock_user_svc.get_quickroll.assert_called_once_with("user-1", "qr-1")


class TestValidate:
    """Tests for QuickrollHandler.validate()."""

    def test_missing_name_rejected(self) -> None:
        """Verify validation rejects an empty name."""
        # Given a handler instance
        handler = QuickrollHandler.__new__(QuickrollHandler)

        # When validating with empty name
        errors = handler.validate({"name": "", "trait_one_id": "t1"})

        # Then a name error is returned
        assert "Name is required" in errors

    def test_whitespace_only_name_rejected(self) -> None:
        """Verify validation rejects a whitespace-only name."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "   "})

        assert "Name is required" in errors

    def test_valid_data_accepted(self) -> None:
        """Verify validation accepts valid form data."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "Attack Roll", "trait_one_id": "trait-1"})

        assert errors == []

    def test_no_traits_rejected(self) -> None:
        """Verify validation rejects form data with no traits selected."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "Attack Roll"})

        assert "At least one trait is required" in errors
