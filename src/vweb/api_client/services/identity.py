"""Service for verified identity resolution."""

from typing import TYPE_CHECKING

from vweb.api_client.endpoints import Endpoints
from vweb.api_client.models import IdentityResolution, UserIdentifyDTO
from vweb.api_client.services.base import BaseService

if TYPE_CHECKING:
    from vweb.api_client.client import VClient


class IdentityService(BaseService):
    """Service for resolving verified provider logins to canonical users.

    Forward the credential obtained from a provider's own login flow (an OIDC
    ID token for apple/google, an OAuth access token for discord/github). The
    API verifies the credential with the provider and resolves the user in
    order: match by provider ID, auto-link by provider-verified email, or
    create a new UNAPPROVED user. Auto-link never replaces an identity: when
    the email's user already holds a different identity from the same
    provider, a new user is created instead. OIDC ID tokens must carry
    ``exp`` and ``iat`` claims.

    This service does not require an acting user (no On-Behalf-Of header).
    Authentication is via developer API key only.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            identity = client.identity()
            result = identity.identify(provider="google", token="<id-token>")
            print(result.resolution, result.user.id)
    """

    def __init__(self, client: "VClient", company_id: str) -> None:
        """Initialize the service scoped to a specific company.

        Args:
            client: The VClient instance to use for requests.
            company_id: The ID of the company to resolve identities in.
        """
        super().__init__(client, company_id=company_id)

    def identify(
        self,
        request: UserIdentifyDTO | None = None,
        **kwargs,
    ) -> IdentityResolution:
        """Resolve a verified provider login to a canonical user.

        The returned ``resolution`` field reports which path the API took:
        ``matched`` (an existing user holds this provider identity), ``linked``
        (the identity was auto-linked onto an existing user by provider-verified
        email), or ``created`` (a new UNAPPROVED user was registered). An email
        match whose user already holds a different identity from the same
        provider resolves to ``created``, not ``linked``.

        Args:
            request: A UserIdentifyDTO model, OR pass fields as keyword arguments.
            **kwargs: Fields for UserIdentifyDTO if request is not provided.
                Accepts: provider (IdentityProvider, required), token (str,
                required), username (str | None), email (str | None). The
                username and email apply only when a new user is created;
                email is required there only if the provider supplied none.

        Returns:
            The IdentityResolution with the resolved user.

        Raises:
            RequestValidationError: If the input parameters fail client-side validation.
            UnprocessableEntityError: If the provider token fails verification
                (code TOKEN_VERIFICATION_FAILED) or creation needs an email the
                provider did not supply (code EMAIL_REQUIRED).
            ServerError: If the provider is unreachable (503, code PROVIDER_UNAVAILABLE).
        """
        body = request if request is not None else self._validate_request(UserIdentifyDTO, **kwargs)
        response = self._post(
            self._format_endpoint(Endpoints.AUTH_IDENTIFY),
            json=body.model_dump(exclude_none=True, exclude_unset=True, mode="json"),
        )
        return IdentityResolution.model_validate(response.json())
