"""Unit tests for the validate_constants CLI's settings resolution and exit codes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx2
import pytest

from scripts import validate_constants

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


def test_missing_company_id_exits_2(mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the CLI refuses to run without a company ID."""
    assert _run(monkeypatch, "--api-url", "http://api", "--api-key", "k") == 2
    mock_main.assert_not_called()


def test_flags_supply_connection(mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify flags alone are enough to run the check."""
    assert _run(monkeypatch, "--company-id", "c1", "--api-url", "http://api", "--api-key", "k") == 0
    mock_main.assert_called_once_with("http://api", "k", "c1")


def test_env_and_flag_combine(mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a flag fills in the value the environment leaves out."""
    monkeypatch.setenv("VWEB_API__BASE_URL", "http://env-api")

    assert _run(monkeypatch, "--company-id", "c1", "--api-key", "k") == 0
    mock_main.assert_called_once_with("http://env-api", "k", "c1")


def test_missing_key_exits_2(
    mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify a missing API key is reported without running the check."""
    monkeypatch.setenv("VWEB_API__BASE_URL", "http://env-api")

    assert _run(monkeypatch, "--company-id", "c1") == 2
    mock_main.assert_not_called()
    assert "API URL and key are required" in capsys.readouterr().err


def test_api_error_exits_2(
    mock_main: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify a transport error is reported as exit code 2 without a traceback."""
    mock_main.side_effect = httpx2.ConnectError("refused")

    assert _run(monkeypatch, "--company-id", "c1", "--api-url", "http://api", "--api-key", "k") == 2
    assert "ConnectError: refused" in capsys.readouterr().err
