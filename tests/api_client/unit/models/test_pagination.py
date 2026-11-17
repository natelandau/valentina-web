"""Tests for vweb.api_client.api.models.pagination."""

import pytest

from vweb.api_client.models.pagination import PaginatedResponse


class TestPaginatedResponse:
    """Tests for PaginatedResponse dataclass."""

    def test_from_dict(self):
        """Verify creating PaginatedResponse from a dictionary."""
        # Given: A dictionary with pagination data
        data = {
            "items": [{"id": 1}, {"id": 2}],
            "limit": 10,
            "offset": 0,
            "total": 47,
        }

        # When: Creating PaginatedResponse from dict
        response = PaginatedResponse.from_dict(data)

        # Then: All values are correctly parsed
        assert response.items == [{"id": 1}, {"id": 2}]
        assert response.limit == 10
        assert response.offset == 0
        assert response.total == 47

    def test_from_dict_with_defaults(self):
        """Verify missing keys get default values."""
        # When: Creating PaginatedResponse from empty dict
        response = PaginatedResponse.from_dict({})

        # Then: Default values are applied
        assert response.items == []
        assert response.limit == 0
        assert response.offset == 0
        assert response.total == 0

    @pytest.mark.parametrize(
        ("items_count", "limit", "offset", "total", "expected"),
        [
            (10, 10, 0, 47, True),  # More pages exist
            (7, 10, 40, 47, False),  # Last page
            (10, 10, 0, 10, False),  # Exact fit
        ],
    )
    def test_has_more(self, items_count, limit, offset, total, expected):
        """Verify has_more calculation."""
        # Given: A paginated response with items
        items = [{"id": i} for i in range(items_count)]
        response = PaginatedResponse(items=items, limit=limit, offset=offset, total=total)

        # When/Then: has_more returns expected value
        assert response.has_more is expected

    def test_next_offset(self):
        """Verify next_offset calculation."""
        # Given: A paginated response
        response = PaginatedResponse(
            items=[{"id": 1}] * 10,
            limit=10,
            offset=20,
            total=100,
        )

        # When/Then: next_offset is correctly calculated
        assert response.next_offset == 30

    @pytest.mark.parametrize(
        ("limit", "total", "expected"),
        [
            (10, 47, 5),  # Ceiling of 47/10
            (10, 50, 5),  # Exact division
            (0, 47, 0),  # Zero limit
        ],
    )
    def test_total_pages(self, limit, total, expected):
        """Verify total_pages calculation."""
        # Given: A paginated response
        response = PaginatedResponse(items=[], limit=limit, offset=0, total=total)

        # When/Then: total_pages returns expected value
        assert response.total_pages == expected

    @pytest.mark.parametrize(
        ("limit", "offset", "total", "expected"),
        [
            (10, 0, 47, 1),  # First page
            (10, 20, 47, 3),  # Middle page
            (10, 40, 47, 5),  # Last page
            (0, 0, 47, 0),  # Zero limit
        ],
    )
    def test_current_page(self, limit, offset, total, expected):
        """Verify current_page calculation."""
        # Given: A paginated response
        response = PaginatedResponse(items=[], limit=limit, offset=offset, total=total)

        # When/Then: current_page returns expected value
        assert response.current_page == expected
