"""Unit tests for the validate_constants CLI's settings resolution and exit codes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts import validate_constants
from vweb.api_client.exceptions import APIConnectionError

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


@pytest.fixture
def mock_main(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    """Isolate the CLI from real settings and the live API."""
    monkeypatch.chdir(tmp_path)
    for name in ("VWEB_API__BASE_URL", "VWEB_API__API_KEY"):
        monkeypatch.delenv(name, raising=False)
    # cli() resets loguru sinks; keep the rest of the suite's sinks intact
    mocker.patch.object(validate_constants.logger, "remove")
    mocker.patch.object(validate_constants.logger, "add")
    return mocker.patch.object(validate_constants, "main", return_value=0)


def _run(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr("sys.argv", ["validate_constants.py", *args])
    return validate_constants.cli()


@pytest.mark.parametrize(
    ("env_url", "args", "expected_call"),
    [
        pytest.param(
            None,
            ("--company-id", "c1", "--api-url", "http://api", "--api-key", "k"),
            ("http://api", "k", "c1"),
            id="flags-only",
        ),
        pytest.param(
            "http://env-api",
            ("--company-id", "c1", "--api-key", "k"),
            ("http://env-api", "k", "c1"),
            id="env-and-flag-combine",
        ),
    ],
)
def test_connection_from_flags_and_env(
    mock_main: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    env_url: str | None,
    args: tuple[str, ...],
    expected_call: tuple[str, str, str],
) -> None:
    """Verify flags and the environment together supply the connection settings."""
    if env_url:
        monkeypatch.setenv("VWEB_API__BASE_URL", env_url)

    assert _run(monkeypatch, *args) == 0
    mock_main.assert_called_once_with(*expected_call)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("--api-url", "http://api", "--api-key", "k"), id="no-company-id"),
        pytest.param(("--company-id", "c1", "--api-url", "http://api"), id="no-api-key"),
    ],
)
def test_missing_setting_exits_2_without_running(
    mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
) -> None:
    """Verify the CLI refuses to run without a company ID, API URL, or API key."""
    assert _run(monkeypatch, *args) == 2
    mock_main.assert_not_called()


def test_api_error_exits_2(
    mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify a transport error is reported as exit code 2 without a traceback."""
    mock_main.side_effect = APIConnectionError("Could not reach the API: refused")

    assert _run(monkeypatch, "--company-id", "c1", "--api-url", "http://api", "--api-key", "k") == 2
    assert "APIConnectionError: Could not reach the API: refused" in capsys.readouterr().err
