"""Shared test fixtures."""

from __future__ import annotations

import re
import socket
import subprocess
import tempfile
from typing import IO, TYPE_CHECKING, Any

import pytest
import werkzeug.test

from tests.helpers import (
    build_global_context,
    build_mock_options_service,
    build_mock_system_service,
    make_cache_store_mock,
)
from vweb.api_client.models.diceroll import DiceRollResultSchema
from vweb.api_client.testing import (
    AssetFactory,
    CampaignBookFactory,
    CampaignChapterFactory,
    CampaignFactory,
    CharacterFactory,
    FakeVClient,
)
from vweb.config import APISettings, RedisSettings, Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from unittest.mock import MagicMock

    from flask import Flask
    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture
    from werkzeug.test import TestResponse

    from vweb.api_client.models import Asset, Campaign, CampaignBook, CampaignChapter, Character
    from vweb.lib.cache.global_context import GlobalContext


@pytest.fixture
def test_settings() -> Settings:
    """Build test settings without requiring environment variables."""
    return Settings(
        _env_file=None,
        app_name="Test App",
        env="development",
        secret_key="test-secret-key",
        host="127.0.0.1",
        port=8089,
        redis=RedisSettings(url=""),
        api=APISettings(
            base_url="http://localhost:8080",
            api_key="test-api-key",
        ),
    )


@pytest.fixture
def app(test_settings) -> Flask:
    """Create a test application instance."""
    import vweb.config
    from vweb.app import create_app

    # Ensure get_settings() returns test_settings everywhere
    vweb.config._settings = test_settings

    app = create_app(settings_override=test_settings)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app) -> FlaskClient:
    """Create a test client with a pre-seeded multi-company session."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-id"
        sess["company_id"] = "test-company-id"
        sess["companies"] = {
            "test-company-id": {
                "user_id": "test-user-id",
                "company_name": "Test Company",
                "role": "PLAYER",
            },
        }
    return client


@pytest.fixture
def mock_global_context() -> GlobalContext:
    """Build the signed-in player's GlobalContext that every request sees by default."""
    return build_global_context(user_role="PLAYER")


@pytest.fixture
def mock_campaign() -> Campaign:
    """Build a factory campaign."""
    return CampaignFactory.build(id="camp-1", name="Test Campaign")


@pytest.fixture
def mock_book() -> CampaignBook:
    """Build a factory book."""
    return CampaignBookFactory.build(
        id="book-1",
        campaign_id="camp-1",
        name="The Gathering Storm",
        number=1,
        description="A tale of beginnings.",
    )


@pytest.fixture
def mock_chapters() -> list[CampaignChapter]:
    """Build factory chapters."""
    return [
        CampaignChapterFactory.build(id="ch-1", book_id="book-1", number=1, name="Chapter One"),
        CampaignChapterFactory.build(id="ch-2", book_id="book-1", number=2, name="Chapter Two"),
        CampaignChapterFactory.build(id="ch-3", book_id="book-1", number=3, name="Chapter Three"),
    ]


@pytest.fixture
def mock_character() -> Character:
    """Build a factory character with profile fields owned by the test session user."""
    return CharacterFactory.build(
        id="char-123",
        name="Test Character",
        name_full="Test Character",
        name_first="Test",
        name_last="Character",
        name_nick="Testy",
        biography="A test biography",
        nature="Brave",
        demeanor="Calm",
        character_class="VAMPIRE",
        campaign_id="camp-1",
        user_player_id="test-user-id",
        concept_id=None,
        specialties=[],
        starting_points=0,
    )


@pytest.fixture
def mock_asset() -> Asset:
    """Build an image asset."""
    return AssetFactory.build(
        id="asset-1",
        asset_type="image",
        public_url="https://cdn.example.com/img.jpg",
        original_filename="img.jpg",
    )


@pytest.fixture
def mock_cache_store(mocker: MockerFixture) -> dict:
    """Provide a dict-backed mock of the shared cache used by the cache domains."""
    return make_cache_store_mock(mocker, "vweb.lib.cache.base.cache")


@pytest.fixture
def fake_vclient(app):
    """Provide a FakeVClient that intercepts all vclient HTTP calls.

    Depends on `app` so the fake client registers as the default AFTER create_app()
    creates its own VClient, ensuring *_service() calls use the fake.
    """
    with FakeVClient() as client:
        yield client


_GIT_LOCAL_ENV_VARS = subprocess.run(
    ["git", "rev-parse", "--local-env-vars"],  # noqa: S607
    capture_output=True,
    text=True,
    check=True,
).stdout.split()


@pytest.fixture(autouse=True)
def _isolate_from_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git commands in tests from acting on this repository.

    Git hooks export GIT_DIR, so under the pre-push hook a test's `git init <tmp>` would
    reinitialize this repository instead, and from a worktree mark it bare.
    """
    for var in _GIT_LOCAL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a network connection instead of using fake_vclient or respx."""

    def _guard(real: Callable[..., Any]) -> Callable[..., Any]:
        def _refuse(sock: socket.socket, address: str | tuple[Any, ...]) -> Any:
            if sock.family == socket.AF_UNIX:
                return real(sock, address)
            sock.close()
            msg = f"Test tried to open a network connection to {address!r}"
            raise RuntimeError(msg)

        return _refuse

    monkeypatch.setattr(socket.socket, "connect", _guard(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guard(socket.socket.connect_ex))


@pytest.fixture(autouse=True)
def _close_test_client_upload_spools(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close the temp files Werkzeug's test client spools large multipart bodies into.

    Werkzeug never closes them, so the leak surfaces as a ResourceWarning in a later test.
    """
    opened: list[IO[bytes]] = []

    def _tracked(*args: Any, **kwargs: Any) -> IO[bytes]:
        spool = tempfile.TemporaryFile(*args, **kwargs)  # noqa: SIM115
        opened.append(spool)
        return spool

    monkeypatch.setattr(werkzeug.test, "TemporaryFile", _tracked)
    yield
    for spool in opened:
        spool.close()


@pytest.fixture
def mock_context_load(mocker: MockerFixture, mock_global_context: GlobalContext) -> MagicMock:
    """Patch the global context load every request runs, serving `mock_global_context`.

    Set `side_effect` on the returned mock to make the load fail.
    """
    return mocker.patch("vweb.lib.cache.global_context.load", return_value=mock_global_context)


@pytest.fixture
def use_context(mock_context_load: MagicMock) -> Callable[..., GlobalContext]:
    """Return a function that serves a GlobalContext to every following request.

    Call it with a built context, or with `build_global_context` keyword arguments
    (`user_role` is required), and use the context it returns.
    """

    def _use(context: GlobalContext | None = None, /, **kwargs: Any) -> GlobalContext:
        if context is None:
            context = build_global_context(**kwargs)
        mock_context_load.return_value = context
        return context

    return _use


@pytest.fixture(autouse=True)
def _mock_api(mocker, mock_context_load) -> None:
    """Prevent before_request hooks and route handlers from calling the real API."""
    mocker.patch("vweb.lib.cache.global_context.clear")

    mock_dict_api = mocker.patch("vweb.lib.cache.dictionary.api_services")
    mock_dict_api.dictionary.return_value.list_all.return_value = []

    # Pages now fetch books/chapters lazily via campaign_content_cache; default to
    # empty lists so full-page renders don't reach for the real API.
    mock_content_api = mocker.patch("vweb.lib.cache.campaign_content.api_services")
    mock_content_api.books.return_value.list_all.return_value = []
    mock_content_api.chapters.return_value.list_all.return_value = []

    # The footer renders system health for approved users, so every page render
    # would otherwise hit the live health endpoint.
    mocker.patch(
        "vweb.lib.cache.system_status.system_service",
        return_value=build_mock_system_service(),
    )

    mock_options_api = mocker.patch("vweb.lib.cache.options.api_services")
    mock_options_api.options.return_value = build_mock_options_service()


def get_csrf(client) -> str:
    """Extract a valid CSRF token from a page that renders PageLayout.

    Uses /pending-approval since it renders PageLayout without hitting any
    campaign or character API mocks that individual tests may override.
    """
    response = client.get("/pending-approval")
    body = response.get_data(as_text=True)
    match = re.search(r'X-CSRFToken":\s*"([^"]+)"', body)
    return match.group(1) if match else ""


def htmx_post(
    client: FlaskClient,
    url: str,
    data: dict[str, Any] | None = None,
    *,
    htmx: bool = True,
    **kwargs: Any,
) -> TestResponse:
    """POST with a valid CSRF token, as an HTMX request unless `htmx` is False.

    Args:
        client: The Flask test client.
        url: The URL to post to.
        data: Form fields to send.
        htmx: Send the HX-Request header. Pass False for a plain form submission.
        **kwargs: Passed to `client.post`, e.g. `content_type`.

    Returns:
        TestResponse: The response.
    """
    headers = {"X-CSRFToken": get_csrf(client)}
    if htmx:
        headers["HX-Request"] = "true"
    return client.post(url, data=data, headers=headers, **kwargs)


def htmx_delete(client: FlaskClient, url: str) -> TestResponse:
    """DELETE as an HTMX request with a valid CSRF token."""
    return client.delete(url, headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)})


def make_dice_roll_result(**overrides: object) -> DiceRollResultSchema:
    """Build a DiceRollResultSchema with sensible defaults."""
    defaults: dict[str, object] = {
        "total_result": 3,
        "total_result_type": "SUCCESS",
        "total_result_humanized": "3 successes",
        "total_dice_roll": [8, 7, 9, 3, 2],
        "player_roll": [8, 7, 9, 3, 2],
        "desperation_roll": [],
        "total_dice_roll_emoji": "",
        "total_dice_roll_shortcode": "",
        "player_roll_emoji": "",
        "player_roll_shortcode": "",
        "desperation_roll_emoji": "",
        "desperation_roll_shortcode": "",
    }
    defaults.update(overrides)
    return DiceRollResultSchema(**defaults)
