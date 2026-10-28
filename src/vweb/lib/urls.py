"""URL checks shared by validation and rendering."""

from __future__ import annotations

from urllib.parse import urlparse


def is_http_url(url: str | None) -> bool:
    """Return True when ``url`` is an absolute http(s) URL with no whitespace.

    Use before rendering any externally stored link as an ``href``: data written by
    other API clients never passed this app's form validation, so a ``javascript:`` or
    ``data:`` link must be rejected at render time too.
    """
    if not url:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not any(char.isspace() for char in url)
    )
