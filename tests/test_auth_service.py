"""Tests for auth service cross-company lookup and mapping."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from vclient.exceptions import NotFoundError, ServerError, UnprocessableEntityError
from vclient.models import UserLookupResult

from vweb.routes.auth.services import (
    build_companies_mapping,
    identify_in_companies,
    lookup_user_companies,
)


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


_TEST_TOKEN = "test-oauth-access-token"  # noqa: S105 - not a password; placeholder OAuth token for tests


class TestIdentifyInCompanies:
    """Tests for identify_in_companies."""

    def test_identify_in_companies_resolves_each_company(self, mocker) -> None:
        """Verify identify is called once per company and resolutions are keyed by company ID."""
        # Given an identity service that resolves successfully
        resolution = MagicMock()
        mock_svc = MagicMock()
        mock_svc.identify.return_value = resolution
        mock_factory = mocker.patch(
            "vweb.routes.auth.services.sync_identity_service",
            autospec=True,
            return_value=mock_svc,
        )

        # When identifying in two companies
        result = identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)

        # Then the service was scoped to each company and both resolutions returned
        assert mock_factory.call_args_list == [
            mocker.call(company_id="c1"),
            mocker.call(company_id="c2"),
        ]
        assert result == {"c1": resolution, "c2": resolution}

    def test_identify_in_companies_skips_company_level_failure(self, mocker, caplog) -> None:
        """Verify a company-level API failure is logged and skipped, not raised."""
        # Given the first company fails with a non-token error and the second succeeds
        resolution = MagicMock()
        mock_svc = MagicMock()
        mock_svc.identify.side_effect = [NotFoundError("nope", 404), resolution]
        mocker.patch(
            "vweb.routes.auth.services.sync_identity_service",
            autospec=True,
            return_value=mock_svc,
        )

        # When identifying in two companies
        with caplog.at_level(logging.ERROR, logger="vweb.routes.auth.services"):
            result = identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)

        # Then only the successful company is in the result and the failure is logged
        assert result == {"c2": resolution}
        assert "identify failed for company c1" in caplog.text

    @pytest.mark.parametrize(
        ("exception_class", "exception_args"),
        [
            (UnprocessableEntityError, ("bad token", 422, {"code": "TOKEN_VERIFICATION_FAILED"})),
            (ServerError, ("provider unreachable", 503, {"code": "PROVIDER_UNAVAILABLE"})),
        ],
    )
    def test_identify_in_companies_raises_token_level_failure(
        self, mocker, exception_class, exception_args
    ) -> None:
        """Verify token- and provider-level failures propagate so callers can branch on the code."""
        # Given the identity service rejects the credential outright
        mock_svc = MagicMock()
        mock_svc.identify.side_effect = exception_class(*exception_args)
        mocker.patch(
            "vweb.routes.auth.services.sync_identity_service",
            autospec=True,
            return_value=mock_svc,
        )

        # When identifying, then the error is raised to the caller
        with pytest.raises(exception_class):
            identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)
