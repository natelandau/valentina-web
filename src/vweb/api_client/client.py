"""Main API client for Valentina."""

import contextvars
import platform
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, overload

import httpx2
from loguru import logger

from vweb.api_client.config import _APIConfig
from vweb.api_client.constants import (
    API_KEY_HEADER,
    DEFAULT_MAX_PARALLEL_REQUESTS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_RETRY_DELAY,
    DEFAULT_RETRY_BUDGET,
    DEFAULT_RETRY_DELAY,
    DEFAULT_TIMEOUT,
    USER_AGENT_PRODUCT,
)

if TYPE_CHECKING:
    from vweb.api_client.services import (
        BooksService,
        CampaignsService,
        ChaptersService,
        CharacterAutogenService,
        CharacterBlueprintService,
        CharactersService,
        CharacterTraitsService,
        CompaniesService,
        DicerollService,
        DictionaryService,
        IdentityService,
        OptionsService,
        SystemService,
        UserLookupService,
        UsersService,
    )


def _in_copied_context[R](call: Callable[[], R]) -> Callable[[], R]:
    """Bind a call to a copy of the current context variables for another thread to run.

    A Context can be entered by one thread at a time, so each call gets its own copy.
    """
    context = contextvars.copy_context()

    def run() -> R:
        return context.run(call)

    return run


class VClient:
    """API client for the Valentina API.

    This is the main entry point for interacting with the API. It manages
    the HTTP session and provides access to domain-specific services.

    By default, the client automatically registers itself as the default client
    for use with factory functions like `companies_service()`.

    Example:
        ```python
        from vweb.api_client import VClient, companies_service

        # Client auto-registers as default
        client = VClient(base_url="https://api.example.com", api_key="...")

        # Use factory functions from any module
        companies = companies_service()
        all_companies = companies.list_all()

        # Use scoped services
        users = client.users("company_id")
        all_users = users.list_all()

        campaigns = client.campaigns("company_id", "user_id")
        all_campaigns = campaigns.list_all()
        ```
    """

    def __init__(  # noqa: PLR0913
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        max_retry_delay: float = DEFAULT_MAX_RETRY_DELAY,
        retry_budget: float = DEFAULT_RETRY_BUDGET,
        auto_retry_rate_limit: bool = True,
        auto_idempotency_keys: bool = False,
        default_company_id: str | None = None,
        max_parallel_requests: int = DEFAULT_MAX_PARALLEL_REQUESTS,
        set_as_default: bool = True,
    ) -> None:
        """Initialize the API client.

        Args:
            base_url: Base URL for the API.
            api_key: API key for authentication.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts for failed requests.
            retry_delay: Base delay between retries in seconds.
            max_retry_delay: Longest single wait between retries in seconds. A server
                ``Retry-After`` longer than this raises the error instead of waiting.
            retry_budget: Total seconds one call may spend across all attempts and
                waits. A retry whose wait would overrun it raises the last error instead.
            auto_retry_rate_limit: Automatically retry requests that hit rate limits.
            auto_idempotency_keys: Automatically generate idempotency keys for
                POST/PUT/PATCH requests.
            default_company_id: Default company ID to use when not explicitly provided
                to service factory methods.
            max_parallel_requests: Worker threads in the pool that ``run_parallel`` and
                ``list_all`` methods share. The calling thread also runs work, so one
                call makes up to this many plus one requests at a time. Set to 0 to
                run every request in the calling thread.
            set_as_default: If True, register this client as the default for factory
                functions. Set to False when creating multiple clients or when using
                the context manager pattern exclusively.

        Raises:
            ValueError: If base_url or api_key is empty, or max_parallel_requests is negative.
        """
        if not base_url:
            msg = "base_url is required"
            raise ValueError(msg)
        if not api_key:
            msg = "api_key is required"
            raise ValueError(msg)
        if max_parallel_requests < 0:
            msg = f"max_parallel_requests must be 0 or more, got {max_parallel_requests}"
            raise ValueError(msg)

        self._config = _APIConfig(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            max_retry_delay=max_retry_delay,
            retry_budget=retry_budget,
            auto_retry_rate_limit=auto_retry_rate_limit,
            auto_idempotency_keys=auto_idempotency_keys,
            default_company_id=default_company_id,
            max_parallel_requests=max_parallel_requests,
        )

        self._executor: ThreadPoolExecutor | None = None
        self._executor_closed = False
        self._executor_lock = threading.Lock()
        self._http: httpx2.Client = self._create_http_client()
        self._companies: CompaniesService | None = None
        self._system: SystemService | None = None
        self._user_lookup: UserLookupService | None = None

        if set_as_default:
            from vweb.api_client.registry import configure_default_client

            configure_default_client(self)

        logger.bind(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            max_retries=self._config.max_retries,
        ).info("Initialize VClient")

    def _create_http_client(self) -> httpx2.Client:
        """Create and configure the HTTP client."""
        user_agent = f"{USER_AGENT_PRODUCT} Python/{platform.python_version()}"

        headers = {
            "Accept": "application/json",
            "User-Agent": user_agent,
            API_KEY_HEADER: self._config.api_key,
        }

        return httpx2.Client(
            base_url=self._config.base_url,
            headers=headers,
            timeout=httpx2.Timeout(self._config.timeout),
        )

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client and the worker pool, and release resources.

        Queued parallel work is cancelled. Work already running finishes first so it
        never sends on a closed HTTP client.
        """
        from vweb.api_client.registry import clear_default_client

        logger.bind(base_url=self._config.base_url).info("Close VClient")
        with self._executor_lock:
            executor, self._executor = self._executor, None
            self._executor_closed = True
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        self._http.close()
        clear_default_client(self)

    def _get_executor(self) -> ThreadPoolExecutor:
        """Return the shared worker pool, creating it on first use.

        Raises:
            RuntimeError: If the client is closed.
        """
        with self._executor_lock:
            if self._executor_closed:
                msg = "Cannot run parallel requests on a closed VClient"
                raise RuntimeError(msg)
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._config.max_parallel_requests,
                    thread_name_prefix="vclient",
                )
            return self._executor

    @overload
    def run_parallel[A, B](self, a: Callable[[], A], b: Callable[[], B], /) -> tuple[A, B]: ...

    @overload
    def run_parallel[A, B, C](
        self, a: Callable[[], A], b: Callable[[], B], c: Callable[[], C], /
    ) -> tuple[A, B, C]: ...

    @overload
    def run_parallel[A, B, C, D](
        self,
        a: Callable[[], A],
        b: Callable[[], B],
        c: Callable[[], C],
        d: Callable[[], D],
        /,
    ) -> tuple[A, B, C, D]: ...

    @overload
    def run_parallel[R](self, *calls: Callable[[], R]) -> tuple[R, ...]: ...

    def run_parallel(self, *calls: Callable[[], Any]) -> tuple[Any, ...]:
        """Run independent API calls concurrently and return their results in call order.

        Use to overlap the network wait of calls that do not depend on each other.
        Build services in the calling thread and pass only the calls, such as
        ``functools.partial(users.list_all)``. Each call runs in a copy of the
        caller's context variables, so per-request logging context still applies.

        The calling thread runs the first call itself and any call no worker has
        started yet, so nested use (a parallel call that runs ``list_all``) cannot
        deadlock on a busy pool.

        The first error in call order propagates. Calls not yet started are cancelled,
        and calls already running finish with their results dropped.

        Args:
            *calls: Zero-argument callables to run.

        Returns:
            Each call's result, in the order the calls were given.
        """
        if len(calls) <= 1 or self._config.max_parallel_requests == 0:
            return tuple(call() for call in calls)

        executor = self._get_executor()
        head, *rest = calls
        futures: list[Future[Any]] = [executor.submit(_in_copied_context(call)) for call in rest]
        try:
            results = [head()]
            # cancel() succeeds only for work still queued; running it here keeps the
            # caller busy instead of blocked behind other requests' work.
            results.extend(
                call() if future.cancel() else future.result()
                for call, future in zip(rest, futures, strict=True)
            )
        except BaseException:
            for future in futures:
                future.cancel()
            raise
        return tuple(results)

    @property
    def is_closed(self) -> bool:
        """Check if the client has been closed."""
        return self._http.is_closed

    @property
    def default_company_id(self) -> str | None:
        """Return the default company ID from config."""
        return self._config.default_company_id

    def _resolve_company_id(self, company_id: str | None) -> str:
        """Resolve company_id, falling back to default if not provided.

        Args:
            company_id: Explicitly provided company ID, or None to use default.

        Returns:
            The resolved company ID.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        resolved = company_id or self._config.default_company_id
        if resolved is None:
            msg = "company_id is required (no default_company_id configured)"
            raise ValueError(msg)
        return resolved

    @property
    def companies(self) -> "CompaniesService":
        """Access the Companies service for managing companies.

        Returns:
            The CompaniesService instance for company operations.
        """
        if self._companies is None:
            from vweb.api_client.services.companies import CompaniesService

            self._companies = CompaniesService(self)
        return self._companies

    @property
    def system(self) -> "SystemService":
        """Access the System service for system-level operations.

        Returns:
            The SystemService instance for system operations like health checks.
        """
        if self._system is None:
            from vweb.api_client.services.system import SystemService

            self._system = SystemService(self)
        return self._system

    @property
    def user_lookup(self) -> "UserLookupService":
        """Access the User Lookup service for cross-company user discovery.

        Returns:
            The UserLookupService instance for user lookup operations.
        """
        if self._user_lookup is None:
            from vweb.api_client.services.user_lookup import UserLookupService

            self._user_lookup = UserLookupService(self)
        return self._user_lookup

    def users(self, on_behalf_of: str, *, company_id: str | None = None) -> "UsersService":
        """Get a UsersService scoped to a specific company.

        Provides methods to create, retrieve, update, and delete users,
        as well as access user statistics and assets.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A UsersService instance scoped to the specified company.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            users = client.users("user_id", "company_id")
            all_users = users.list_all()
            user = users.get("user_id")
        """
        from vweb.api_client.services.users import UsersService

        return UsersService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def identity(self, *, company_id: str | None = None) -> "IdentityService":
        """Get a company-scoped IdentityService.

        Resolves verified provider logins (Apple/Google ID tokens,
        Discord/GitHub access tokens) to canonical users. Does not require
        an acting user, only developer API key authentication.

        Args:
            company_id: The ID of the company to resolve identities in. If not
                provided, uses the default_company_id from config.

        Returns:
            An IdentityService instance.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            identity = client.identity()
            result = identity.identify(provider="google", token="<id-token>")
        """
        from vweb.api_client.services.identity import IdentityService

        return IdentityService(self, self._resolve_company_id(company_id))

    def campaigns(
        self,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "CampaignsService":
        """Get a CampaignsService scoped to a specific company.

        Provides methods to create, retrieve, update, and delete campaigns,
        as well as access campaign statistics, assets, and notes.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A CampaignsService instance scoped to the specified company.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            campaigns = client.campaigns("user_id")
            all_campaigns = campaigns.list_all()
            campaign = campaigns.get("campaign_id")
        """
        from vweb.api_client.services.campaigns import CampaignsService

        return CampaignsService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def books(
        self,
        campaign_id: str,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "BooksService":
        """Get a BooksService scoped to a specific company and campaign.

        Provides methods to create, retrieve, update, and delete campaign books,
        as well as access book notes and assets.

        Args:
            campaign_id: The ID of the campaign to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A BooksService instance scoped to the specified context.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            books = client.books("campaign_id", "user_id")
            all_books = books.list_all()
            book = books.get("book_id")
        """
        from vweb.api_client.services.campaign_books import BooksService

        return BooksService(
            self,
            company_id=self._resolve_company_id(company_id),
            campaign_id=campaign_id,
            on_behalf_of=on_behalf_of,
        )

    def chapters(
        self,
        campaign_id: str,
        book_id: str,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "ChaptersService":
        """Get a ChaptersService scoped to a specific company, campaign, and book.

        Provides methods to create, retrieve, update, and delete campaign book chapters,
        as well as access chapter notes and assets.

        Args:
            campaign_id: The ID of the campaign to operate within.
            book_id: The ID of the book to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A ChaptersService instance scoped to the specified context.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            chapters = client.chapters("campaign_id", "book_id", "user_id")
            all_chapters = chapters.list_all()
            chapter = chapters.get("chapter_id")
        """
        from vweb.api_client.services.campaign_book_chapters import ChaptersService

        return ChaptersService(
            self,
            company_id=self._resolve_company_id(company_id),
            campaign_id=campaign_id,
            book_id=book_id,
            on_behalf_of=on_behalf_of,
        )

    def characters(
        self,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "CharactersService":
        """Get a CharactersService scoped to a specific company.

        Provides methods to create, retrieve, update, and delete characters.
        Use the optional ``campaign_id`` filter on list methods to scope to a campaign.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A CharactersService instance scoped to the specified context.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            characters = client.characters("user_id")
            all_characters = characters.list_all()
            character = characters.get("character_id")
        """
        from vweb.api_client.services.characters import CharactersService

        return CharactersService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def character_traits(
        self,
        character_id: str,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "CharacterTraitsService":
        """Get a CharacterTraitsService scoped to a specific company and character.

        Provides methods to create, retrieve, update, and delete character traits within
        a character.

        Args:
            character_id: The ID of the character to operate within.
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Returns:
            A CharacterTraitsService instance scoped to the specified context.

        Raises:
            ValueError: If no company_id provided and no default configured.

        Example:
            character_traits = client.character_traits("character_id", "user_id")
            all_character_traits = character_traits.list_all()
            character_trait = character_traits.get("character_trait_id")
        """
        from vweb.api_client.services.character_traits import CharacterTraitsService

        return CharacterTraitsService(
            self,
            company_id=self._resolve_company_id(company_id),
            character_id=character_id,
            on_behalf_of=on_behalf_of,
        )

    def character_blueprint(
        self, on_behalf_of: str | None = None, *, company_id: str | None = None
    ) -> "CharacterBlueprintService":
        """Get a CharacterBlueprintService scoped to a specific company.

        Provides methods to create, retrieve, update, and delete character blueprint sections,
        categories, and traits.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        from vweb.api_client.services.character_blueprint import CharacterBlueprintService

        return CharacterBlueprintService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def dictionary(
        self, on_behalf_of: str | None = None, *, company_id: str | None = None
    ) -> "DictionaryService":
        """Get a DictionaryService scoped to a specific company.

        Provides methods to create, retrieve, update, and delete dictionary terms.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        from vweb.api_client.services.dictionary import DictionaryService

        return DictionaryService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def dicerolls(
        self,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "DicerollService":
        """Get a DicerollService scoped to a specific company.

        Provides methods to create, retrieve, and list dice rolls.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        from vweb.api_client.services.dicerolls import DicerollService

        return DicerollService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def options(
        self, on_behalf_of: str | None = None, *, company_id: str | None = None
    ) -> "OptionsService":
        """Get a OptionsService scoped to a specific company.

        Provides methods to retrieve all options and enumerations for the api.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        from vweb.api_client.services.options import OptionsService

        return OptionsService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )

    def character_autogen(
        self,
        on_behalf_of: str,
        *,
        company_id: str | None = None,
    ) -> "CharacterAutogenService":
        """Get a CharacterAutogenService scoped to a specific company.

        Provides methods to autogenerate characters and manage chargen sessions.
        Pass ``campaign_id`` directly to ``generate_character()`` and
        ``start_chargen_session()`` to scope each call to a specific campaign.

        Args:
            on_behalf_of: User ID to impersonate via On-Behalf-Of header.
            company_id: The ID of the company to operate within. If not provided,
                uses the default_company_id from config.

        Raises:
            ValueError: If no company_id provided and no default configured.
        """
        from vweb.api_client.services.character_autogen import CharacterAutogenService

        return CharacterAutogenService(
            self, company_id=self._resolve_company_id(company_id), on_behalf_of=on_behalf_of
        )
