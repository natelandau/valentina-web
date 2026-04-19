"""Tests for global context data caching."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from vclient.testing import (
    CampaignBookFactory,
    CampaignFactory,
    CharacterFactory,
    CompanyFactory,
    Routes,
    UserFactory,
)

from tests.helpers import make_cache_store_mock
from vweb.lib.global_context import (
    GlobalContext,
    _fetch_global_data,
    clear_global_context_cache,
    load_global_context,
)


@pytest.fixture
def _fake_vclient_data(fake_vclient) -> None:
    """Set up SyncFakeVClient with known data for _fetch_global_data tests."""
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
    return make_cache_store_mock(mocker, "vweb.lib.global_context.cache")


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
    """Verify pending_user_count reflects list_all_unapproved when user is ADMIN."""
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

    # Then pending_user_count matches the unapproved list length
    assert result.pending_user_count == 2


def test_fetch_global_data_non_admin_skips_pending_user_count(app, fake_vclient) -> None:
    """Verify pending_user_count stays 0 for non-admins (no list_all_unapproved call)."""
    # Given a PLAYER requesting user
    company = CompanyFactory.build(id="test-company-id")
    player = UserFactory.build(id="player-id", role="PLAYER", company_id="test-company-id")

    fake_vclient.set_response(Routes.COMPANIES_GET, model=company)
    fake_vclient.set_response(Routes.USERS_LIST, items=[player])
    # list_all_unapproved intentionally not registered — calling it would 404
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
    """Verify load_global_context returns cached data when company timestamp hasn't changed."""
    # Given a company whose timestamp stays the same
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.global_context.sync_companies_service", return_value=mock_company_svc)

    mock_fetch = mocker.patch(
        "vweb.lib.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    # When load_global_context is called twice
    with app.app_context():
        clear_global_context_cache("test-company-id", "test-user-id")
        first = load_global_context("test-company-id", "test-user-id")
        second = load_global_context("test-company-id", "test-user-id")

    # Then _fetch_global_data is called only once
    assert first is second
    mock_fetch.assert_called_once()


def test_load_global_context_refetches_on_new_timestamp(
    app, mocker, mock_global_context, mock_cache_store
) -> None:
    """Verify load_global_context re-fetches data when company timestamp changes."""
    # Given a company whose timestamp changes between calls
    mock_company_v1 = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_v2 = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.side_effect = [mock_company_v1, mock_company_v2]
    mocker.patch("vweb.lib.global_context.sync_companies_service", return_value=mock_company_svc)

    # Given _fetch_global_data returns different GlobalContexts
    ctx_v2 = GlobalContext(
        company=CompanyFactory.build(),
        users=[UserFactory.build()],
        campaigns=[],
        resources_modified_at="2026-01-02T00:00:00+00:00",
    )
    mock_fetch = mocker.patch(
        "vweb.lib.global_context._fetch_global_data",
        side_effect=[mock_global_context, ctx_v2],
    )

    # When load_global_context is called, timestamp expires, then called again
    with app.app_context():
        clear_global_context_cache("test-company-id", "test-user-id")
        first = load_global_context("test-company-id", "test-user-id")
        mock_cache_store.pop("global_timestamp:test-company-id", None)
        second = load_global_context("test-company-id", "test-user-id")

    # Then _fetch_global_data is called twice (data was refreshed)
    assert first is not second
    assert mock_fetch.call_count == 2


@pytest.mark.usefixtures("mock_cache_store")
def test_clear_global_context_cache_deletes_only_global_keys(
    app, mocker, mock_global_context, mock_cache_store
) -> None:
    """Verify clear_global_context_cache deletes only global context keys."""
    # Given a company with a stable timestamp
    mock_company = CompanyFactory.build(
        resources_modified_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    )
    mock_company_svc = mocker.MagicMock()
    mock_company_svc.get.return_value = mock_company
    mocker.patch("vweb.lib.global_context.sync_companies_service", return_value=mock_company_svc)

    mock_fetch = mocker.patch(
        "vweb.lib.global_context._fetch_global_data",
        return_value=mock_global_context,
    )

    with app.app_context():
        # Given global context is loaded and an unrelated key exists
        load_global_context("test-company-id", "test-user-id")
        mock_cache_store["bp_all_traits"] = {"some": "data"}

        # When clear_global_context_cache is called
        clear_global_context_cache("test-company-id", "test-user-id")

        # Then global context requires a re-fetch
        load_global_context("test-company-id", "test-user-id")
        assert mock_fetch.call_count == 2

        # And unrelated cache keys are preserved
        assert "bp_all_traits" in mock_cache_store


def test_before_request_sets_g_global_context(client, mocker, mock_global_context) -> None:
    """Verify the before_request hook populates g.global_context for normal requests."""
    # Given a mocked load_global_context that returns a real GlobalContext
    mocker.patch(
        "vweb.lib.hooks.load_global_context",
        return_value=mock_global_context,
    )

    # When a normal page request is made
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
    response = client.get("/", follow_redirects=True)

    # Then the request succeeds (hook ran without error)
    assert response.status_code == 200


def test_before_request_skips_static(app, mocker) -> None:
    """Verify the before_request hook does not call load_global_context for static paths."""
    # Given a mocked load_global_context
    mock_load = mocker.patch("vweb.lib.hooks.load_global_context")

    # When a static file request is made
    with app.test_request_context("/static/css/style.css"):
        from flask import session

        session["user_id"] = "test-user-id"
        for func in app.before_request_funcs.get(None, []):
            func()

    # Then load_global_context was never called
    mock_load.assert_not_called()


def test_before_request_skips_without_user_id(app, mocker) -> None:
    """Verify the before_request hook skips when no user_id is in session."""
    # Given a mocked load_global_context
    mock_load = mocker.patch("vweb.lib.hooks.load_global_context")

    # When a request is made without user_id in session
    with app.test_request_context("/"):
        for func in app.before_request_funcs.get(None, []):
            if func.__name__ == "inject_global_context":
                func()

    # Then load_global_context was never called
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


@pytest.mark.usefixtures("mock_cache_store")
def test_get_campaign_statistics_returns_stats(app, mocker) -> None:
    """Verify get_campaign_statistics fetches and returns campaign statistics."""
    from vclient.testing import CompanyFactory, RollStatisticsFactory, UserFactory

    from vweb.lib.global_context import GlobalContext, get_campaign_statistics

    # Given a mocked campaigns service returning stats
    expected_stats = RollStatisticsFactory.build()
    mock_svc = mocker.MagicMock()
    mock_svc.get_statistics.return_value = expected_stats
    mocker.patch("vweb.lib.global_context.sync_campaigns_service", return_value=mock_svc)

    # When fetching campaign statistics
    with app.test_request_context():
        from flask import g

        g.requesting_user = UserFactory.build(id="test-user-id")
        g.global_context = GlobalContext(
            company=CompanyFactory.build(id="test-company-id"),
            users=[],
            campaigns=[],
        )
        result = get_campaign_statistics("camp-1")

    # Then the stats are returned
    assert result is expected_stats


@pytest.mark.usefixtures("mock_cache_store")
def test_get_campaign_statistics_caches_result(app, mocker) -> None:
    """Verify get_campaign_statistics returns cached result on second call."""
    from vclient.testing import CompanyFactory, RollStatisticsFactory, UserFactory

    from vweb.lib.global_context import GlobalContext, get_campaign_statistics

    # Given a mocked campaigns service
    expected_stats = RollStatisticsFactory.build()
    mock_svc = mocker.MagicMock()
    mock_svc.get_statistics.return_value = expected_stats
    mocker.patch("vweb.lib.global_context.sync_campaigns_service", return_value=mock_svc)

    # When fetching stats twice
    with app.test_request_context():
        from flask import g

        g.requesting_user = UserFactory.build(id="test-user-id")
        g.global_context = GlobalContext(
            company=CompanyFactory.build(id="test-company-id"),
            users=[],
            campaigns=[],
        )
        first = get_campaign_statistics("camp-1")
        second = get_campaign_statistics("camp-1")

    # Then the API is called only once
    assert first is second
    mock_svc.get_statistics.assert_called_once()


@pytest.mark.usefixtures("_fake_vclient_data")
def test_fetch_global_data_returns_books_by_campaign(app, fake_vclient) -> None:
    """Verify _fetch_global_data populates books_by_campaign."""
    # Given books exist for the campaign — use params so this override takes priority
    books = CampaignBookFactory.batch(2)
    fake_vclient.set_response(Routes.BOOKS_LIST, items=books, params={"campaign_id": "camp-1"})

    # When fetching global data
    with app.app_context():
        result = _fetch_global_data("test-company-id", "test-user-id")

    # Then books_by_campaign contains the campaign's books
    assert len(result.books_by_campaign) == 1
    assert len(result.books_by_campaign["camp-1"]) == 2


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
        "vweb.lib.hooks.load_global_context",
        side_effect=[ctx_without_user, ctx_with_user],
    )
    mocker.patch("vweb.lib.hooks.clear_global_context_cache")

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

    # Then the hook retried and the request succeeded
    assert response.status_code == 200
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
    mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx_no_user)
    mocker.patch("vweb.lib.hooks.clear_global_context_cache")

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
