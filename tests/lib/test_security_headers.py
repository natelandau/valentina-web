"""Tests for security headers via Flask-Talisman."""


class TestSecurityHeaders:
    """Validate security headers are set on responses."""

    def test_x_content_type_options_is_set(self, client) -> None:
        """Verify X-Content-Type-Options nosniff header is present."""
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_is_set(self, client) -> None:
        """Verify X-Frame-Options header is present."""
        assert client.get("/").headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_csp_allows_cdn_scripts(self, client) -> None:
        """Verify CSP script-src includes required CDN origins."""
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "unpkg.com" in csp
        assert "kit.fontawesome.com" in csp
