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
