"""Tests for error handlers."""

from __future__ import annotations

import pytest
from flask import abort


@pytest.mark.parametrize("code", [400, 403, 404, 410, 500])
def test_http_error_keeps_status_without_exception_log(app, client, mocker, code: int) -> None:
    """Verify an HTTP error renders the error page with its own status and is not logged."""

    @app.route("/test-abort")
    def aborting() -> str:
        abort(code)

    log_spy = mocker.patch("vweb.lib.errors.logger.exception")

    response = client.get("/test-abort")

    assert response.status_code == code
    assert response.mimetype == "text/html"
    log_spy.assert_not_called()


def test_method_not_allowed_keeps_405(app, client, mocker) -> None:
    """Verify bot probes with the wrong method get a 405, not a logged 500."""

    @app.route("/test-405-get-only")
    def get_only() -> str:
        return "ok"

    log_spy = mocker.patch("vweb.lib.errors.logger.exception")

    response = client.post("/test-405-get-only")

    assert response.status_code == 405
    log_spy.assert_not_called()


def test_unhandled_exception_returns_500_and_logs(app, client, mocker) -> None:
    """Verify an unexpected exception renders a 500 page and is logged."""

    @app.route("/test-500")
    def trigger_error() -> str:
        msg = "test error"
        raise RuntimeError(msg)

    log_spy = mocker.patch("vweb.lib.errors.logger.exception")

    response = client.get("/test-500")

    assert response.status_code == 500
    assert "test error" not in response.get_data(as_text=True)
    log_spy.assert_called_once()
