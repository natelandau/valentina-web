"""Service for cross-company user lookup."""

from vweb.api_client.models import UserLookupResult
from vweb.api_client.routes import Routes
from vweb.api_client.services.base import BaseService


class UserLookupService(BaseService):
    """Service for looking up users across companies.

    Discover which companies a person has a user record in by searching
    via email, Discord ID, Google ID, GitHub ID, or Apple ID.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            results = client.user_lookup.by_email("alice@example.com")
            for r in results:
                print(f"{r.company_name}: {r.role}")
    """

    def _lookup(self, **params: str) -> list[UserLookupResult]:
        return self._list(Routes.USERS_LOOKUP, params=params)

    def by_email(self, email: str) -> list[UserLookupResult]:
        """Look up a user by email address.

        Args:
            email: Exact email address to search for.

        Returns:
            List of companies where a matching user was found. Empty list if no matches.
        """
        return self._lookup(email=email)

    def by_discord_id(self, discord_id: str) -> list[UserLookupResult]:
        """Look up a user by Discord profile ID.

        Args:
            discord_id: Discord profile ID to search for.

        Returns:
            List of companies where a matching user was found. Empty list if no matches.
        """
        return self._lookup(discord_id=discord_id)

    def by_google_id(self, google_id: str) -> list[UserLookupResult]:
        """Look up a user by Google profile ID.

        Args:
            google_id: Google profile ID to search for.

        Returns:
            List of companies where a matching user was found. Empty list if no matches.
        """
        return self._lookup(google_id=google_id)

    def by_github_id(self, github_id: str) -> list[UserLookupResult]:
        """Look up a user by GitHub profile ID.

        Args:
            github_id: GitHub profile ID to search for.

        Returns:
            List of companies where a matching user was found. Empty list if no matches.
        """
        return self._lookup(github_id=github_id)

    def by_apple_id(self, apple_id: str) -> list[UserLookupResult]:
        """Look up a user by Apple profile ID.

        Args:
            apple_id: Apple profile ID to search for.

        Returns:
            List of companies where a matching user was found. Empty list if no matches.
        """
        return self._lookup(apple_id=apple_id)
