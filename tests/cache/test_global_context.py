"""Tests for global context data caching."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from tests.helpers import assert_redirects_to, make_cache_store_mock
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
    FakeResponse,
    Routes,
    UserFactory,
)
from vweb.lib.cache.global_context import GlobalContext, clear, load

if TYPE_CHECKING:
    import httpx2

CO = "test-company-id"
ME = "test-user-id"


@pytest.fixture
def _fake_vclient_data(fake_vclient) -> None:
    """Serve one company, user, campaign, and character from the fake API."""
    company = CompanyFactory.build(
        id=CO, name="Test Company", resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    )
    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.USERS_LIST, items=[UserFactory.build(id=ME, company_id=CO)])
    fake_vclient.set_response(Routes.USERS_UNAPPROVED_LIST, items=[])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=[CampaignFactory.build(id="camp-1")])
    fake_vclient.set_response(Routes.CHARACTERS_LIST, items=[CharacterFactory.build(name="Char 1")])


@pytest.fixture
def mock_cache_store(mocker) -> dict:
    """Provide a dict-backed cache mock for global_context."""
    return make_cache_store_mock(mocker, "vweb.lib.cache.global_context.cache")


def _serve(fake_vclient, *, campaigns: list, characters=None, users=None) -> None:
    fake_vclient.set_response(Routes.COMPANIES_GET, model=CompanyFactory.build(id=CO))
    fake_vclient.set_response(Routes.USERS_LIST, items=users or [UserFactory.build(id=ME)])
    fake_vclient.set_response(Routes.CAMPAIGNS_LIST, items=campaigns)
    if characters is not None:
        fake_vclient.set_response(Routes.CHARACTERS_LIST, items=characters)


@pytest.mark.usefixtures("_fake_vclient_data", "mock_cache_store")
def test_load_matches_sequential_fetches(app, fake_vclient) -> None:
    """Verify a cold load builds the same context as calling each service in turn."""
    with app.app_context():
        company = companies_service().get(CO)
        users = users_service(on_behalf_of=ME, company_id=CO).list_all()
        campaigns = campaigns_service(on_behalf_of=ME, company_id=CO).list_all()
        characters = characters_service(on_behalf_of=ME, company_id=CO).list_all()
        fake_vclient.clear_requests()

        result = load(CO, ME)

    assert result.company == company
    assert result.users == users
    assert result.campaigns == campaigns
    assert result.characters == characters
    assert result.characters_by_campaign == {characters[0].campaign_id: characters}
    assert result.resources_modified_at == "2026-01-01T00:00:00+00:00"
    assert result.pending_user_count == 0
    # The company fetched for the timestamp is reused, not requested twice
    fake_vclient.assert_called(Routes.COMPANIES_GET, params={"company_id": CO}, times=1)
    fake_vclient.assert_not_called(Routes.BOOKS_LIST)
    fake_vclient.assert_not_called(Routes.CHAPTERS_LIST)


@pytest.mark.usefixtures("mock_cache_store")
@pytest.mark.parametrize(("role", "expected"), [("ADMIN", 2), ("PLAYER", 0)])
def test_pending_user_count_only_for_admins(app, fake_vclient, role: str, expected: int) -> None:
    """Verify admins see the pending-user count and others never request it."""
    _serve(fake_vclient, campaigns=[], users=[UserFactory.build(id=ME, role=role)])
    fake_vclient.set_response(
        Routes.USERS_UNAPPROVED_LIST, items=UserFactory.batch(2, role="UNAPPROVED")
    )

    with app.app_context():
        result = load(CO, ME)

    assert result.pending_user_count == expected
    fake_vclient.assert_called(Routes.USERS_UNAPPROVED_LIST, times=1 if expected else 0)


@pytest.mark.usefixtures("mock_cache_store")
def test_load_keeps_every_character_the_api_returns(app, fake_vclient) -> None:
    """Verify the context holds other players' characters too, so routes must filter them."""
    mine = CharacterFactory.build(name="My Char", user_player_id=ME)
    theirs = CharacterFactory.build(name="Other Char", user_player_id="other-user-id")
    _serve(fake_vclient, campaigns=[CampaignFactory.build()], characters=[mine, theirs])

    with app.app_context():
        result = load(CO, ME)

    assert {c.name for c in result.characters} == {"My Char", "Other Char"}


@pytest.mark.usefixtures("mock_cache_store")
@pytest.mark.parametrize("characters_fail", [False, True])
def test_company_without_campaigns_has_no_characters(
    app, fake_vclient, *, characters_fail: bool
) -> None:
    """Verify characters are dropped, and a character error ignored, when there are no campaigns."""
    _serve(fake_vclient, campaigns=[], characters=[CharacterFactory.build()])
    if characters_fail:
        fake_vclient.set_error(Routes.CHARACTERS_LIST, status_code=403)

    with app.app_context():
        result = load(CO, ME)

    assert result.characters == []
    assert result.characters_by_campaign == {}


@pytest.mark.usefixtures("mock_cache_store")
def test_character_error_raises_when_campaigns_exist(app, fake_vclient) -> None:
    """Verify a failed character list still fails when campaigns need those characters."""
    _serve(fake_vclient, campaigns=[CampaignFactory.build()])
    fake_vclient.set_error(Routes.CHARACTERS_LIST, status_code=403)

    with app.app_context(), pytest.raises(AuthorizationError):
        load(CO, ME)


@pytest.mark.usefixtures("_fake_vclient_data")
def test_load_serves_cache_until_cleared(app, fake_vclient, mock_cache_store) -> None:
    """Verify a warm context is reused, and clear forces a rebuild without touching other keys."""
    with app.app_context():
        first = load(CO, ME)
        second = load(CO, ME)
        mock_cache_store["bp_all_traits"] = {"some": "data"}

        clear(CO, ME)
        load(CO, ME)

    assert first is second
    fake_vclient.assert_called(Routes.USERS_LIST, times=2)
    assert "bp_all_traits" in mock_cache_store


@pytest.mark.usefixtures("_fake_vclient_data")
@pytest.mark.parametrize(("changed", "rebuilds"), [(False, 1), (True, 2)])
def test_load_rebuilds_only_when_company_stamp_changes(
    app, fake_vclient, mock_cache_store, *, changed: bool, rebuilds: int
) -> None:
    """Verify an expired timestamp rebuilds the context only when the company has changed."""
    stamps = [datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2 if changed else 1, tzinfo=UTC)]
    fake_vclient.set_responses(
        Routes.COMPANIES_GET,
        [FakeResponse(model=CompanyFactory.build(id=CO, resources_modified_at=s)) for s in stamps],
    )

    with app.app_context():
        load(CO, ME)
        # Simulate the short timestamp TTL expiring
        mock_cache_store.pop(f"global_timestamp:{CO}")
        load(CO, ME)

    fake_vclient.assert_called(Routes.COMPANIES_GET, times=2)
    fake_vclient.assert_called(Routes.USERS_LIST, times=rebuilds)


@pytest.mark.parametrize(
    ("path", "session_user"),
    [("/static/css/style.css", "test-user-id"), ("/", None)],
    ids=["static-path", "logged-out"],
)
def test_hook_skips_context_load(
    app, mock_context_load, path: str, session_user: str | None
) -> None:
    """Verify static files and logged-out requests never load the global context."""
    client = app.test_client()
    if session_user:
        with client.session_transaction() as sess:
            sess["user_id"] = session_user
            sess["company_id"] = CO

    client.get(path)

    mock_context_load.assert_not_called()


def test_hook_retries_on_user_not_found(app, mock_context_load) -> None:
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
    mock_context_load.side_effect = [ctx_without_user, ctx_with_user]

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
    assert mock_context_load.call_count == 2


def test_hook_redirects_when_user_not_found_after_retry(app, use_context) -> None:
    """Verify the hook clears session and redirects when user is not found even after retry."""
    # Given a context that never contains the user
    ctx_no_user = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build(id="other-user")],
        campaigns=[],
        resources_modified_at="2026-01-01T00:00:00+00:00",
    )
    use_context(ctx_no_user)

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
    assert_redirects_to(response, "/")

    # And the session is cleared
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_load_global_context_single_flight_collapses_concurrent_rebuilds(
    app, mocker, fake_vclient
) -> None:
    """Verify concurrent cold rebuilds for one user trigger exactly one full fetch."""
    from vweb.extensions import cache

    # Given a company service and a real GlobalContext for the fetch result
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    fake_vclient.set_response(Routes.COMPANIES_GET, model=mock_company)

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


def test_hook_clears_legacy_session_without_company(app, mock_context_load) -> None:
    """Verify a legacy session lacking company_id is cleared and redirected to login."""
    # Given an authenticated session with no company scope (pre-multi-company shape)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"

    # When requesting a context-backed page
    response = client.get("/home")

    # Then the session is cleared, the user is redirected, and no context load was attempted
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    mock_context_load.assert_not_called()


@pytest.mark.usefixtures("_fake_vclient_data")
def test_load_sends_requests_concurrently(app, fake_vclient, mocker, mock_cache_store) -> None:
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

    # When loading a cold context
    with app.app_context():
        load("test-company-id", "test-user-id")

    # Then more than one request was in flight at once
    assert peak > 1
