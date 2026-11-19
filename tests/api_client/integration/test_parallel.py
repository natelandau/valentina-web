"""Tests for parallel page fetches and the client's shared worker pool."""

import contextvars
import threading
from collections.abc import Callable, Iterator
from functools import partial
from math import ceil

import httpx
import pytest
import respx

from tests.api_client.payloads import endpoint_url, page, wire
from vweb.api_client import VClient
from vweb.api_client.constants import ON_BEHALF_OF_HEADER
from vweb.api_client.endpoints import Endpoints
from vweb.api_client.exceptions import NotFoundError
from vweb.api_client.routes import Routes
from vweb.api_client.testing import UserFactory

COMPANY_ID = "company-1"
USER_ID = "acting-user"


@pytest.fixture
def client(base_url, api_key) -> Iterator[VClient]:
    """Return a client with two pool workers so page order is not fetch order."""
    client = VClient(
        base_url=base_url, api_key=api_key, max_parallel_requests=2, set_as_default=False
    )
    yield client
    client.close()


def _users_url(base_url: str) -> str:
    return endpoint_url(base_url, Endpoints.USERS, company_id=COMPANY_ID)


def _page_handler(
    users: list[dict],
    *,
    limit: int,
    total: int | None = None,
    hold_offset: int | None = None,
) -> tuple[Callable[[httpx.Request], respx.MockResponse], list[httpx.Request], list[str]]:
    """Build a respx side effect that serves ``users`` by the request's offset.

    The page at ``hold_offset`` is not answered until every other page has been
    requested, so the remaining pages are in flight on pool workers before it finishes.
    """
    total = len(users) if total is None else total
    page_count = ceil(total / limit)
    seen: list[httpx.Request] = []
    threads: list[str] = []
    lock = threading.Lock()
    all_requested = threading.Event()

    def handler(request: httpx.Request) -> respx.MockResponse:
        offset = int(request.url.params["offset"])
        with lock:
            seen.append(request)
            threads.append(threading.current_thread().name)
            if len(seen) == page_count:
                all_requested.set()
        if offset == hold_offset:
            assert all_requested.wait(timeout=5), "other pages were never requested"
        return respx.MockResponse(
            200,
            json=page(*users[offset : offset + limit], limit=limit, offset=offset, total=total),
        )

    return handler, seen, threads


class TestListAllParallel:
    """Verify list_all fetches pages concurrently and keeps their order."""

    @respx.mock
    def test_returns_items_in_offset_order_when_pages_finish_out_of_order(self, client, base_url):
        """Verify a slow early page does not reorder the result."""
        # Given: Seven users served two per page, with the second page answered last
        users = [wire(UserFactory.build(id=f"u{i}")) for i in range(7)]
        handler, seen, _ = _page_handler(users, limit=2, hold_offset=2)
        respx.get(_users_url(base_url)).mock(side_effect=handler)

        # When: Listing every user with a page size of two
        result = _list_users(client, limit=2)

        # Then: Items come back in offset order and each page was requested once
        assert [user.id for user in result] == [f"u{i}" for i in range(7)]
        assert sorted(int(r.url.params["offset"]) for r in seen) == [0, 2, 4, 6]

    @respx.mock
    def test_pages_keep_filters_and_on_behalf_of_header(self, client, base_url):
        """Verify pages fetched on worker threads send the same query and headers."""
        # Given: Five users served two per page
        users = [wire(UserFactory.build(id=f"u{i}")) for i in range(5)]
        handler, seen, threads = _page_handler(users, limit=2, hold_offset=2)
        respx.get(_users_url(base_url)).mock(side_effect=handler)

        # When: Listing users with a filter
        client.users(USER_ID, company_id=COMPANY_ID).list_all(email="a@example.com")

        # Then: Every page carried the filter, the page limit, and the acting user
        assert len(seen) == 3
        for request in seen:
            assert request.url.params["email"] == "a@example.com"
            assert request.url.params["limit"] == "100"
            assert request.headers[ON_BEHALF_OF_HEADER] == USER_ID
        # Then: At least one later page ran on a pool worker
        assert any(name.startswith("vclient") for name in threads)

    @respx.mock
    def test_single_page_makes_one_request(self, client, base_url):
        """Verify a collection that fits in one page needs no further requests."""
        # Given: Two users that fit in the first page
        users = [wire(UserFactory.build(id=f"u{i}")) for i in range(2)]
        handler, seen, _ = _page_handler(users, limit=100)
        respx.get(_users_url(base_url)).mock(side_effect=handler)

        # When: Listing every user
        result = client.users(USER_ID, company_id=COMPANY_ID).list_all()

        # Then: One request returned both users
        assert [user.id for user in result] == ["u0", "u1"]
        assert len(seen) == 1

    @respx.mock
    def test_trusts_the_first_page_total(self, client, base_url):
        """Verify offsets come from the first page even if a later page reports more items."""
        # Given: A first page that reports three users, then a collection that grows
        users = [wire(UserFactory.build(id=f"u{i}")) for i in range(6)]

        def handler(request: httpx.Request) -> respx.MockResponse:
            offset = int(request.url.params["offset"])
            total = 3 if offset == 0 else 6
            items = users[offset : offset + 2]
            return respx.MockResponse(200, json=page(*items, limit=2, offset=offset, total=total))

        route = respx.get(_users_url(base_url)).mock(side_effect=handler)

        # When: Listing every user
        result = _list_users(client, limit=2)

        # Then: Only the offsets the first page implied were requested
        assert route.call_count == 2
        assert [user.id for user in result] == ["u0", "u1", "u2", "u3"]

    @respx.mock
    def test_page_error_propagates(self, client, base_url):
        """Verify an error on any later page is raised from list_all."""
        # Given: Six users where the page at offset four fails
        users = [wire(UserFactory.build(id=f"u{i}")) for i in range(6)]
        handler, _, _ = _page_handler(users, limit=2)

        def failing(request: httpx.Request) -> respx.MockResponse:
            if request.url.params["offset"] == "4":
                return respx.MockResponse(404, json={"detail": "gone"})
            return handler(request)

        respx.get(_users_url(base_url)).mock(side_effect=failing)

        # When/Then: Listing every user raises the page's error
        with pytest.raises(NotFoundError):
            _list_users(client, limit=2)


def _list_users(client: VClient, *, limit: int) -> list:
    """List every user through the paginated users route with a custom page size."""
    service = client.users(USER_ID, company_id=COMPANY_ID)
    return service._list_all(Routes.USERS_LIST, limit=limit)


class TestRunParallel:
    """Verify VClient.run_parallel runs calls concurrently and safely."""

    def test_returns_results_in_call_order(self, client):
        """Verify results line up with the calls, not with finish order."""
        # Given: Calls where the first finishes only after the last has run
        last_ran = threading.Event()

        def slow() -> str:
            last_ran.wait(timeout=5)
            return "slow"

        def faster() -> str:
            last_ran.set()
            return "faster"

        # When: Running them in parallel
        results = client.run_parallel(slow, lambda: "fast", faster)

        # Then: Results follow call order
        assert results == ("slow", "fast", "faster")

    def test_raises_first_error_and_cancels_queued_calls(self, base_url, api_key):
        """Verify an error is raised and calls no worker has started never run."""
        # Given: One worker held busy, so the last call stays queued
        client = VClient(
            base_url=base_url, api_key=api_key, max_parallel_requests=1, set_as_default=False
        )
        release = threading.Event()
        started = threading.Event()
        ran_late: list[bool] = []

        def busy() -> None:
            started.set()
            release.wait(timeout=5)

        def fail() -> None:
            started.wait(timeout=5)
            msg = "boom"
            raise ValueError(msg)

        # When: The caller's own call fails while the last call is still queued
        with pytest.raises(ValueError, match="boom"):
            client.run_parallel(fail, busy, lambda: ran_late.append(True))
        release.set()
        client.close()

        # Then: The queued call was cancelled
        assert ran_late == []

    def test_calls_see_the_callers_context_variables(self, client):
        """Verify per-request context, such as logging context, reaches worker threads."""
        # Given: A context variable set in the calling thread
        request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")
        request_id.set("req-1")

        # When: Reading it from parallel calls
        results = client.run_parallel(*(request_id.get for _ in range(4)))

        # Then: Every call saw the caller's value
        assert results == ("req-1",) * 4

    def test_nested_use_does_not_deadlock(self, base_url, api_key):
        """Verify parallel calls that themselves run parallel work finish with one worker."""
        # Given: A client with a single worker
        with VClient(
            base_url=base_url, api_key=api_key, max_parallel_requests=1, set_as_default=False
        ) as client:
            inner = partial(client.run_parallel, lambda: 1, lambda: 2, lambda: 3)

            # When: Each outer call runs its own parallel batch
            results = client.run_parallel(inner, inner, inner)

        # Then: All batches complete
        assert results == ((1, 2, 3),) * 3

    def test_zero_workers_runs_in_the_calling_thread(self, base_url, api_key):
        """Verify max_parallel_requests=0 turns parallelism off."""
        # Given: A client with parallelism off
        with VClient(
            base_url=base_url, api_key=api_key, max_parallel_requests=0, set_as_default=False
        ) as client:
            # When: Running several calls
            names = client.run_parallel(*(lambda: threading.current_thread().name,) * 3)

            # Then: All ran on the calling thread and no pool was created
            assert set(names) == {threading.current_thread().name}
            assert client._executor is None

    def test_negative_worker_count_is_rejected(self, base_url, api_key):
        """Verify a negative max_parallel_requests fails fast."""
        with pytest.raises(ValueError, match="max_parallel_requests"):
            VClient(base_url=base_url, api_key=api_key, max_parallel_requests=-1)

    def test_close_shuts_down_the_pool(self, base_url, api_key):
        """Verify close stops the worker threads and refuses later parallel work."""
        # Given: A client whose pool has started worker threads
        client = VClient(
            base_url=base_url, api_key=api_key, max_parallel_requests=2, set_as_default=False
        )
        workers: list[threading.Thread] = []
        worker_ran = threading.Event()

        def record() -> None:
            workers.append(threading.current_thread())
            worker_ran.set()

        # The caller's own call waits so the queued calls reach the pool instead of
        # being run on the calling thread.
        client.run_parallel(partial(worker_ran.wait, timeout=5), record, record)
        pool_threads = [t for t in workers if t.name.startswith("vclient")]
        assert pool_threads

        # When: Closing the client
        client.close()

        # Then: The worker threads have exited and new parallel work is refused
        assert not any(thread.is_alive() for thread in pool_threads)
        with pytest.raises(RuntimeError, match="closed"):
            client.run_parallel(lambda: 1, lambda: 2)
