"""Views for the OAuth login flows: provider authorize redirects and callbacks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx2
from authlib.integrations.base_client.errors import OAuthError
from flask import current_app, flash, redirect, request, session, url_for
from flask.views import MethodView
from vclient.exceptions import APIError, ServerError, UnprocessableEntityError
from werkzeug.wrappers.response import Response

from vweb.extensions import oauth
from vweb.routes.auth.apple_oauth import build_apple_client_secret
from vweb.routes.auth.services import (
    build_companies_mapping,
    extract_apple_display_name,
    identify_in_companies,
    lookup_user_companies,
)
from vweb.routes.auth.views_identity import handle_link, link_redirect_target

if TYPE_CHECKING:
    from vclient.constants import IdentityProvider
    from vclient.models import UserLookupResult

logger = logging.getLogger(__name__)


def _safe_lookup(
    *,
    provider: str,
    provider_id: str,
    email: str,
) -> list[UserLookupResult] | Response:
    """Wrap lookup_user_companies with transport/API error handling.

    Returns the lookup results on success, or a redirect Response on failure.
    """
    try:
        return lookup_user_companies(
            provider=provider,
            provider_id=provider_id,
            email=email,
        )
    except (httpx2.HTTPError, APIError):
        logger.exception("%s OAuth callback failed: API unreachable", provider)
        flash(
            f"We couldn't reach the Valentina API to complete your {provider} login. "
            "Please try again in a few minutes.",
            "error",
        )
        return redirect(url_for("index.index"))


def flash_identify_error(exc: APIError, provider: str) -> None:
    """Translate an identity verification failure into a user-facing flash message."""
    if isinstance(exc, UnprocessableEntityError) and exc.code == "EMAIL_REQUIRED":
        flash(
            f"Your {provider.title()} account did not provide an email address, "
            "which is required to create an account.",
            "error",
        )
    elif isinstance(exc, ServerError) and exc.code == "PROVIDER_UNAVAILABLE":
        flash(
            f"{provider.title()} is currently unreachable. Please try again in a few minutes.",
            "error",
        )
    else:
        flash(
            f"Your {provider.title()} login could not be verified. Please try again.",
            "error",
        )


def _handle_login_result(
    results: list[UserLookupResult],
    *,
    provider: IdentityProvider,
    credential: str,
    username: str | None,
    email: str | None,
) -> Response:
    """Branch on lookup results to set session state and redirect appropriately."""
    session.pop("pending_oauth", None)

    if not results:
        # New user with no existing accounts — keep the verified credential so
        # registration can run identify() after they pick companies
        session["pending_oauth"] = {
            "provider": provider,
            "token": credential,
            "username": username,
            "email": email,
        }
        return redirect(url_for("auth.select_companies"))

    # Server-verify the credential and refresh/auto-link the identity in every
    # company the user belongs to. Token-level failures abort the login;
    # per-company failures are logged inside the helper and login proceeds.
    try:
        identify_in_companies(
            [r.company_id for r in results],
            provider=provider,
            token=credential,
        )
    except (UnprocessableEntityError, ServerError) as exc:
        flash_identify_error(exc, provider)
        return redirect(url_for("index.index"))

    companies = build_companies_mapping(results)
    approved = {cid: data for cid, data in companies.items() if data["role"] != "UNAPPROVED"}

    if len(results) == 1:
        r = results[0]
        session["companies"] = companies
        session["company_id"] = r.company_id
        session["user_id"] = r.user_id
        session.permanent = True

        if r.role == "UNAPPROVED":
            return redirect(url_for("auth.pending_approval"))
        return redirect(url_for("index.index"))

    # Multiple companies
    session["companies"] = companies
    session.permanent = True

    if not approved:
        # All companies are UNAPPROVED
        first = results[0]
        session["company_id"] = first.company_id
        session["user_id"] = first.user_id
        return redirect(url_for("auth.pending_approval"))

    # Multiple companies with at least one approved — let user pick
    return redirect(url_for("auth.select_company"))


class DiscordLoginView(MethodView):
    """Initiate Discord OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to Discord's OAuth authorization page."""
        # Drop any link-mode flag left over from an abandoned "connect account" flow
        # so the same shared callback resolves this as a login, not an identity link.
        session.pop("oauth_link_mode", None)
        redirect_uri = url_for("auth.discord_callback", _external=True)
        return oauth.discord.authorize_redirect(redirect_uri)


class DiscordCallbackView(MethodView):
    """Handle the Discord OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        link_mode = session.pop("oauth_link_mode", False)
        try:
            token = oauth.discord.authorize_access_token()
        except OAuthError as exc:
            logger.warning("Discord OAuth error: %s", exc)
            flash("Discord login was cancelled or denied.", "error")
            return redirect(link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return handle_link("discord", token["access_token"])

        resp = oauth.discord.get("users/@me", token=token)
        discord_data = resp.json()

        result = _safe_lookup(
            provider="discord",
            provider_id=discord_data.get("id", ""),
            email=discord_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(
            result,
            provider="discord",
            credential=token["access_token"],
            username=discord_data.get("username"),
            email=discord_data.get("email"),
        )


class GitHubLoginView(MethodView):
    """Initiate GitHub OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to GitHub's OAuth authorization page."""
        # Drop any link-mode flag left over from an abandoned "connect account" flow
        # so the same shared callback resolves this as a login, not an identity link.
        session.pop("oauth_link_mode", None)
        redirect_uri = url_for("auth.github_callback", _external=True)
        return oauth.github.authorize_redirect(redirect_uri)


class GitHubCallbackView(MethodView):
    """Handle the GitHub OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        link_mode = session.pop("oauth_link_mode", False)
        try:
            token = oauth.github.authorize_access_token()
        except OAuthError as exc:
            logger.warning("GitHub OAuth error: %s", exc)
            flash("GitHub login was cancelled or denied.", "error")
            return redirect(link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return handle_link("github", token["access_token"])

        resp = oauth.github.get("user", token=token)
        github_data = resp.json()

        # GitHub may return email as null; fetch from /user/emails as fallback
        if not github_data.get("email"):
            emails_resp = oauth.github.get("user/emails", token=token)
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    github_data["email"] = entry["email"]
                    break

        result = _safe_lookup(
            provider="github",
            provider_id=str(github_data.get("id", "")),
            email=github_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(
            result,
            provider="github",
            credential=token["access_token"],
            username=github_data.get("login"),
            email=github_data.get("email"),
        )


class GoogleLoginView(MethodView):
    """Initiate Google OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to Google's OAuth authorization page."""
        # Drop any link-mode flag left over from an abandoned "connect account" flow
        # so the same shared callback resolves this as a login, not an identity link.
        session.pop("oauth_link_mode", None)
        redirect_uri = url_for("auth.google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)


class GoogleCallbackView(MethodView):
    """Handle the Google OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        link_mode = session.pop("oauth_link_mode", False)
        try:
            token = oauth.google.authorize_access_token()
        except OAuthError as exc:
            logger.warning("Google OAuth error: %s", exc)
            flash("Google login was cancelled or denied.", "error")
            return redirect(link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return handle_link("google", token["id_token"])

        google_data = token["userinfo"]

        result = _safe_lookup(
            provider="google",
            provider_id=google_data.get("sub", ""),
            email=google_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(
            result,
            provider="google",
            # Use the OIDC ID token so the API can verify the credential with Google
            credential=token["id_token"],
            username=google_data.get("name"),
            email=google_data.get("email"),
        )


class AppleLoginView(MethodView):
    """Initiate Sign in with Apple authorization flow."""

    def get(self) -> Response:
        """Redirect to Apple's OAuth authorization page."""
        # Drop any link-mode flag left over from an abandoned "connect account" flow
        # so the shared callback resolves this as a login, not an identity link.
        session.pop("oauth_link_mode", None)
        redirect_uri = url_for("auth.apple_callback", _external=True)
        # response_mode=form_post is configured on the provider in oauth_setup.
        return oauth.apple.authorize_redirect(redirect_uri)


class AppleCallbackView(MethodView):
    """Handle the Sign in with Apple callback, which Apple sends as a form POST."""

    def post(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        link_mode = session.pop("oauth_link_mode", False)
        # Apple's client_secret is a short-lived signed JWT, not a static string.
        # Mint a fresh one here; Authlib reads client_secret when it builds the
        # token request, so assigning it immediately before the exchange is honored.
        # This writes a process-shared object, but under threaded workers a race is
        # benign: every secret is signed by the same key for the same client and is
        # interchangeable. Adding a per-request claim (jti/nonce) would change that.
        settings = current_app.config["SETTINGS"]
        oauth.apple.client_secret = build_apple_client_secret(settings.oauth.apple)
        try:
            token = oauth.apple.authorize_access_token()
        except OAuthError as exc:
            logger.warning("Apple OAuth error: %s", exc)
            flash("Apple login was cancelled or denied.", "error")
            return redirect(link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return handle_link("apple", token["id_token"])

        apple_data = token["userinfo"]

        result = _safe_lookup(
            provider="apple",
            provider_id=apple_data.get("sub", ""),
            email=apple_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(
            result,
            provider="apple",
            # Use the OIDC ID token so the API can verify the credential with Apple
            credential=token["id_token"],
            # Apple sends the name only on first login, as JSON in the form POST
            username=extract_apple_display_name(request.form.get("user")),
            email=apple_data.get("email"),
        )
