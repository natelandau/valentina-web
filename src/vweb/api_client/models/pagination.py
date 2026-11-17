"""Pagination models for API responses."""

from dataclasses import dataclass
from typing import Any, Self


@dataclass
class PaginatedResponse[T]:
    """Response structure for paginated endpoints.

    Attributes:
        items: The requested page of results.
        limit: The limit that was applied.
        offset: The offset that was applied.
        total: Total number of items available across all pages.
    """

    items: list[T]
    limit: int
    offset: int
    total: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create a PaginatedResponse from a dictionary.

        Args:
            data: Dictionary containing pagination response data.

        Returns:
            A PaginatedResponse instance.
        """
        return cls(
            items=data.get("items", []),
            limit=data.get("limit", 0),
            offset=data.get("offset", 0),
            total=data.get("total", 0),
        )

    @property
    def has_more(self) -> bool:
        """Check if there are more pages available."""
        return self.offset + len(self.items) < self.total

    @property
    def next_offset(self) -> int:
        """Calculate the offset for the next page."""
        return self.offset + self.limit

    @property
    def total_pages(self) -> int:
        """Calculate the total number of pages."""
        if self.limit == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit

    @property
    def current_page(self) -> int:
        """Calculate the current page number (1-indexed)."""
        if self.limit == 0:
            return 0
        return (self.offset // self.limit) + 1
