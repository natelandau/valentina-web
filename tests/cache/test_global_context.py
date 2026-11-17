"""Tests for global context data caching."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from tests.helpers import make_cache_store_mock
from vweb.api_client import (
    campaigns_service,
    characters_service,
    companies_service,
    users_service,
)
from vweb.api_client.exceptions import AuthorizationError
from vweb.api_client.testing import (
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    Routes,
    UserFactory,
)
from vweb.lib.cache.global_context import (
    GlobalContext,
    _fetch_global_data,
    clear,
    load,
)

if TYPE_CHECKING:
    import httpx2


@pytest.fixture
def _fake_vclient_data(fake_vclient) -> None:
    """Set up FakeVClient with known data for _fetch_global_data tests."""
    company = CompanyFactory.build(
        id="test-company-id",
        name="Test Company",
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)

    user = UserFactory.build(id="test-user-id", username="test-user", company_id="test-company-id")
    fake_vclient.set_response(Routes.USERS_LIST, items=[user])
    fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[])

    campaign = CampaignFactory.build(id="camp-1", name="Campaign 1")
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[campaign])

    character = CharacterFactory.build(name="Char 1")
    fake_vclient.set_response(Routes.CHARACTERS_LIST, items=[character])


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for global_context."""
    return make_cache_store_mock(mocker, "vweb.lib.cache.global_context.cache")


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_returns_global_context(app) -> None:
    """Verify _fetch_global_data returns a populated GlobalContext."""
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    assert isinstance(result, GlobalContext)
    assert result.company.name == "Test Company"


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_returns_timestamp(app) -> None:
    """Verify _fetch_global_data stores the company's resources_modified_at as ISO string."""
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    assert result.resources_modified_at == "2026-01-01T00:00:00+00:00"


def test_fetch_global_data_admin_populates_pending_user_count(app, fake_vclient) -> None:
    """Verify pending_user_count reflects the unapproved-users total when user is ADMIN."""
    # Given an ADMIN requesting user and two pending users on the company
    company = CompanyFactory.build(id="test-company-id")
    admin = UserFactory.build(id="admin-id", role="ADMIN", company_id="test-company-id")
    pending = UserFactory.batch(2, role="UNAPPROVED", company_id="test-company-id")

    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.USERS_LIST, items=[admin])
    fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=pending)
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[])

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "admin-id")

    # Then pending_user_count matches the unapproved-users total
    assert result.pending_user_count == 2


def test_fetch_global_data_non_admin_skips_pending_user_count(app, fake_vclient) -> None:
    """Verify pending_user_count stays 0 for non-admins (no unapproved-users call)."""
    # Given a PLAYER requesting user
    company = CompanyFactory.build(id="test-company-id")
    player = UserFactory.build(id="player-id", role="PLAYER", company_id="test-company-id")

    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.USERS_LIST, items=[player])
    # The unapproved-users route is intentionally not registered — calling it would 404
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[])

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "player-id")

    # Then pending_user_count is 0 and the unapproved endpoint was never called
    assert result.pending_user_count == 0


@pytest.mark.usefixtures("mock_cache_store")
def test_load_global_context_returns_cached_on_same_timestamp(
    app, mocker, mock_global_context
) -> None:
    """Verify load returns cached data when company timestamp hasn't changed."""
    # Given a company whose timestamp stays the same
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    mock_fetch = mocker.patch(
        "vweb.lib.cache.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    # When load is called twice
    with app.app_context():
        clear("test-company-id", "test-user-id")
        first = load("test-company-id", "test-user-id")
        second = load("test-company-id", "test-user-id")

    # Then _fetch_global_data is called only once
    assert first is second
    mock_fetch.assert_called_once()


def test_load_global_context_refetches_on_new_timestamp(
    app, mocker, mock_global_context, mock_cache_store
) -> None:
    """Verify load re-fetches data when company timestamp changes."""
    # Given a company whose timestamp changes between calls
    mock_company_v1 = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_v2 = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.side_effect = [mock_company_v1, mock_company_v2]
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    # Given _fetch_global_data returns different GlobalContexts
    ctx_v2 = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build()],
        campaigns=[],
        resources_modified_at="2026-01-02T00:00:00+00:00",
    )
    mock_fetch = mocker.patch(
        "vweb.lib.cache.global_context._fetch_global_data",
        side_effect=[mock_global_context, ctx_v2],
    )

    # When load is called, timestamp expires, then called again
    with app.app_context():
        clear("test-company-id", "test-user-id")
        first = load("test-company-id", "test-user-id")
        mock_cache_store.pop("global_timestamp:test-company-id", None)
        second = load("test-company-id", "test-user-id")

    # Then _fetch_global_data is called twice (data was refreshed)
    assert first is not second
    assert mock_fetch.call_count == 2


@pytest.mark.usefixtures("mock_cache_store")
def test_clear_global_context_cache_deletes_only_global_keys(
    app, mocker, mock_global_context, mock_cache_store
) -> None:
    """Verify clear deletes only global context keys."""
    # Given a company with a stable timestamp
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    mock_fetch = mocker.patch(
        "vweb.lib.cache.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    with app.app_context():
        # Given global context is loaded and an unrelated key exists
        load("test-company-id", "test-user-id")
        mock_cache_store["bp_all_traits"] = {"some": "data"}

        # When clear is called
        clear("test-company-id", "test-user-id")

        # Then global context requires a re-fetch
        load("test-company-id", "test-user-id")
        assert mock_fetch.call_count == 2

        # And unrelated cache keys are preserved
        assert "bp_all_traits" in mock_cache_store


def test_before_request_sets_g_global_context(client, mocker, mock_global_context) -> None:
    """Verify the before_request hook populates g.global_context for normal requests."""
    # Given a mocked load that returns a real GlobalContext
    mocker.patch(
        "vweb.lib.cache.global_context.load",
        return_value=mock_global_context,
    )

    # When a normal page request is made
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
    response = client.get("/", follow_redirects=True)

    # Then the request succeeds (hook ran without error)
    assert response.status_code == 200


def test_before_request_skips_static(app, mocker) -> None:
    """Verify the before_request hook does not call load for static paths."""
    # Given a mocked load
    mock_load = mocker.patch("vweb.lib.cache.global_context.load")

    # When a static file request is made
    with app.test_request_context("/static/css/style.css"):
        from flask import session

        session["user_id"] = "test-user-id"
        for func in app.before_request_funcs.get(None, []):
            func()

    # Then load was never called
    mock_load.assert_not_called()


def test_before_request_skips_without_user_id(app, mocker) -> None:
    """Verify the before_request hook skips when no user_id is in session."""
    # Given a mocked load
    mock_load = mocker.patch("vweb.lib.cache.global_context.load")

    # When a request is made without user_id in session
    with app.test_request_context("/"):
        for func in app.before_request_funcs.get(None, []):
            if func.__name__ == "inject_global_context":
                func()

    # Then load was never called
    mock_load.assert_not_called()


def test_fetch_global_data_returns_all_characters_unfiltered(app, fake_vclient) -> None:
    """Verify _fetch_global_data returns all characters, not just the requesting user's."""
    # Given a company, users, and campaigns are set up
    company = CompanyFactory.build(
        id="test-company-id",
        name="Test Company",
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    user = UserFactory.build(id="test-user-id", username="test-user", company_id="test-company-id")
    fake_vclient.set_response(Routes.USERS_LIST, items=[user])
    campaign = CampaignFactory.build(id="camp-1", name="Campaign 1")
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[campaign])

    # Given characters belonging to different users
    my_char = CharacterFactory.build(name="My Char", user_player_id="test-user-id")
    other_char = CharacterFactory.build(name="Other Char", user_player_id="other-user-id")
    fake_vclient.set_response(
        Routes.CHARACTERS_LIST,
        items=[my_char, other_char],
    )

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then both characters are returned
    assert len(result.characters) == 2
    char_names = {c.name for c in result.characters}
    assert "My Char" in char_names
    assert "Other Char" in char_names


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_does_not_fetch_books_or_chapters(app, mocker) -> None:
    """Verify _fetch_global_data no longer eagerly fans out to books and chapters."""
    # Given the book and chapter services would raise if invoked
    book_svc = mocker.patch("vweb.lib.cache.global_context.books_service", create=True)
    chapter_svc = mocker.patch("vweb.lib.cache.global_context.chapters_service", create=True)

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then characters are still populated but no book/chapter fetch occurred
    assert len(result.characters) == 1
    book_svc.assert_not_called()
    chapter_svc.assert_not_called()


def test_hook_retries_on_user_not_found(app, mocker) -> None:
    """Verify the hook refreshes the cache and retries when the user is not in the context."""
    # Given a first context without the user, and a second context with the user
    ctx_without_user = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build(id="other-user")],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    user = UserFactory.build(id="test-user-id")
    ctx_with_user = GlobalContext(
        company=CompanyFactory.build(),
        users=[user],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mock_load = mocker.patch(
        "vweb.lib.cache.global_context.load",
        side_effect=[ctx_without_user, ctx_with_user],
    )
    mocker.patch("vweb.lib.cache.global_context.clear")

    # When a request is made with a session user_id
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
        sess["company_id"] = "test-company-id"
        sess["companies"] = {
            "test-company-id": {
                "user_id": "test-user-id",
                "company_name": "Test",
                "role": "PLAYER",
            },
        }
    response = client.get("/")

    # Then the hook retried and the request proceeded to the entry redirect
    # (zero campaigns now route to the company hub instead of rendering inline)
    assert response.status_code == 302
    assert "/home" in response.headers["Location"]
    assert mock_load.call_count == 2


def test_hook_redirects_when_user_not_found_after_retry(app, mocker) -> None:
    """Verify the hook clears session and redirects when user is not found even after retry."""
    # Given a context that never contains the user
    ctx_no_user = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build(id="other-user")],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx_no_user)
    mocker.patch("vweb.lib.cache.global_context.clear")

    # When a request is made to a protected route
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
        sess["company_id"] = "test-company-id"
        sess["companies"] = {
            "test-company-id": {
                "user_id": "test-user-id",
                "company_name": "Test",
                "role": "PLAYER",
            },
        }
    response = client.get("/character/some-id")

    # Then the user is redirected to the landing page
    assert response.status_code == 302
    assert response.location == "/"

    # And the session is cleared
    with client.session_transaction() as sess:
        assert "user_id" not in sess


@pytest.mark.usefixtures("mock_cache_store")
def test_load_global_context_fetches_company_once_on_cold_cache(
    app, mocker, mock_global_context
) -> None:
    """Verify a cold load fetches the company once, not twice (timestamp + fetch)."""
    # Given a company service and a real _fetch_global_data that reuses the company
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    # Given _fetch_global_data is patched so we isolate the company-fetch behavior
    mocker.patch(
        "vweb.lib.cache.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    # When load runs against a cold cache
    with app.app_context():
        clear("test-company-id", "test-user-id")
        load("test-company-id", "test-user-id")

    # Then the company is fetched exactly once (reused for the timestamp and fetch)
    mock_company_svc.get.assert_called_once()


@pytest.mark.usefixtures("mock_cache_store")
def test_load_global_context_passes_company_to_fetch(app, mocker, mock_global_context) -> None:
    """Verify the cold-path company is handed to _fetch_global_data to avoid a refetch."""
    # Given a known company returned for the timestamp lookup
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    mock_fetch = mocker.patch(
        "vweb.lib.cache.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    # When load runs against a cold cache
    with app.app_context():
        clear("test-company-id", "test-user-id")
        load("test-company-id", "test-user-id")

    # Then the pre-fetched company is forwarded so _fetch_global_data skips its own get
    assert mock_fetch.call_args.kwargs["company"] is mock_company


def test_single_flight_lock_registry_stable_per_key() -> None:
    """Verify the single-flight lock registry returns the same lock per key and distinct locks per key."""
    from vweb.lib.cache.base import _lock_for

    # Given two distinct context keys
    # Then the same key yields the same lock, and distinct keys yield distinct locks
    assert _lock_for("global_ctx:a:b") is _lock_for("global_ctx:a:b")
    assert _lock_for("global_ctx:a:b") is not _lock_for("global_ctx:c:d")


def test_load_global_context_single_flight_collapses_concurrent_rebuilds(app, mocker) -> None:
    """Verify concurrent cold rebuilds for one user trigger exactly one full fetch."""
    from vweb.extensions import cache

    # Given a company service and a real GlobalContext for the fetch result
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.cache.global_context.companies_service", return_value=mock_company_svc)

    built_context = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build(id="test-user-id")],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )

    # Given a fetch that blocks inside the lock so a second thread must queue behind it
    fetch_count = 0
    entered = threading.Event()
    release = threading.Event()

    def blocking_fetch(*_args, **_kwargs) -> GlobalContext:
        nonlocal fetch_count
        fetch_count += 1
        entered.set()
        # Block so the second thread is forced to wait on the single-flight lock,
        # making the race deterministic rather than timing-dependent.
        release.wait(timeout=5)
        return built_context

    mocker.patch("vweb.lib.cache.global_context._fetch_global_data", side_effect=blocking_fetch)

    results: dict[str, GlobalContext] = {}

    def worker(name: str) -> None:
        with app.app_context():
            results[name] = load("test-company-id", "test-user-id")

    with app.app_context():
        clear("test-company-id", "test-user-id")
        cache.clear()

    # When thread A enters the rebuild and blocks, then thread B starts and queues
    thread_a = threading.Thread(target=worker, args=("a",))
    thread_a.start()
    assert entered.wait(timeout=5), "thread A never entered _fetch_global_data"

    thread_b = threading.Thread(target=worker, args=("b",))
    thread_b.start()
    # Give B a moment to reach and block on the single-flight lock before releasing A.
    threading.Event().wait(0.1)
    release.set()

    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    # Then both threads finished without hanging
    assert not thread_a.is_alive(), "thread A hung"
    assert not thread_b.is_alive(), "thread B hung"

    # Then exactly one full rebuild ran (thread B reused the rebuilt context via the
    # double-check rather than fetching again). Thread B's copy comes back through the
    # cache (SimpleCache pickles on set), so it is equal but not identical.
    assert fetch_count == 1
    assert results["a"] is built_context
    assert results["b"] == built_context


def test_hook_clears_legacy_session_without_company(app, mocker) -> None:
    """Verify a legacy session lacking company_id is cleared and redirected to login."""
    # Given an authenticated session with no company scope (pre-multi-company shape)
    mock_load = mocker.patch("vweb.lib.cache.global_context.load")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"

    # When requesting a context-backed page
    response = client.get("/home")

    # Then the session is cleared, the user is redirected, and no context load was attempted
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    mock_load.assert_not_called()


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_matches_sequential_fetches(app) -> None:
    """Verify the concurrent fetch builds the same context as calling each service in turn."""
    # Given the services the global context reads, called one after another
    with app.app_context():
        company = companies_service().get("test-company-id")
        users = users_service(on_behalf_of="test-user-id", company_id="test-company-id").list_all()
        campaigns = campaigns_service(
            on_behalf_of="test-user-id", company_id="test-company-id"
        ).list_all()
        characters = characters_service(
            on_behalf_of="test-user-id", company_id="test-company-id"
        ).list_all()

        # When fetching global data
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then every field matches the sequential results
    assert result.company == company
    assert result.users == users
    assert result.campaigns == campaigns
    assert result.characters == characters
    assert result.characters_by_campaign == {characters[0].campaign_id: characters}
    assert result.pending_user_count == 0


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_sends_requests_concurrently(app, fake_vclient, mocker) -> None:
    """Verify the independent fetches overlap instead of waiting on each other."""
    # Given a fake API where every response takes a moment and in-flight calls are counted
    router = fake_vclient._router
    finalize = router._finalize
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def slow_finalize(response: httpx2.Response) -> httpx2.Response:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return finalize(response)

    mocker.patch.object(router, "_finalize", side_effect=slow_finalize)

    # When fetching global data without a pre-fetched company
    with app.app_context():
        _fetch_global_data("test-company-id", "test-user-id")

    # Then more than one request was in flight at once
    assert peak > 1


def test_fetch_global_data_drops_characters_without_campaigns(app, fake_vclient) -> None:
    """Verify characters fetched alongside campaigns are not exposed when there are none."""
    # Given a company with no campaigns but a character the API would list
    fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build())
    fake_vclient.set_response(Routes.USERS_LIST, items=[UserFactory.build(id="test-user-id")])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[])
    fake_vclient.set_response(Routes.CHARACTERS_LIST, items=[CharacterFactory.build()])

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then no characters are exposed
    assert result.characters == []
    assert result.characters_by_campaign == {}


def test_fetch_global_data_ignores_character_error_without_campaigns(app, fake_vclient) -> None:
    """Verify a failed character list does not fail a company that has no campaigns."""
    # Given a company with no campaigns where listing characters fails
    fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build())
    fake_vclient.set_response(Routes.USERS_LIST, items=[UserFactory.build(id="test-user-id")])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[])
    fake_vclient.set_error(Routes.CHARACTERS_LIST, status_code=403)

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then the context builds without characters
    assert result.characters == []


def test_fetch_global_data_raises_character_error_with_campaigns(app, fake_vclient) -> None:
    """Verify a failed character list still fails when campaigns need those characters."""
    # Given a company with a campaign where listing characters fails
    fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build())
    fake_vclient.set_response(Routes.USERS_LIST, items=[UserFactory.build(id="test-user-id")])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[CampaignFactory.build()])
    fake_vclient.set_error(Routes.CHARACTERS_LIST, status_code=403)

    # When/Then fetching global data raises the character error
    with app.app_context(), pytest.raises(AuthorizationError):
        _fetch_global_data("test-company-id", "test-user-id")


def test_fetch_global_data_reuses_given_company(app, fake_vclient) -> None:
    """Verify a pre-fetched company is used instead of requesting it again."""
    # Given a pre-fetched company and an API whose company route would fail
    company = CompanyFactory.build(id="test-company-id", name="Prefetched")
    fake_vclient.set_error(Routes.COMPANIES_GET, status_code=500)
    fake_vclient.set_response(Routes.USERS_LIST, items=[UserFactory.build(id="test-user-id")])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[])

    # When fetching global data with that company
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id", company=company)

    # Then the given company is in the context
    assert result.company.name == "Prefetched"
