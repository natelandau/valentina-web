"""Tests for auth service cross-company lookup and mapping."""

from __future__ import annotations

import logging

import pytest

from vweb.api_client.exceptions import ServerError, UnprocessableEntityError
from vweb.api_client.testing import IdentityResolutionFactory, Routes, UserLookupResultFactory
from vweb.routes.auth.services import (
    build_companies_mapping,
    identify_in_companies,
    lookup_user_companies,
)


class TestLookupUserCompanies:
    """Tests for lookup_user_companies()."""

    def test_provider_id_lookup_succeeds(self, fake_vclient) -> None:
        """Verify lookup returns results when provider ID matches."""
        # Given a lookup endpoint that finds a user by discord ID
        expected = [UserLookupResultFactory.build()]
        fake_vclient.set_response(
            Routes.USERS_LOOKUP, items=expected, query={"discord_id": "discord-123"}
        )

        # When looking up by discord provider
        results = lookup_user_companies(
            provider="discord",
            provider_id="discord-123",
            email="test@example.com",
        )

        # Then the provider ID results are returned without email fallback
        assert results == expected
        fake_vclient.assert_called(
            Routes.USERS_LOOKUP, query={"discord_id": "discord-123"}, times=1
        )
        fake_vclient.assert_not_called(Routes.USERS_LOOKUP, query={"email": "test@example.com"})

    def test_email_fallback_when_provider_returns_empty(self, fake_vclient) -> None:
        """Verify lookup falls back to email when provider ID returns no results."""
        # Given a lookup endpoint where provider ID returns empty but email matches
        email_results = [UserLookupResultFactory.build(user_id="user-via-email")]
        fake_vclient.set_response(Routes.USERS_LOOKUP, items=[], query={"github_id": "gh-999"})
        fake_vclient.set_response(
            Routes.USERS_LOOKUP, items=email_results, query={"email": "found@example.com"}
        )

        # When looking up by github provider
        results = lookup_user_companies(
            provider="github",
            provider_id="gh-999",
            email="found@example.com",
        )

        # Then email fallback results are returned
        assert results == email_results
        fake_vclient.assert_called(Routes.USERS_LOOKUP, query={"github_id": "gh-999"}, times=1)
        fake_vclient.assert_called(
            Routes.USERS_LOOKUP, query={"email": "found@example.com"}, times=1
        )

    def test_empty_results_when_no_match(self, fake_vclient) -> None:
        """Verify lookup returns empty list when neither provider ID nor email matches."""
        # Given a lookup endpoint that finds nothing
        fake_vclient.set_response(Routes.USERS_LOOKUP, items=[])

        # When looking up by google provider
        results = lookup_user_companies(
            provider="google",
            provider_id="google-nope",
            email="nobody@example.com",
        )

        # Then an empty list is returned
        assert results == []

    def test_no_email_fallback_when_email_empty(self, fake_vclient) -> None:
        """Verify lookup skips email fallback when email is empty string."""
        # Given a lookup endpoint where provider ID returns empty
        fake_vclient.set_response(Routes.USERS_LOOKUP, items=[])

        # When looking up with empty email
        results = lookup_user_companies(
            provider="discord",
            provider_id="disc-1",
            email="",
        )

        # Then no email fallback is attempted
        assert results == []
        (request,) = fake_vclient.requests_for(Routes.USERS_LOOKUP)
        assert request.query == {"discord_id": "disc-1"}


class TestBuildCompaniesMapping:
    """Tests for build_companies_mapping()."""

    def test_produces_correct_dict(self) -> None:
        """Verify mapping builds correct structure from lookup results."""
        # Given two lookup results
        results = [
            UserLookupResultFactory.build(
                company_id="c1",
                company_name="Alpha Corp",
                user_id="u1",
                role="ADMIN",
            ),
            UserLookupResultFactory.build(
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


_TEST_TOKEN = "test-oauth-access-token"


class TestIdentifyInCompanies:
    """Tests for identify_in_companies."""

    def test_identify_in_companies_resolves_each_company(self, fake_vclient) -> None:
        """Verify identify is called once per company and resolutions are keyed by company ID."""
        # Given an identify endpoint that resolves in each company
        resolutions = {cid: IdentityResolutionFactory.build() for cid in ("c1", "c2")}
        for cid, resolution in resolutions.items():
            fake_vclient.set_response(
                Routes.IDENTITY_IDENTIFY, model=resolution, params={"company_id": cid}
            )

        # When identifying in two companies
        result = identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)

        # Then each company received the credential once and both resolutions returned
        for cid in ("c1", "c2"):
            fake_vclient.assert_called(
                Routes.IDENTITY_IDENTIFY,
                params={"company_id": cid},
                json={"provider": "discord", "token": _TEST_TOKEN},
                times=1,
            )
        assert result == resolutions

    def test_identify_in_companies_skips_company_level_failure(self, fake_vclient, caplog) -> None:
        """Verify a company-level API failure is logged and skipped, not raised."""
        # Given the first company fails with a non-token error and the second succeeds
        resolution = IdentityResolutionFactory.build()
        fake_vclient.set_error(
            Routes.IDENTITY_IDENTIFY, status_code=404, params={"company_id": "c1"}
        )
        fake_vclient.set_response(
            Routes.IDENTITY_IDENTIFY, model=resolution, params={"company_id": "c2"}
        )

        # When identifying in two companies
        with caplog.at_level(logging.ERROR, logger="vweb.routes.auth.services"):
            result = identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)

        # Then only the successful company is in the result and the failure is logged
        assert result == {"c2": resolution}
        assert any(r.levelno == logging.ERROR and "c1" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize(
        ("exception_class", "status_code", "code"),
        [
            (UnprocessableEntityError, 422, "TOKEN_VERIFICATION_FAILED"),
            (ServerError, 503, "PROVIDER_UNAVAILABLE"),
        ],
    )
    def test_identify_in_companies_raises_token_level_failure(
        self, fake_vclient, exception_class, status_code, code
    ) -> None:
        """Verify token- and provider-level failures propagate so callers can branch on the code."""
        # Given the identify endpoint rejects the credential outright
        fake_vclient.set_error(Routes.IDENTITY_IDENTIFY, status_code=status_code, code=code)

        # When identifying, then the error is raised to the caller with its code
        with pytest.raises(exception_class) as exc_info:
            identify_in_companies(["c1", "c2"], provider="discord", token=_TEST_TOKEN)
        assert exc_info.value.code == code
        fake_vclient.assert_not_called(Routes.IDENTITY_IDENTIFY, params={"company_id": "c2"})
