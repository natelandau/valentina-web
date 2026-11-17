"""Service for interacting with the Character Traits API."""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, TrackerAction, TraitModifyCurrency
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    _TRACKER_ADAPTER,
    BulkAssignTraitResponse,
    CharacterTrait,
    CharacterTraitAdd,
    CharacterTraitSpecialtyCreate,
    CharacterTraitSpecialtyUpdate,
    CharacterTraitValueOptionsResponse,
    PaginatedResponse,
    Tracker,
    TrackerStateSet,
    TraitCreate,
    _TrackerAction,
    _TraitModify,
)
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class CharacterTraitsService(BaseService):
    """Service for interacting with the Character Traits API."""

    def __init__(
        self,
        client: "VClient",
        company_id: str,
        character_id: str,
        on_behalf_of: str,
    ) -> None:
        """Initialize the service.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            character_id: The ID of the character to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client)
        self._company_id = company_id
        self._character_id = character_id
        self._on_behalf_of = on_behalf_of

    def _format_endpoint(self, endpoint: str, **kwargs: str) -> str:
        """Format an endpoint with the scoped company_id and character_id plus any extra params."""
        return endpoint.format(
            company_id=self._company_id,
            character_id=self._character_id,
            **kwargs,
        )

    # Character Trait CRUD Methods

    def get_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        category_id: str | None = None,
        is_rollable: bool | None = None,
    ) -> PaginatedResponse[CharacterTrait]:
        """Retrieve a paginated page of character traits.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).
            category_id: Filter by category ID.
            is_rollable: Filter by whether the trait is rollable.

        Returns:
            A PaginatedResponse containing CharacterTrait objects and pagination metadata.
        """
        params: dict[str, str | int] = {}
        if category_id is not None:
            params["category_id"] = category_id
        if is_rollable is not None:
            params["is_rollable"] = is_rollable

        return self._get_paginated_as(
            self._format_endpoint(Endpoints.CHARACTER_TRAITS),
            CharacterTrait,
            limit=limit,
            offset=offset,
            params=params or None,
        )

    def list_all(
        self,
        *,
        category_id: str | None = None,
        is_rollable: bool | None = None,
    ) -> list[CharacterTrait]:
        """Retrieve all character traits.

        Args:
            category_id: Filter by category ID.
            is_rollable: Filter by whether the trait is rollable.

        Returns:
            A list of all CharacterTrait objects.
        """
        return list(self.iter_all(category_id=category_id, is_rollable=is_rollable))

    def iter_all(
        self,
        *,
        limit: int = 100,
        category_id: str | None = None,
        is_rollable: bool | None = None,
    ) -> Iterator[CharacterTrait]:
        """Iterate through all character traits.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            category_id: Filter by category ID.
            is_rollable: Filter by whether the trait is rollable.

        Yields:
            Individual CharacterTrait objects.

        Example:
            for trait in character_traits.iter_all():
                print(trait.name)
        """
        params: dict[str, str | int] = {}
        if category_id is not None:
            params["category_id"] = category_id
        if is_rollable is not None:
            params["is_rollable"] = is_rollable

        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.CHARACTER_TRAITS),
            limit=limit,
            params=params or None,
        ):
            yield CharacterTrait.model_validate(item)

    def get(self, character_trait_id: str) -> CharacterTrait:
        """Retrieve a specific character trait.

        Args:
            character_trait_id: The ID of the trait to retrieve.

        Returns:
            The CharacterTrait object.

        Raises:
            NotFoundError: If the character trait does not exist.
            AuthorizationError: If you don't have access to the character.
        """
        response = self._get(
            self._format_endpoint(Endpoints.CHARACTER_TRAIT, character_trait_id=character_trait_id)
        )
        return CharacterTrait.model_validate(response.json())

    def delete(self, character_trait_id: str, currency: TraitModifyCurrency | None = None) -> None:
        """Delete a character trait.

        Any specialties on the trait are removed with it and the cost of each is refunded.

        Args:
            character_trait_id: The ID of the trait to delete.
            currency: The currency to use to recoup the cost of the trait.

        Returns:
            None

        Raises:
            NotFoundError: If the trait does not exist.
            AuthorizationError: If you don't have access to the character.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            ConflictError: If recouping ``XP`` or ``STARTING_POINTS`` and another request
                changed the trait's value first. Refetch the trait and retry.
        """
        params: dict[str, str | int] = {}
        if currency is not None:
            params["currency"] = currency

        self._delete(
            self._format_endpoint(Endpoints.CHARACTER_TRAIT, character_trait_id=character_trait_id),
            params=params or None,
        )

    def assign(self, trait_id: str, value: int, currency: TraitModifyCurrency) -> CharacterTrait:
        """Assign a trait to a character.

        Args:
            trait_id: The ID of the trait to assign.
            value: The value of the trait to assign.
            currency: The currency to use to pay for the trait.

        Returns:
            The newly assigned CharacterTrait object.

        Raises:
            NotFoundError: If the trait does not exist.
            AuthorizationError: If you don't have access to the character.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            ConflictError: If paying with ``XP`` or ``STARTING_POINTS`` and another request
                changed the trait's value first. Refetch the trait and retry.
        """
        body = self._validate_request(
            CharacterTraitAdd,
            trait_id=trait_id,
            value=value,
            currency=currency,
        )
        response = self._post(
            self._format_endpoint(Endpoints.CHARACTER_TRAIT_ASSIGN),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CharacterTrait.model_validate(response.json())

    def bulk_assign(self, items: list[CharacterTraitAdd]) -> BulkAssignTraitResponse:
        """Assign multiple traits to a character in a single request.

        Each assignment is processed independently with best-effort semantics —
        successful traits are saved and failed ones are reported with error details.
        Currency balances are tracked across the batch.

        Args:
            items: List of CharacterTraitAdd models, each specifying a trait_id,
                value, and currency. Maximum 200 items (enforced server-side).

        Returns:
            BulkAssignTraitResponse with succeeded and failed lists.
        """
        response = self._post(
            self._format_endpoint(Endpoints.CHARACTER_TRAIT_BULK_ASSIGN),
            json=[
                item.model_dump(exclude_none=True, exclude_unset=True, mode="json")
                for item in items
            ],
        )
        return BulkAssignTraitResponse.model_validate(response.json())

    def create(
        self,
        request: TraitCreate | None = None,
        **kwargs,
    ) -> CharacterTrait:
        """Create a new custom character trait.

        The trait is always created at a value of ``1``; the supplied ``currency`` pays
        for that first dot. ``NPC`` and ``STORYTELLER`` characters accept only
        ``"NO_COST"``.

        Args:
            request: A TraitCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for TraitCreate if request is not provided.
                Required: name (str), category_id (str), currency (TraitModifyCurrency).
                Optional: description (str | None), max_value (int), min_value (int),
                show_when_zero (bool), is_rollable (bool, default True),
                initial_cost (int | None), upgrade_cost (int | None),
                count_based_cost_multiplier (int | None).

        Returns:
            The newly created CharacterTrait object.

        Raises:
            ConflictError: If paying with ``XP`` or ``STARTING_POINTS`` and another request
                changed the trait's value first. Refetch the trait and retry.
        """
        body = request if request is not None else self._validate_request(TraitCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.CHARACTER_TRAIT_CREATE),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CharacterTrait.model_validate(response.json())

    # Trait Value Modification Methods
    def get_value_options(self, character_trait_id: str) -> CharacterTraitValueOptionsResponse:
        """Get the value options for a character trait.

        Args:
            character_trait_id: The ID of the trait to get the value options for.

        Returns:
            The CharacterTraitValueOptionsResponse object.

        Raises:
            NotFoundError: If the trait does not exist.
            AuthorizationError: If you don't have access to the character.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        response = self._get(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_VALUE_OPTIONS, character_trait_id=character_trait_id
            ),
        )
        return CharacterTraitValueOptionsResponse.model_validate(response.json())

    def change_value(
        self,
        character_trait_id: str,
        new_value: int,
        currency: TraitModifyCurrency,
    ) -> CharacterTrait:
        """Change the value of a character trait.

        Lowering an ability to ``0`` also removes its specialties and refunds the cost of
        each. The value change and the refunds are applied together or not at all.

        Args:
            character_trait_id: The ID of the trait to change the value of.
            new_value: The new value of the trait.
            currency: The currency to use for the modification.

        Returns:
            The updated CharacterTrait object.

        Raises:
            ConflictError: If another request changed the trait's value after this request
                read it. Nothing is spent or refunded. Refetch the trait and retry.
        """
        body = self._validate_request(
            _TraitModify,
            target_value=new_value,
            currency=currency,
        )
        response = self._put(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_VALUE, character_trait_id=character_trait_id
            ),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return CharacterTrait.model_validate(response.json())

    # Specialty Methods

    def add_specialty(
        self,
        character_trait_id: str,
        name: str,
        currency: TraitModifyCurrency = "NO_COST",
    ) -> CharacterTrait:
        """Add a specialty to an ability trait.

        Specialties are only available on abilities with a value of 1 or higher. When the
        company's ``specialty_xp_cost_enabled`` setting is on, a specialty paid with ``XP``
        or ``STARTING_POINTS`` costs 3 points, and ``NO_COST`` follows the company's
        ``permission_free_trait_changes`` setting. When the setting is off, specialties are free.

        Args:
            character_trait_id: The ID of the ability trait.
            name: The specialty name (3-50 characters), unique on the trait ignoring case.
            currency: The currency to use to pay for the specialty.

        Returns:
            The updated CharacterTrait object, including its specialties.

        Raises:
            NotFoundError: If the trait does not exist.
            AuthorizationError: If you don't have access to the character.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the trait is not an ability, has a value of 0, already has a
                specialty with this name, the character cannot afford the cost, or an
                ``NPC`` or ``STORYTELLER`` character pays with anything but ``NO_COST``.
        """
        body = self._validate_request(
            CharacterTraitSpecialtyCreate,
            name=name,
            currency=currency,
        )
        response = self._post(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_SPECIALTIES, character_trait_id=character_trait_id
            ),
            json=body.model_dump(exclude_none=True, mode="json"),
        )
        return CharacterTrait.model_validate(response.json())

    def update_specialty(
        self,
        character_trait_id: str,
        specialty_id: str,
        name: str,
    ) -> CharacterTrait:
        """Rename a specialty on an ability trait.

        Renaming never changes the cost paid or the currency used.

        Args:
            character_trait_id: The ID of the ability trait.
            specialty_id: The ID of the specialty to rename.
            name: The new specialty name (3-50 characters), unique on the trait ignoring case.

        Returns:
            The updated CharacterTrait object, including its specialties.

        Raises:
            NotFoundError: If the trait or specialty does not exist, or the specialty
                belongs to a different trait.
            AuthorizationError: If you don't have access to the character.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the trait already has a specialty with this name.
        """
        body = self._validate_request(CharacterTraitSpecialtyUpdate, name=name)
        response = self._patch(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_SPECIALTY,
                character_trait_id=character_trait_id,
                specialty_id=specialty_id,
            ),
            json=body.model_dump(exclude_none=True, mode="json"),
        )
        return CharacterTrait.model_validate(response.json())

    def delete_specialty(self, character_trait_id: str, specialty_id: str) -> None:
        """Remove a specialty from an ability trait.

        The cost paid is refunded in the currency used to buy it. An ``XP`` refund follows
        the company's ``permission_recoup_xp`` setting; starting points are always refunded.

        Args:
            character_trait_id: The ID of the ability trait.
            specialty_id: The ID of the specialty to remove.

        Returns:
            None

        Raises:
            NotFoundError: If the trait or specialty does not exist, or the specialty
                belongs to a different trait.
            AuthorizationError: If you don't have access to the character.
        """
        self._delete(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_SPECIALTY,
                character_trait_id=character_trait_id,
                specialty_id=specialty_id,
            ),
        )

    # Tracker Methods

    def get_tracker(self, character_trait_id: str) -> Tracker:
        """Get the in-play tracker state of a character trait.

        The same object appears as ``CharacterTrait.tracker``. Use this to refresh one
        tracker without fetching the whole trait.

        Args:
            character_trait_id: The ID of the character trait.

        Returns:
            A CounterTracker or StainsTracker. Switch on ``type``.

        Raises:
            NotFoundError: If the trait has no tracker for the character's game version.
            AuthorizationError: If you don't have access to the character.
        """
        response = self._get(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_TRACKER, character_trait_id=character_trait_id
            ),
        )
        return _TRACKER_ADAPTER.validate_python(response.json())

    def set_tracker(
        self,
        character_trait_id: str,
        request: TrackerStateSet | None = None,
        **kwargs,
    ) -> Tracker:
        """Replace the full state of a trait tracker, such as to correct a mistake.

        Send only the field for the tracker's type: ``current`` for counters (required) or
        ``stains`` for stains. An empty request clears a stains tracker. Use
        ``apply_tracker_action`` for in-play changes instead.

        Args:
            character_trait_id: The ID of the character trait.
            request: A TrackerStateSet model, OR pass fields as keyword arguments.
            **kwargs: Fields for TrackerStateSet if request is not provided.
                Accepts: current, stains (int >= 0).

        Returns:
            The updated tracker.

        Raises:
            NotFoundError: If the trait has no tracker for the character's game version.
            AuthorizationError: If you are not the character's player or a storyteller.
            RequestValidationError: If a value is negative or a field is unknown.
            ValidationError: If a field does not fit the tracker type, a counter has no
                ``current``, or a value exceeds the tracker size.
        """
        body = request if request is not None else self._validate_request(TrackerStateSet, **kwargs)
        response = self._put(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_TRACKER, character_trait_id=character_trait_id
            ),
            json=body.model_dump(exclude_none=True, mode="json"),
        )
        return _TRACKER_ADAPTER.validate_python(response.json())

    def apply_tracker_action(
        self,
        character_trait_id: str,
        action: TrackerAction,
        *,
        amount: int = 1,
    ) -> Tracker:
        """Apply one in-play action to a trait tracker, such as spending Willpower.

        The actions each tracker accepts are listed in
        ``characters.TrackerRules[game_version][tracker.type]`` from ``options.get_options()``.

        Args:
            character_trait_id: The ID of the character trait.
            action: The action to apply.
            amount: How many points to apply. Must be at least 1.

        Returns:
            The updated tracker.

        Raises:
            NotFoundError: If the trait has no tracker for the character's game version.
            AuthorizationError: If you are not the character's player or a storyteller.
            RequestValidationError: If ``amount`` is less than 1.
            ValidationError: If the action does not fit the tracker or a spend exceeds the
                current value.
        """
        body = self._validate_request(_TrackerAction, action=action, amount=amount)
        response = self._post(
            self._format_endpoint(
                Endpoints.CHARACTER_TRAIT_TRACKER_ACTIONS, character_trait_id=character_trait_id
            ),
            json=body.model_dump(exclude_none=True, mode="json"),
        )
        return _TRACKER_ADAPTER.validate_python(response.json())
