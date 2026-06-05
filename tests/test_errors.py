"""Tests for error handlers."""

from __future__ import annotations


class TestErrorHandlers:
    """Validate custom error handlers return styled pages."""

    def test_404_returns_styled_page(self, client) -> None:
        """Verify 404 errors render the error page template."""
        response = client.get("/nonexistent-page-that-does-not-exist")
        assert response.status_code == 404
        body = response.get_data(as_text=True)
        assert "Page Not Found" in body

    def test_405_returns_405_without_exception_log(self, app, client, mocker) -> None:
        """Verify method-not-allowed errors keep their status code and skip exception logging."""

        # Given a GET-only route and a spy on the unhandled-exception logger
        @app.route("/test-405-get-only")
        def get_only() -> str:
            return "ok"

        log_spy = mocker.patch("vweb.lib.errors.logger.exception")

        # When POSTing to the GET-only route
        response = client.post("/test-405-get-only")

        # Then the response is a styled 405, not a logged 500
        assert response.status_code == 405
        body = response.get_data(as_text=True)
        assert "Method Not Allowed" in body
        log_spy.assert_not_called()

    def test_500_returns_styled_page(self, app, client) -> None:
        """Verify unhandled exceptions render the error page template."""

        @app.route("/test-500")
        def trigger_error() -> str:
            msg = "test error"
            raise RuntimeError(msg)

        response = client.get("/test-500")
        assert response.status_code == 500
        body = response.get_data(as_text=True)
        assert "Server Error" in body
