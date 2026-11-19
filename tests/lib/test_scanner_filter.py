"""Tests for the request-path before_request hooks: scanner blocking and trailing slashes."""

import pytest


@pytest.mark.parametrize(
    "path",
    [
        # Dotfiles at any depth
        "/.env",
        "/.git/config",
        "/.npmrc",
        "/.htaccess",
        "/.DS_Store",
        "/app/.env",
        "/app/.git/config",
        "/.cursor/mcp.json",
        "/app/.env.production",
        # Known scanner prefixes
        "/wp-admin",
        "/wp-login.php",
        "/wordpress/wp-admin",
        "/phpmyadmin/index",
        "/pma",
        "/adminer",
        "/cgi-bin/test",
        "/xmlrpc",
        "/sitemap.xml",
        # Non-Python script extensions
        "/login.php",
        "/admin.asp",
        "/page.aspx",
        "/index.jsp",
        "/test.cgi",
        # Patterns anywhere in the path
        "/backup.env.old",
        "/phpinfo",
        # Matching ignores case
        "/WP-ADMIN",
        "/.Env",
        "/login.PHP",
        # Public files are exempt only at their exact path
        "/ROBOTS.TXT",
    ],
)
def test_scanner_paths_return_404(client, path) -> None:
    """Verify requests for paths vulnerability scanners probe are blocked with 404."""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/auth/discord",
        "/auth/github",
        "/auth/google",
        "/pending-approval",
        "/robots.txt",
    ],
)
def test_legitimate_paths_are_not_blocked(client, path) -> None:
    """Verify normal application paths pass through the scanner filter."""
    # May be 200 or 302 depending on auth state, just not blocked
    response = client.get(path)
    response.close()
    assert response.status_code != 404


def test_trailing_slash_redirects_to_canonical_url(client) -> None:
    """Verify a trailing-slash URL permanently redirects to the URL without it."""
    response = client.get("/pending-approval/")

    assert response.status_code == 301
    assert response.headers["Location"] == "/pending-approval"
