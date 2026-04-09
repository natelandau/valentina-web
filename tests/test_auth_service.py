"""Tests for auth service cross-company lookup and mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from vclient.models import UserLookupResult

from vweb.routes.auth.services import build_companies_mapping, lookup_user_companies


def _make_lookup_result(**kwargs) -> UserLookupResult:
    """Build a UserLookupResult with sensible defaults."""
    defaults = {
        "company_id": "comp-1",
        "company_name": "Test Company",
        "user_id": "user-1",
        "role": "PLAYER",
    }
    defaults.update(kwargs)
    return UserLookupResult(**defaults)


class TestLookupUserCompanies:
    """Tests for lookup_user_companies()."""

    @patch("vweb.routes.auth.services.sync_user_lookup_service")
    def test_provider_id_lookup_succeeds(self, mock_svc_factory) -> None:
        """Verify lookup returns results when provider ID matches."""
        # Given a lookup service that finds a user by discord ID
        expected = [_make_lookup_result()]
        mock_svc = MagicMock()
        mock_svc.by_discord_id.return_value = expected
        mock_svc_factory.return_value = mock_svc

        # When looking up by discord provider
        results = lookup_user_companies(
            provider="discord",
            provider_id="discord-123",
            email="test@example.com",
        )

        # Then the provider ID results are returned without email fallback
        assert results == expected
        mock_svc.by_discord_id.assert_called_once_with("discord-123")
        mock_svc.by_email.assert_not_called()

    @patch("vweb.routes.auth.services.sync_user_lookup_service")
    def test_email_fallback_when_provider_returns_empty(self, mock_svc_factory) -> None:
        """Verify lookup falls back to email when provider ID returns no results."""
        # Given a lookup service where provider ID returns empty but email matches
        email_results = [_make_lookup_result(user_id="user-via-email")]
        mock_svc = MagicMock()
        mock_svc.by_github_id.return_value = []
        mock_svc.by_email.return_value = email_results
        mock_svc_factory.return_value = mock_svc

        # When looking up by github provider
        results = lookup_user_companies(
            provider="github",
            provider_id="gh-999",
            email="found@example.com",
        )

        # Then email fallback results are returned
        assert results == email_results
        mock_svc.by_github_id.assert_called_once_with("gh-999")
        mock_svc.by_email.assert_called_once_with("found@example.com")

    @patch("vweb.routes.auth.services.sync_user_lookup_service")
    def test_empty_results_when_no_match(self, mock_svc_factory) -> None:
        """Verify lookup returns empty list when neither provider ID nor email matches."""
        # Given a lookup service that finds nothing
        mock_svc = MagicMock()
        mock_svc.by_google_id.return_value = []
        mock_svc.by_email.return_value = []
        mock_svc_factory.return_value = mock_svc

        # When looking up by google provider
        results = lookup_user_companies(
            provider="google",
            provider_id="google-nope",
            email="nobody@example.com",
        )

        # Then an empty list is returned
        assert results == []

    @patch("vweb.routes.auth.services.sync_user_lookup_service")
    def test_no_email_fallback_when_email_empty(self, mock_svc_factory) -> None:
        """Verify lookup skips email fallback when email is empty string."""
        # Given a lookup service where provider ID returns empty
        mock_svc = MagicMock()
        mock_svc.by_discord_id.return_value = []
        mock_svc_factory.return_value = mock_svc

        # When looking up with empty email
        results = lookup_user_companies(
            provider="discord",
            provider_id="disc-1",
            email="",
        )

        # Then no email fallback is attempted
        assert results == []
        mock_svc.by_email.assert_not_called()


class TestBuildCompaniesMapping:
    """Tests for build_companies_mapping()."""

    def test_produces_correct_dict(self) -> None:
        """Verify mapping builds correct structure from lookup results."""
        # Given two lookup results
        results = [
            _make_lookup_result(
                company_id="c1",
                company_name="Alpha Corp",
                user_id="u1",
                role="ADMIN",
            ),
            _make_lookup_result(
                company_id="c2",
                company_name="Beta Inc",
                user_id="u2",
                role="PLAYER",
            ),
        ]

        # When building the mapping
        mapping = build_companies_mapping(results)

        # Then each company_id maps to its user_id, company_name, and role
        assert mapping == {
            "c1": {"user_id": "u1", "company_name": "Alpha Corp", "role": "ADMIN"},
            "c2": {"user_id": "u2", "company_name": "Beta Inc", "role": "PLAYER"},
        }

    def test_empty_results_produce_empty_dict(self) -> None:
        """Verify empty results produce empty mapping."""
        assert build_companies_mapping([]) == {}
