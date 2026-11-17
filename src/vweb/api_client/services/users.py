"""Service for interacting with the Users API."""

import mimetypes
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from vweb.api_client.constants import DEFAULT_PAGE_LIMIT, IdentityProvider, UserInclude, UserRole
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import (
    Asset,
    CampaignExperience,
    Note,
    NoteCreate,
    NoteUpdate,
    PaginatedResponse,
    Quickroll,
    QuickrollCreate,
    QuickrollUpdate,
    RollStatistics,
    User,
    UserApproveDTO,
    UserCreate,
    UserDetail,
    UserIdentityLinkDTO,
    UserMergeDTO,
    UserUpdate,
    _ExperienceAddRemove,
)
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class UsersService(BaseService):
    """Service for managing users within a company in the Valentina API.

    This service is scoped to a specific company at initialization time.
    All methods operate within that company context.

    Provides methods to create, retrieve, update, and delete users,
    as well as access user statistics and assets.

    Example:
        >>> with VClient() as client:
        ...     users = client.users("company_id")
        ...     all_users = users.list_all()
        ...     user = users.get("user_id")
    """

    def __init__(self, client: "VClient", company_id: str, on_behalf_of: str) -> None:
        """Initialize the service scoped to a specific company.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
        """
        super().__init__(client)
        self._company_id = company_id
        self._on_behalf_of = on_behalf_of

    def _format_endpoint(self, endpoint: str, **kwargs: str) -> str:
        """Format an endpoint with the scoped company_id plus any extra params."""
        return endpoint.format(company_id=self._company_id, **kwargs)

    # Unapproved User Methods

    def get_unapproved_page(
        self,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[User]:
        """Retrieve a paginated page of unapproved users within a company.

        Unapproved users have registered but have not yet been approved by an admin.

        Args:
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing User objects and pagination metadata.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.USERS_UNAPPROVED_LIST),
            User,
            limit=limit,
            offset=offset,
        )

    def list_all_unapproved(self) -> list[User]:
        """Retrieve all unapproved users within a company.

        Automatically paginates through all results. Use `get_unapproved_page()` for
        paginated access or `iter_all_unapproved()` for memory-efficient streaming.

        Returns:
            A list of all unapproved User objects.
        """
        return list(self.iter_all_unapproved())

    def iter_all_unapproved(
        self,
        *,
        limit: int = 100,
    ) -> Iterator[User]:
        """Iterate through all unapproved users within a company.

        Yields individual unapproved users, automatically fetching subsequent pages
        until all items have been retrieved.

        Args:
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual User objects.
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.USERS_UNAPPROVED_LIST),
            limit=limit,
        ):
            yield User.model_validate(item)

    def approve_user(
        self,
        user_id: str,
        role: UserRole,
    ) -> User:
        """Approve an unapproved user and assign them a role.

        The assigned ``role`` is validated through the server-side role-assignment
        hierarchy — for example, a STORYTELLER cannot approve a user directly to
        ADMIN, and only ADMIN may approve a user to ADMIN or DEACTIVATED.

        Args:
            user_id: The ID of the unapproved user to approve.
            role: The role to assign to the approved user.

        Returns:
            The approved User object with the assigned role.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If the requesting user lacks permission to assign
                the requested role under the hierarchy.
        """
        body = UserApproveDTO(role=role)
        response = self._post(
            self._format_endpoint(Endpoints.USER_APPROVE, user_id=user_id),
            json=body.model_dump(mode="json"),
        )
        return User.model_validate(response.json())

    def deny_user(
        self,
        user_id: str,
    ) -> None:
        """Deny an unapproved user.

        Args:
            user_id: The ID of the unapproved user to deny.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._post(
            self._format_endpoint(Endpoints.USER_DENY, user_id=user_id),
        )

    def merge(
        self,
        primary_user_id: str,
        secondary_user_id: str,
    ) -> User:
        """Merge an unapproved user into an existing primary user.

        The secondary (unapproved) user's data is merged into the primary user,
        and the secondary user is removed.

        Args:
            primary_user_id: The ID of the primary user to merge into.
            secondary_user_id: The ID of the unapproved user to merge from.

        Returns:
            The primary User object after the merge.

        Raises:
            NotFoundError: If either user does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        body = UserMergeDTO(
            primary_user_id=primary_user_id,
            secondary_user_id=secondary_user_id,
        )
        response = self._post(
            self._format_endpoint(Endpoints.USER_MERGE),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return User.model_validate(response.json())

    def link_identity(
        self,
        user_id: str,
        *,
        provider: IdentityProvider,
        token: str,
    ) -> User:
        """Attach an additional verified provider identity to a user.

        Use for "connect your account" settings flows: a user already
        authenticated via one provider presents a credential from a second
        provider, which the API verifies and links to the same user. Only the
        acting user themselves or a company ADMIN may link identities.
        Re-linking the same identity is idempotent and refreshes the stored
        profile.

        Args:
            user_id: The ID of the user receiving the identity.
            provider: The identity provider that issued the credential.
            token: The provider credential (OIDC ID token for apple/google,
                OAuth access token for discord/github).

        Returns:
            The updated User object.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            AuthorizationError: If the acting user is neither the target user nor an admin.
            ConflictError: If the identity belongs to another user, or the user
                already has a different identity from this provider
                (code IDENTITY_ALREADY_LINKED).
            UnprocessableEntityError: If the provider token fails verification
                (code TOKEN_VERIFICATION_FAILED).
        """
        body = self._validate_request(UserIdentityLinkDTO, provider=provider, token=token)
        response = self._post(
            self._format_endpoint(Endpoints.USER_IDENTITIES, user_id=user_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return User.model_validate(response.json())

    def unlink_identity(
        self,
        user_id: str,
        *,
        provider: IdentityProvider,
    ) -> User:
        """Disconnect a verified provider identity from a user.

        The counterpart to link_identity for "disconnect your account" settings
        flows: remove a single OAuth provider identity so it can no longer be
        used to log in. Only the acting user themselves or a company ADMIN may
        unlink identities. The provider's profile field on the returned User is
        cleared to None.

        The final remaining identity cannot be removed, since that would leave
        the account unable to authenticate. Link another provider first.

        Args:
            user_id: The ID of the user losing the identity.
            provider: The identity provider to disconnect.

        Returns:
            The updated User object with the provider's profile field cleared.

        Raises:
            AuthorizationError: If the acting user is neither the target user nor an admin.
            NotFoundError: If the user has no identity from this provider
                (code IDENTITY_NOT_LINKED).
            ConflictError: If the provider is the user's only linked identity,
                which cannot be removed (code LAST_IDENTITY).
        """
        response = self._delete(
            self._format_endpoint(Endpoints.USER_IDENTITY, user_id=user_id, provider=provider),
        )
        return User.model_validate(response.json())

    # User CRUD Methods

    def get_page(
        self,
        *,
        user_role: UserRole | None = None,
        email: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[User]:
        """Retrieve a paginated page of users within a company.

        Optionally filter by user role to view specific user types such as players
        or storytellers.

        Args:
            user_role: Optional role filter (ADMIN, STORYTELLER, PLAYER).
            email: Optional email filter.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing User objects and pagination metadata.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.USERS),
            User,
            limit=limit,
            offset=offset,
            params=self._build_params(user_role=user_role, email=email),
        )

    def list_all(
        self,
        *,
        user_role: UserRole | None = None,
        email: str | None = None,
    ) -> list[User]:
        """Retrieve all users within a company.

        Automatically paginates through all results. Use `get_page()` for paginated access
        or `iter_all()` for memory-efficient streaming of large datasets.

        Args:
            user_role: Optional role filter (ADMIN, STORYTELLER, PLAYER).
            email: Optional email filter.

        Returns:
            A list of all User objects.
        """
        return list(self.iter_all(user_role=user_role, email=email))

    def iter_all(
        self,
        *,
        user_role: UserRole | None = None,
        email: str | None = None,
        limit: int = 100,
    ) -> Iterator[User]:
        """Iterate through all users within a company.

        Yields individual users, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            user_role: Optional role filter (ADMIN, STORYTELLER, PLAYER).
            email: Optional email filter.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual User objects.

        Example:
            >>> for user in users.iter_all():
            ...     print(user.name)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.USERS),
            limit=limit,
            params=self._build_params(user_role=user_role, email=email),
        ):
            yield User.model_validate(item)

    def get(
        self,
        user_id: str,
        *,
        include: Sequence[UserInclude] | None = None,
    ) -> UserDetail:
        """Retrieve detailed information about a specific user.

        Fetches the user and optionally embeds child resources directly in the
        response, avoiding follow-up requests.

        Args:
            user_id: The ID of the user to retrieve.
            include: Child resources to embed in the response. Valid values are
                ``"quickrolls"``, ``"notes"``, ``"assets"``, and ``"characters"``.
                ``"assets"`` returns assets attached to the user (not assets the user
                uploaded). ``"characters"`` returns only characters the user plays.

        Returns:
            The UserDetail object with full details and any requested embeds.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(Endpoints.USER, user_id=user_id),
            params=self._build_params(include=list(include) if include else None),
        )
        return UserDetail.model_validate(response.json())

    def create(
        self,
        request: UserCreate | None = None,
        **kwargs,
    ) -> User:
        """Create a new user within a company.

        The user is automatically added to the company's user list.

        Provider identities (Discord, Google, GitHub, Apple) cannot be set here;
        any provider-profile values passed are silently ignored. Resolve them
        through the verified identity endpoints instead
        (:meth:`IdentityService.identify` or :meth:`UsersService.link_identity`).

        The initial ``role`` cannot be ``UNAPPROVED`` or ``DEACTIVATED`` (not a
        creation path); either will surface as ``ValidationError``.

        Args:
            request: A UserCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for UserCreate if request is not provided.
                Accepts: username (str, required), email (str, required),
                role (UserRole, required),
                name_first (str | None), name_last (str | None).

        Returns:
            The newly created User object.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
            AuthorizationError: If you don't have admin-level access to the company.
        """
        body = request if request is not None else self._validate_request(UserCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.USERS),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return User.model_validate(response.json())

    def update(
        self,
        user_id: str,
        request: UserUpdate | None = None,
        **kwargs,
    ) -> User:
        """Modify a user's properties.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Setting ``role="DEACTIVATED"`` is the canonical way to deactivate a user:
        the account can no longer log in or act, but their characters, assets, XP,
        and notes remain intact and manageable by other users. Reactivate by calling
        this same endpoint with any other valid role. Role changes are subject to a
        server-side role-assignment hierarchy (e.g. only ADMIN may assign or remove
        ADMIN/DEACTIVATED) and the server refuses to demote or deactivate the last
        remaining active admin.

        Args:
            user_id: The ID of the user to update.
            request: A UserUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for UserUpdate if request is not provided.
                Accepts: username (str | None), email (str | None),
                role (UserRole | None),
                name_first (str | None), name_last (str | None).

        Provider identities (Discord, Google, GitHub, Apple) cannot be changed
        here; any provider-profile values passed are silently ignored. Resolve
        them through the verified identity endpoints instead
        (:meth:`IdentityService.identify` or :meth:`UsersService.link_identity`).

        Returns:
            The updated User object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If the requesting user lacks permission to make
                the change or to assign the requested role under the hierarchy.
            ConflictError: If the change would remove the last active admin.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(UserUpdate, **kwargs)
        response = self._patch(
            self._format_endpoint(Endpoints.USER, user_id=user_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return User.model_validate(response.json())

    def delete(
        self,
        user_id: str,
    ) -> None:
        """Remove a user from the company.

        The user is removed from the company's user list and their data is archived.

        Args:
            user_id: The ID of the user to delete.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(
            self._format_endpoint(Endpoints.USER, user_id=user_id),
        )

    def get_statistics(
        self,
        user_id: str,
        *,
        num_top_traits: int = 5,
    ) -> RollStatistics:
        """Retrieve aggregated dice roll statistics for a specific user.

        Includes success rates, critical frequencies, most-used traits, etc.

        Args:
            user_id: The ID of the user to get statistics for.
            num_top_traits: Number of top traits to include (default 5).

        Returns:
            RollStatistics object with aggregated statistics.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(Endpoints.USER_STATISTICS, user_id=user_id),
            params={"num_top_traits": num_top_traits},
        )
        return RollStatistics.model_validate(response.json())

    # Asset Methods

    def get_assets_page(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Asset]:
        """Retrieve a paginated page of assets for a user.

        Args:
            user_id: The ID of the user whose assets to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Asset objects and pagination metadata.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.USER_ASSETS, user_id=user_id),
            Asset,
            limit=limit,
            offset=offset,
        )

    def list_all_assets(
        self,
        user_id: str,
    ) -> list[Asset]:
        """Retrieve all assets for a user.

        Automatically paginates through all results. Use `get_assets_page()` for paginated
        access or `iter_all_assets()` for memory-efficient streaming of large datasets.

        Args:
            user_id: The ID of the user whose assets to list.

        Returns:
            A list of all Asset objects.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return list(self.iter_all_assets(user_id))

    def iter_all_assets(
        self,
        user_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Asset]:
        """Iterate through all assets for a user.

        Yields individual assets, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            user_id: The ID of the user whose assets to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Asset objects.

        Example:
            >>> for asset in users.iter_all_assets("user_id"):
            ...     print(asset.original_filename)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.USER_ASSETS, user_id=user_id),
            limit=limit,
        ):
            yield Asset.model_validate(item)

    def get_asset(
        self,
        user_id: str,
        asset_id: str,
    ) -> Asset:
        """Retrieve details of a specific asset including its URL and metadata.

        Args:
            user_id: The ID of the user who owns the asset.
            asset_id: The ID of the asset to retrieve.

        Returns:
            The Asset object with full details.

        Raises:
            NotFoundError: If the asset does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(Endpoints.USER_ASSET, user_id=user_id, asset_id=asset_id)
        )
        return Asset.model_validate(response.json())

    def delete_asset(
        self,
        user_id: str,
        asset_id: str,
    ) -> None:
        """Delete an asset from a user.

        This action cannot be undone. The asset file is permanently removed.

        Args:
            user_id: The ID of the user who owns the asset.
            asset_id: The ID of the asset to delete.

        Raises:
            NotFoundError: If the asset does not exist or belongs to a different user.
            AuthorizationError: If the acting user is neither ``user_id`` nor a
                company admin.
        """
        self._delete(
            self._format_endpoint(Endpoints.USER_ASSET, user_id=user_id, asset_id=asset_id)
        )

    def upload_asset(
        self,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> Asset:
        """Upload a new image asset for a user.

        Uploads an image to S3 storage and associates it with the user.

        Only image files are accepted: PNG, JPEG, GIF, and WEBP. Any other
        upload (documents, audio, video, archives, SVG, or a non-image payload
        mislabeled as an image) is rejected with 400 Bad Request, as are
        images over 24 megapixels (width x height). The stored
        ``mime_type`` is detected from the file's bytes; the ``content_type``
        argument is ignored server-side and cannot change or bypass the stored
        type. Uploaded assets therefore always have ``asset_type == "image"``.

        Args:
            user_id: The ID of the user to upload the asset for.
            filename: The original filename of the asset.
            content: The raw bytes of the file to upload.
            content_type: The MIME type of the file. If not provided, inferred from filename.

        Returns:
            The created Asset object with the public URL and metadata.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If the acting user is neither ``user_id`` nor a
                company admin.
            ValidationError: If the file is invalid or exceeds size limits.
        """
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        response = self._post_file(
            self._format_endpoint(Endpoints.USER_ASSET_UPLOAD, user_id=user_id),
            file=(filename, content, content_type),
        )
        return Asset.model_validate(response.json())

    # Avatar Methods

    def upload_avatar(
        self,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> User:
        """Upload a custom avatar for a user, replacing any existing one.

        Accepts PNG, JPEG, WEBP, or GIF (first frame) up to 5 MB and 24
        megapixels. The server normalizes the image to a 512x512 WebP and it
        overrides any identity-provider-derived avatar. Requires the
        ``On-Behalf-Of`` header (permitted for the user themselves or an admin).

        Args:
            user_id: The ID of the user to set the avatar for.
            filename: The original filename of the image.
            content: The raw bytes of the image to upload.
            content_type: The MIME type. If not provided, inferred from filename.

        Returns:
            The updated User object with the new ``avatar_url``.
        """
        if content_type is None:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        response = self._put_file(
            self._format_endpoint(Endpoints.USER_AVATAR, user_id=user_id),
            file=(filename, content, content_type),
        )
        return User.model_validate(response.json())

    def delete_avatar(self, user_id: str) -> User:
        """Remove a user's custom avatar.

        The avatar falls back to the identity-provider avatar, or ``None`` if
        none exists. Requires the ``On-Behalf-Of`` header (permitted for the
        user themselves or an admin). Responds 200 OK with the updated user
        body (not 204).

        Args:
            user_id: The ID of the user whose custom avatar to remove.

        Returns:
            The updated User object with the resolved ``avatar_url``.
        """
        response = self._delete(
            self._format_endpoint(Endpoints.USER_AVATAR, user_id=user_id),
        )
        return User.model_validate(response.json())

    # Experience Methods

    def get_experience(
        self,
        user_id: str,
        campaign_id: str,
    ) -> CampaignExperience:
        """Retrieve a user's experience points and cool points for a specific campaign.

        Creates the experience record automatically if it doesn't exist for the campaign.

        Args:
            user_id: The ID of the user to get experience for.
            campaign_id: The ID of the campaign to get experience for.

        Returns:
            CampaignExperience object with xp_current, xp_total, and cool_points.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(
                Endpoints.USER_EXPERIENCE_CAMPAIGN, user_id=user_id, campaign_id=campaign_id
            )
        )
        return CampaignExperience.model_validate(response.json())

    def add_xp(
        self,
        user_id: str,
        campaign_id: str,
        amount: int,
    ) -> CampaignExperience:
        """Award experience points to a user for a specific campaign.

        The XP is added to both the current XP pool (available for spending) and
        the total XP tracker (lifetime earned).

        Args:
            user_id: The ID of the user to award XP to.
            campaign_id: The ID of the campaign to add XP for.
            amount: The amount of XP to add. Must be at least 1.

        Returns:
            Updated CampaignExperience object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
        """
        body = self._validate_request(
            _ExperienceAddRemove,
            amount=amount,
            campaign_id=campaign_id,
        )
        response = self._post(
            self._format_endpoint(Endpoints.USER_EXPERIENCE_XP_ADD, user_id=user_id),
            json=body.model_dump(mode="json"),
        )
        return CampaignExperience.model_validate(response.json())

    def remove_xp(
        self,
        user_id: str,
        campaign_id: str,
        amount: int,
    ) -> CampaignExperience:
        """Deduct experience points from a user's current XP pool.

        Returns an error if the user has insufficient XP to complete the deduction.

        Args:
            user_id: The ID of the user to remove XP from.
            campaign_id: The ID of the campaign to remove XP for.
            amount: The amount of XP to remove. Must be at least 1.

        Returns:
            Updated CampaignExperience object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the user has insufficient XP.
        """
        body = self._validate_request(
            _ExperienceAddRemove,
            amount=amount,
            campaign_id=campaign_id,
        )
        response = self._post(
            self._format_endpoint(Endpoints.USER_EXPERIENCE_XP_REMOVE, user_id=user_id),
            json=body.model_dump(mode="json"),
        )
        return CampaignExperience.model_validate(response.json())

    def add_cool_points(
        self,
        user_id: str,
        campaign_id: str,
        amount: int,
    ) -> CampaignExperience:
        """Award cool points to a user for a specific campaign.

        Cool points are converted to XP automatically based on the company's
        configured exchange rate.

        Args:
            user_id: The ID of the user to award cool points to.
            campaign_id: The ID of the campaign to add cool points for.
            amount: The amount of cool points to add. Must be at least 1.

        Returns:
            Updated CampaignExperience object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
        """
        body = self._validate_request(
            _ExperienceAddRemove,
            amount=amount,
            campaign_id=campaign_id,
        )
        response = self._post(
            self._format_endpoint(Endpoints.USER_EXPERIENCE_CP_ADD, user_id=user_id),
            json=body.model_dump(mode="json"),
        )
        return CampaignExperience.model_validate(response.json())

    # Notes Methods

    def get_notes_page(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Note]:
        """Retrieve a paginated page of notes for a user.

        Args:
            user_id: The ID of the user whose notes to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Note objects and pagination metadata.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.USER_NOTES, user_id=user_id),
            Note,
            limit=limit,
            offset=offset,
        )

    def list_all_notes(
        self,
        user_id: str,
    ) -> list[Note]:
        """Retrieve all notes for a user.

        Automatically paginates through all results. Use `get_notes_page()` for paginated
        access or `iter_all_notes()` for memory-efficient streaming of large datasets.

        Args:
            user_id: The ID of the user whose notes to list.

        Returns:
            A list of all Note objects.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return list(self.iter_all_notes(user_id))

    def iter_all_notes(
        self,
        user_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Note]:
        """Iterate through all notes for a user.

        Yields individual notes, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            user_id: The ID of the user whose notes to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Note objects.

        Example:
            >>> for note in users.iter_all_notes("user_id"):
            ...     print(note.title)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.USER_NOTES, user_id=user_id),
            limit=limit,
        ):
            yield Note.model_validate(item)

    def get_note(
        self,
        user_id: str,
        note_id: str,
    ) -> Note:
        """Retrieve a specific note including its content and metadata.

        Args:
            user_id: The ID of the user who owns the note.
            note_id: The ID of the note to retrieve.

        Returns:
            The Note object with full details.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(Endpoints.USER_NOTE, user_id=user_id, note_id=note_id)
        )
        return Note.model_validate(response.json())

    def create_note(
        self,
        user_id: str,
        request: NoteCreate | None = None,
        **kwargs,
    ) -> Note:
        """Create a new note for a user.

        Notes support markdown formatting for rich text content.

        Args:
            user_id: The ID of the user to create the note for.
            request: A NoteCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteCreate if request is not provided.
                Accepts: title (str, required), content (str, required).

        Returns:
            The newly created Note object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.USER_NOTES, user_id=user_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def update_note(
        self,
        user_id: str,
        note_id: str,
        request: NoteUpdate | None = None,
        **kwargs,
    ) -> Note:
        """Modify a note's content.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            user_id: The ID of the user who owns the note.
            note_id: The ID of the note to update.
            request: A NoteUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for NoteUpdate if request is not provided.
                Accepts: title (str | None), content (str | None).

        Returns:
            The updated Note object.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(NoteUpdate, **kwargs)
        response = self._patch(
            self._format_endpoint(Endpoints.USER_NOTE, user_id=user_id, note_id=note_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Note.model_validate(response.json())

    def delete_note(
        self,
        user_id: str,
        note_id: str,
    ) -> None:
        """Remove a note from a user.

        This action cannot be undone.

        Args:
            user_id: The ID of the user who owns the note.
            note_id: The ID of the note to delete.

        Raises:
            NotFoundError: If the note does not exist.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(self._format_endpoint(Endpoints.USER_NOTE, user_id=user_id, note_id=note_id))

    # Quickroll Methods

    def get_quickrolls_page(
        self,
        user_id: str,
        *,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> PaginatedResponse[Quickroll]:
        """Retrieve a paginated page of quickrolls for a user.

        Quickrolls are pre-configured dice pools for frequently used trait combinations,
        allowing faster gameplay.

        Args:
            user_id: The ID of the user whose quickrolls to list.
            limit: Maximum number of items to return (0-100, default 10).
            offset: Number of items to skip from the beginning (default 0).

        Returns:
            A PaginatedResponse containing Quickroll objects and pagination metadata.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return self._get_paginated_as(
            self._format_endpoint(Endpoints.USER_QUICKROLLS, user_id=user_id),
            Quickroll,
            limit=limit,
            offset=offset,
        )

    def list_all_quickrolls(
        self,
        user_id: str,
    ) -> list[Quickroll]:
        """Retrieve all quickrolls for a user.

        Automatically paginates through all results. Use `get_quickrolls_page()` for
        paginated access or `iter_all_quickrolls()` for memory-efficient streaming.

        Args:
            user_id: The ID of the user whose quickrolls to list.

        Returns:
            A list of all Quickroll objects.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have access to the company.
        """
        return list(self.iter_all_quickrolls(user_id))

    def iter_all_quickrolls(
        self,
        user_id: str,
        *,
        limit: int = 100,
    ) -> Iterator[Quickroll]:
        """Iterate through all quickrolls for a user.

        Yields individual quickrolls, automatically fetching subsequent pages until
        all items have been retrieved.

        Args:
            user_id: The ID of the user whose quickrolls to iterate.
            limit: Items per page (default 100 for efficiency).

        Yields:
            Individual Quickroll objects.

        Example:
            >>> for qr in users.iter_all_quickrolls("user_id"):
            ...     print(qr.name)
        """
        for item in self._iter_all_pages(
            self._format_endpoint(Endpoints.USER_QUICKROLLS, user_id=user_id),
            limit=limit,
        ):
            yield Quickroll.model_validate(item)

    def get_quickroll(
        self,
        user_id: str,
        quickroll_id: str,
    ) -> Quickroll:
        """Retrieve a specific quickroll including its name and trait configuration.

        Args:
            user_id: The ID of the user who owns the quickroll.
            quickroll_id: The ID of the quickroll to retrieve.

        Returns:
            The Quickroll object with full details.

        Raises:
            NotFoundError: If the quickroll does not exist or does not belong to
                ``user_id``.
            AuthorizationError: If you don't have access to the company.
        """
        response = self._get(
            self._format_endpoint(
                Endpoints.USER_QUICKROLL, user_id=user_id, quickroll_id=quickroll_id
            )
        )
        return Quickroll.model_validate(response.json())

    def create_quickroll(
        self,
        user_id: str,
        request: QuickrollCreate | None = None,
        **kwargs,
    ) -> Quickroll:
        """Create a new quickroll for a user.

        Define the traits that make up the dice pool. Quickroll names must be unique
        per user.

        Args:
            user_id: The ID of the user to create the quickroll for.
            request: A QuickrollCreate model, OR pass fields as keyword arguments.
            **kwargs: Fields for QuickrollCreate if request is not provided.
                Accepts: name (str, required), description (str | None),
                trait_ids (list[str]).

        Returns:
            The newly created Quickroll object.

        Raises:
            NotFoundError: If the user does not exist.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(QuickrollCreate, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.USER_QUICKROLLS, user_id=user_id),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Quickroll.model_validate(response.json())

    def update_quickroll(
        self,
        user_id: str,
        quickroll_id: str,
        request: QuickrollUpdate | None = None,
        **kwargs,
    ) -> Quickroll:
        """Modify a quickroll's name or trait configuration.

        Only include fields that need to be changed; omitted fields remain unchanged.

        Args:
            user_id: The ID of the user who owns the quickroll.
            quickroll_id: The ID of the quickroll to update.
            request: A QuickrollUpdate model, OR pass fields as keyword arguments.
            **kwargs: Fields for QuickrollUpdate if request is not provided.
                Accepts: name (str | None), description (str | None),
                trait_ids (list[str] | None).

        Returns:
            The updated Quickroll object.

        Raises:
            NotFoundError: If the quickroll does not exist or does not belong to
                ``user_id``.
            AuthorizationError: If you don't have appropriate access.
            RequestValidationError: If the input parameters fail client-side validation.
            ValidationError: If the request data is invalid.
        """
        body = request if request is not None else self._validate_request(QuickrollUpdate, **kwargs)
        response = self._patch(
            self._format_endpoint(
                Endpoints.USER_QUICKROLL, user_id=user_id, quickroll_id=quickroll_id
            ),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return Quickroll.model_validate(response.json())

    def delete_quickroll(
        self,
        user_id: str,
        quickroll_id: str,
    ) -> None:
        """Remove a quickroll from a user.

        This action cannot be undone.

        Args:
            user_id: The ID of the user who owns the quickroll.
            quickroll_id: The ID of the quickroll to delete.

        Raises:
            NotFoundError: If the quickroll does not exist or does not belong to
                ``user_id``.
            AuthorizationError: If you don't have appropriate access.
        """
        self._delete(
            self._format_endpoint(
                Endpoints.USER_QUICKROLL, user_id=user_id, quickroll_id=quickroll_id
            )
        )
