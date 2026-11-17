"""Service for interacting with the Dice Rolls API."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, CharacterType
from vweb.api_client.models import (
    Diceroll,
    DicerollCreate,
    PaginatedResponse,
    _DicerollQuickrollCreate,
)
from vweb.api_client.routes import Routes
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class DicerollService(BaseService):
    """Service for interacting with the Dice Rolls API."""

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client, on_behalf_of=on_behalf_of, company_id=company_id)

    # -------------------------------------------------------------------------
    # Diceroll CRUD Methods
    # -------------------------------------------------------------------------

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        userid: str | None = None,
        characterid: str | None = None,
        campaignid: str | None = None,
        character_type: CharacterType | None = None,
    ) -> PaginatedResponse[Diceroll]:
        """Retrieve a paginated page of dice rolls.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).
            userid: Filter by user ID.
            characterid: Filter by character ID.
            campaignid: Filter by campaign ID.
            character_type: Filter by the associated character's type. Rolls with
                no character are excluded when this filter is set.

        Returns:
            A PaginatedResponse containing Diceroll objects and pagination metadata.
        """
        return self._page(
            Routes.DICEROLLS_LIST,
            limit=limit,
            offset=offset,
            params=self._build_params(
                userid=userid,
                characterid=characterid,
                campaignid=campaignid,
                character_type=character_type,
            ),
        )

    def list_all(
        self,
        *,
        userid: str | None = None,
        characterid: str | None = None,
        campaignid: str | None = None,
        character_type: CharacterType | None = None,
    ) -> list[Diceroll]:
        """Retrieve all dice rolls.

        Args:
            userid: Filter by user ID.
            characterid: Filter by character ID.
            campaignid: Filter by campaign ID.
            character_type: Filter by the associated character's type. Rolls with
                no character are excluded when this filter is set.

        Returns:
            A list of all Diceroll objects.
        """
        return list(
            self.iter_all(
                userid=userid,
                characterid=characterid,
                campaignid=campaignid,
                character_type=character_type,
            )
        )

    def iter_all(
        self,
        *,
        userid: str | None = None,
        characterid: str | None = None,
        campaignid: str | None = None,
        character_type: CharacterType | None = None,
        limit: int = 100,
    ) -> Iterator[Diceroll]:
        """Iterate through all dice rolls.

        Args:
            userid: Filter by user ID.
            characterid: Filter by character ID.
            campaignid: Filter by campaign ID.
            character_type: Filter by the associated character's type. Rolls with
                no character are excluded when this filter is set.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Diceroll objects.
        """
        yield from self._iter(
            Routes.DICEROLLS_LIST,
            limit=limit,
            params=self._build_params(
                userid=userid,
                characterid=characterid,
                campaignid=campaignid,
                character_type=character_type,
            ),
        )

    def get(self, diceroll_id: str) -> Diceroll:
        """Retrieve a specific dice roll."""
        return self._call(Routes.DICEROLLS_GET, diceroll_id=diceroll_id)

    def create(
        self,
        request: DicerollCreate | None = None,
        **kwargs,
    ) -> Diceroll:
        """Create a new dice roll.

        Args:
            request: A DicerollCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for DicerollCreate if request is not provided.
                Accepts: dice_size (DiceSize, required), num_dice (int, required),
                difficulty (int | None), num_desperation_dice (int, default 0),
                dice_modifier (int, default 0),
                comment (str | None), trait_ids (list[str]),
                character_id (str | None), campaign_id (str | None).
        """
        body = request if request is not None else DicerollCreate(**kwargs)
        return self._call(
            Routes.DICEROLLS_CREATE,
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )

    def create_from_quickroll(
        self,
        *,
        quickroll_id: str,
        character_id: str,
        comment: str | None = None,
        difficulty: int = 6,
        num_desperation_dice: int = 0,
        dice_modifier: int = 0,
    ) -> Diceroll:
        """Create a new dice roll using a quickroll template."""
        return self._call(
            Routes.DICEROLLS_QUICKROLL,
            json=_DicerollQuickrollCreate(
                quickroll_id=quickroll_id,
                character_id=character_id,
                comment=comment,
                difficulty=difficulty,
                num_desperation_dice=num_desperation_dice,
                dice_modifier=dice_modifier,
            ).model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
