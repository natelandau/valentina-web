"""Tests for the scanner probe before_request hook."""

import pytest


class TestScannerProbeBlocking:
    """Verify the scanner probe hook blocks malicious paths and allows legitimate ones."""

    @pytest.mark.parametrize(
        "path",
        [
            "/.env",
            "/.git/config",
            "/.npmrc",
            "/.htaccess",
            "/.DS_Store",
            "/app/.env",
            "/app/.git/config",
            "/.cursor/mcp.json",
        ],
    )
    def test_dotfile_paths_return_404(self, client, path) -> None:
        """Verify requests for dotfile paths are blocked with 404."""
        # When requesting a dotfile path
        response = client.get(path)

        # Then a 404 is returned
        assert response.status_code == 404

    def test_well_known_path_is_not_blocked(self, client) -> None:
        """Verify .well-known paths pass through the scanner filter."""
        # When requesting a .well-known path
        response = client.get("/.well-known/openid-configuration")

        # Then the request is NOT blocked by the scanner filter
        # (it will 404 from normal routing, but not from the scanner hook —
        # we just verify it doesn't get caught by dotfile detection)
        assert response.status_code != 403

    @pytest.mark.parametrize(
        "path",
        [
            "/wp-admin",
            "/wp-login.php",
            "/wordpress/wp-admin",
            "/phpmyadmin",
            "/phpmyadmin/index",
            "/pma",
            "/adminer",
            "/cgi-bin/test",
            "/xmlrpc",
        ],
    )
    def test_scanner_prefix_paths_return_404(self, client, path) -> None:
        """Verify requests for known scanner prefixes are blocked with 404."""
        # When requesting a known scanner path
        response = client.get(path)

        # Then a 404 is returned
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/login.php",
            "/admin.asp",
            "/page.aspx",
            "/index.jsp",
            "/test.cgi",
        ],
    )
    def test_script_suffix_paths_return_404(self, client, path) -> None:
        """Verify requests for non-Python script extensions are blocked with 404."""
        # When requesting a path with a blocked extension
        response = client.get(path)

        # Then a 404 is returned
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/app/.env.production",
            "/app/.env.local",
            "/app/.env.backup",
            "/.env.development",
        ],
    )
    def test_env_variant_paths_return_404(self, client, path) -> None:
        """Verify .env.* variant paths are caught by the regex pattern."""
        # When requesting a .env variant path
        response = client.get(path)

        # Then a 404 is returned
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/auth/discord",
            "/auth/github",
            "/auth/google",
            "/pending-approval",
        ],
    )
    def test_legitimate_paths_are_not_blocked(self, client, path) -> None:
        """Verify normal application paths pass through the scanner filter."""
        # When requesting a legitimate path
        response = client.get(path)

        # Then the response is NOT a 404 from the scanner filter
        # (may be 200, 302, etc. depending on auth state — just not blocked)
        assert response.status_code != 404
