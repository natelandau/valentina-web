"""Options and enumerations service."""

import json
from typing import TYPE_CHECKING, Any

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class OptionsService(BaseService):
    """Service for interacting with the Options and Enumerations API."""

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str | None = None) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client, on_behalf_of=on_behalf_of, company_id=company_id)

    # -------------------------------------------------------------------------
    # Options and Enumerations Methods
    # -------------------------------------------------------------------------

    def get_options(self) -> dict[str, dict[str, Any]]:
        """Retrieve all options and enumerations for the api.

        Most values are lists of enum values. ``characters.TrackerRules`` is a nested map
        ``{game_version: {tracker_type: {"actions": [...]}}}``. Health is keyed by its
        ``type``, ``DAMAGE``. Use it to choose which tracker actions to offer instead of
        hardcoding them.

        Returns:
            A dictionary of options and enumerations for the api.
        """
        response = self._get(self._format_endpoint(Endpoints.OPTIONS))
        return json.loads(response.content)
