"""Tests for QuickrollHandler service."""

from __future__ import annotations

import pytest

from tests.helpers import seed_session
from vweb.api_client.testing import QuickrollFactory, Routes, TraitFactory
from vweb.routes.profile.handlers import QuickrollDisplay, QuickrollHandler


@pytest.fixture
def mock_get_all_traits(mocker):
    """Mock the blueprint traits cache for quickroll handler tests."""
    return mocker.patch("vweb.lib.cache.blueprint.traits")


class TestListItems:
    """Tests for QuickrollHandler.list_items()."""

    def test_two_traits_resolved(self, app, fake_vclient, mock_get_all_traits) -> None:
        """Verify list_items resolves both trait names from the blueprint cache."""
        with app.test_request_context("/"):
            seed_session()
            # Given a quickroll with two trait IDs
            qr = QuickrollFactory.build(
                id="qr-1", name="Attack", description="Quick attack", trait_ids=["t1", "t2"]
            )
            fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[qr])

            trait1 = TraitFactory.build(id="t1", name="Strength")
            trait2 = TraitFactory.build(id="t2", name="Brawl")
            mock_get_all_traits.return_value = {"t1": trait1, "t2": trait2}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then the user's quickrolls are fetched and one QuickrollDisplay is returned
            fake_vclient.assert_called(Routes.USERS_QUICKROLLS_LIST, params={"user_id": "user-1"})
            assert len(result) == 1
            assert isinstance(result[0], QuickrollDisplay)
            assert result[0].name == "Attack"
            assert result[0].description == "Quick attack"
            assert result[0].trait_one_name == "Strength"
            assert result[0].trait_two_name == "Brawl"

    def test_one_trait_resolved(self, app, fake_vclient, mock_get_all_traits) -> None:
        """Verify list_items handles a quickroll with only one trait."""
        with app.test_request_context("/"):
            seed_session()
            # Given a quickroll with one trait ID
            qr = QuickrollFactory.build(id="qr-2", name="Dodge", trait_ids=["t1"])
            fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[qr])

            trait1 = TraitFactory.build(id="t1", name="Dexterity")
            mock_get_all_traits.return_value = {"t1": trait1}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then one trait name is resolved and the other defaults to dash
            assert result[0].trait_one_name == "Dexterity"
            assert result[0].trait_two_name == "-"

    def test_zero_traits(self, app, fake_vclient, mock_get_all_traits) -> None:
        """Verify list_items handles a quickroll with no traits."""
        with app.test_request_context("/"):
            seed_session()
            # Given a quickroll with no trait IDs
            qr = QuickrollFactory.build(id="qr-3", name="Empty", trait_ids=[])
            fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[qr])
            mock_get_all_traits.return_value = {}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then both trait names default to dash
            assert result[0].trait_one_name == "-"
            assert result[0].trait_two_name == "-"

    def test_unknown_trait_returns_dash(self, app, fake_vclient, mock_get_all_traits) -> None:
        """Verify trait resolution falls back to dash when trait ID is not found."""
        with app.test_request_context("/"):
            seed_session()
            # Given a quickroll with an unknown trait ID
            qr = QuickrollFactory.build(id="qr-5", name="Broken", trait_ids=["bad-id"])
            fake_vclient.set_response(Routes.USERS_QUICKROLLS_LIST, items=[qr])
            mock_get_all_traits.return_value = {}

            handler = QuickrollHandler("user-1")

            # When listing items
            result = handler.list_items()

            # Then the trait name defaults to dash
            assert result[0].trait_one_name == "-"


class TestCrudOperations:
    """Tests for QuickrollHandler create, update, delete, and get_item."""

    def test_create_item_delegates_to_service(self, app, fake_vclient) -> None:
        """Verify create_item sends the parsed form to the API."""
        with app.test_request_context("/"):
            seed_session()
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

            # Then the API receives stripped values and the trait IDs list for the user
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_CREATE,
                params={"user_id": "user-1"},
                json={
                    "name": "Attack Roll",
                    "description": "Quick attack",
                    "trait_ids": ["t1", "t2"],
                },
                times=1,
            )

    def test_create_item_omits_empty_description(self, app, fake_vclient) -> None:
        """Verify create_item omits an empty description."""
        with app.test_request_context("/"):
            seed_session()
            handler = QuickrollHandler("user-1")

            # When creating with empty description
            handler.create_item({"name": "Roll", "description": "", "trait_one_id": "t1"})

            # Then no description is sent
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_CREATE,
                json={"name": "Roll", "trait_ids": ["t1"]},
                times=1,
            )

    def test_create_item_filters_empty_trait_ids(self, app, fake_vclient) -> None:
        """Verify create_item excludes empty trait ID strings."""
        with app.test_request_context("/"):
            seed_session()
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
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_CREATE, json_subset={"trait_ids": ["t1"]}, times=1
            )

    def test_update_item_delegates_to_service(self, app, fake_vclient) -> None:
        """Verify update_item sends the parsed form to the quickroll's API path."""
        with app.test_request_context("/"):
            seed_session()
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

            # Then the API receives the updated data for that user's quickroll
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_UPDATE,
                params={"user_id": "user-1", "quickroll_id": "qr-1"},
                json_subset={"name": "Updated", "trait_ids": ["t3", "t4"]},
                times=1,
            )

    def test_update_item_clears_empty_description(self, app, fake_vclient) -> None:
        """Verify update_item sends an empty description, which the API stores as cleared."""
        with app.test_request_context("/"):
            seed_session()
            handler = QuickrollHandler("user-1")

            # When updating with a blank description
            handler.update_item(
                "qr-1", {"name": "Updated", "description": "   ", "trait_one_id": "t3"}
            )

            # Then the API receives an empty description
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_UPDATE,
                params={"user_id": "user-1", "quickroll_id": "qr-1"},
                json_subset={"description": ""},
                times=1,
            )

    def test_delete_item_delegates_to_service(self, app, fake_vclient) -> None:
        """Verify delete_item deletes the quickroll through the API."""
        with app.test_request_context("/"):
            seed_session()
            handler = QuickrollHandler("user-1")

            # When deleting a quickroll
            handler.delete_item("qr-1")

            # Then the API receives a delete for that user's quickroll
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_DELETE,
                params={"user_id": "user-1", "quickroll_id": "qr-1"},
                times=1,
            )

    def test_get_item_delegates_to_service(self, app, fake_vclient) -> None:
        """Verify get_item fetches the quickroll through the API."""
        with app.test_request_context("/"):
            seed_session()
            handler = QuickrollHandler("user-1")

            # When getting a quickroll
            handler.get_item("qr-1")

            # Then the API receives a fetch for that user's quickroll
            fake_vclient.assert_called(
                Routes.USERS_QUICKROLLS_GET,
                params={"user_id": "user-1", "quickroll_id": "qr-1"},
                times=1,
            )


class TestValidate:
    """Tests for QuickrollHandler.validate()."""

    def test_missing_name_rejected(self) -> None:
        """Verify validation rejects an empty name."""
        # Given a handler instance
        handler = QuickrollHandler.__new__(QuickrollHandler)

        # When validating with empty name
        errors = handler.validate({"name": "", "trait_one_id": "t1"})

        # Then a name error is returned
        assert errors["name"] == "Name is required"

    def test_whitespace_only_name_rejected(self) -> None:
        """Verify validation rejects a whitespace-only name."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "   "})

        assert errors["name"] == "Name is required"

    def test_valid_data_accepted(self) -> None:
        """Verify validation accepts valid form data."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "Attack Roll", "trait_one_id": "trait-1"})

        assert errors == {}

    def test_no_traits_rejected(self) -> None:
        """Verify validation rejects form data with no traits selected."""
        handler = QuickrollHandler.__new__(QuickrollHandler)

        errors = handler.validate({"name": "Attack Roll"})

        assert errors["_general"] == "At least one trait is required"
