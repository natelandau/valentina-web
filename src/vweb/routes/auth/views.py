"""Authentication routes for OAuth login, callback, and logout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, flash, redirect, request, session, url_for
from flask.views import MethodView
from vclient import sync_companies_service, sync_users_service
from vclient.exceptions import APIError
from vclient.models.users import UserRegisterDTO
from werkzeug.wrappers.response import Response

from vweb import catalog
from vweb.extensions import oauth
from vweb.routes.auth.services import (
    build_companies_mapping,
    lookup_user_companies,
    update_discord_profile,
    update_github_profile,
    update_google_profile,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from vclient.models import UserLookupResult

bp = Blueprint("auth", __name__)

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
    except (httpx.HTTPError, APIError):
        logger.exception("%s OAuth callback failed: API unreachable", provider)
        flash(
            f"We couldn't reach the Valentina API to complete your {provider} login. "
            "Please try again in a few minutes.",
            "error",
        )
        return redirect(url_for("index.index"))


def _handle_login_result(
    results: list[UserLookupResult],
    provider_data: dict,
    provider: str,
    profile_updater: Callable[[str, str, dict], None],
) -> Response:
    """Branch on lookup results to set session state and redirect appropriately."""
    session.pop("pending_profile_update", None)
    session.pop("pending_oauth", None)

    if not results:
        # New user with no existing accounts — store OAuth data and pick companies
        session["pending_oauth"] = {
            "provider": provider,
            "data": provider_data,
        }
        return redirect(url_for("auth.select_companies"))

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

        # Update provider profile for the single approved company
        try:
            profile_updater(r.company_id, r.user_id, provider_data)
        except (httpx.HTTPError, APIError):
            logger.exception("Failed to update %s profile after login", provider)

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
    session["pending_profile_update"] = {
        "provider": provider,
        "data": provider_data,
    }
    return redirect(url_for("auth.select_company"))


class DiscordLoginView(MethodView):
    """Initiate Discord OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to Discord's OAuth authorization page."""
        redirect_uri = url_for("auth.discord_callback", _external=True)
        return oauth.discord.authorize_redirect(redirect_uri)


class DiscordCallbackView(MethodView):
    """Handle the Discord OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        try:
            token = oauth.discord.authorize_access_token()
        except OAuthError as exc:
            logger.warning("Discord OAuth error: %s", exc)
            flash("Discord login was cancelled or denied.", "error")
            return redirect(url_for("index.index"))

        resp = oauth.discord.get("users/@me", token=token)
        discord_data = resp.json()

        result = _safe_lookup(
            provider="discord",
            provider_id=discord_data.get("id", ""),
            email=discord_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(result, discord_data, "discord", update_discord_profile)


class LogoutView(MethodView):
    """Clear the user session and redirect to the home page."""

    def post(self) -> Response:
        """Clear session data and redirect to index."""
        session.clear()
        return redirect(url_for("index.index"))


class PendingApprovalView(MethodView):
    """Render the pending approval page for unapproved users."""

    def get(self) -> str:
        """Render the pending approval template."""
        return catalog.render(
            "auth.PendingApproval",
            companies=session.get("companies", {}),
        )


class GitHubLoginView(MethodView):
    """Initiate GitHub OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to GitHub's OAuth authorization page."""
        redirect_uri = url_for("auth.github_callback", _external=True)
        return oauth.github.authorize_redirect(redirect_uri)


class GitHubCallbackView(MethodView):
    """Handle the GitHub OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        try:
            token = oauth.github.authorize_access_token()
        except OAuthError as exc:
            logger.warning("GitHub OAuth error: %s", exc)
            flash("GitHub login was cancelled or denied.", "error")
            return redirect(url_for("index.index"))

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

        return _handle_login_result(result, github_data, "github", update_github_profile)


class GoogleLoginView(MethodView):
    """Initiate Google OAuth authorization flow."""

    def get(self) -> Response:
        """Redirect to Google's OAuth authorization page."""
        redirect_uri = url_for("auth.google_callback", _external=True)
        return oauth.google.authorize_redirect(redirect_uri)


class GoogleCallbackView(MethodView):
    """Handle the Google OAuth callback after user authorization."""

    def get(self) -> Response:
        """Exchange authorization code for token and resolve user identity."""
        try:
            token = oauth.google.authorize_access_token()
        except OAuthError as exc:
            logger.warning("Google OAuth error: %s", exc)
            flash("Google login was cancelled or denied.", "error")
            return redirect(url_for("index.index"))

        google_data = token["userinfo"]

        result = _safe_lookup(
            provider="google",
            provider_id=google_data.get("sub", ""),
            email=google_data.get("email", ""),
        )
        if isinstance(result, Response):
            return result

        return _handle_login_result(result, google_data, "google", update_google_profile)


class SelectCompaniesView(MethodView):
    """Show available companies for new users to join."""

    def get(self) -> str:
        """Render the company selection form for new users."""
        companies = sync_companies_service().list_all()
        return catalog.render("auth.SelectCompanies", companies=companies)

    def post(self) -> Response:
        """Register the user in selected companies."""
        pending = session.get("pending_oauth")
        if not pending:
            flash("Session expired. Please log in again.", "error")
            return redirect(url_for("index.index"))

        company_ids = request.form.getlist("company_ids")
        if not company_ids:
            flash("Please select at least one company.", "warning")
            return redirect(url_for("auth.select_companies"))

        provider = pending["provider"]
        data = pending["data"]

        if provider == "discord":
            from vclient.models.users import DiscordProfileUpdate

            register_dto = UserRegisterDTO(
                username=data.get("username", ""),
                email=data.get("email", ""),
                discord_profile=DiscordProfileUpdate(
                    id=data.get("id"),
                    username=data.get("username"),
                    global_name=data.get("global_name"),
                    avatar_id=data.get("avatar"),
                    discriminator=data.get("discriminator"),
                    email=data.get("email"),
                    verified=data.get("verified"),
                ),
            )
        elif provider == "github":
            from vclient.models.users import GitHubProfile

            register_dto = UserRegisterDTO(
                username=data.get("login", ""),
                email=data.get("email", ""),
                github_profile=GitHubProfile(
                    id=str(data.get("id", "")),
                    login=data.get("login"),
                    username=data.get("name"),
                    avatar_url=data.get("avatar_url"),
                    email=data.get("email"),
                    profile_url=data.get("html_url"),
                ),
            )
        elif provider == "google":
            from vclient.models.users import GoogleProfile

            register_dto = UserRegisterDTO(
                username=data.get("name", ""),
                email=data.get("email", ""),
                google_profile=GoogleProfile(
                    id=data.get("sub", ""),
                    email=data.get("email"),
                    verified_email=data.get("email_verified"),
                    username=data.get("name"),
                    name_first=data.get("given_name"),
                    name_last=data.get("family_name"),
                    avatar_url=data.get("picture"),
                    locale=data.get("locale"),
                ),
                name_first=data.get("given_name") or None,
                name_last=data.get("family_name") or None,
            )
        else:
            flash("Unsupported authentication provider.", "error")
            return redirect(url_for("index.index"))

        all_companies = sync_companies_service().list_all()
        company_names = {c.id: c.name for c in all_companies}

        companies_mapping: dict[str, dict[str, str]] = {}
        first_company_id = None
        first_user_id = None

        for company_id in company_ids:
            try:
                user = sync_users_service(on_behalf_of="anonymous", company_id=company_id).register(
                    request=register_dto,
                )
                companies_mapping[company_id] = {
                    "user_id": user.id,
                    "company_name": company_names.get(company_id, company_id),
                    "role": user.role,
                }
                if first_company_id is None:
                    first_company_id = company_id
                    first_user_id = user.id
            except (httpx.HTTPError, APIError):
                logger.exception("Failed to register user in company %s", company_id)

        if not companies_mapping:
            session.pop("pending_oauth", None)
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("index.index"))

        session.pop("pending_oauth", None)
        session["companies"] = companies_mapping
        session["company_id"] = first_company_id
        session["user_id"] = first_user_id
        session.permanent = True

        return redirect(url_for("auth.pending_approval"))


class SelectCompanyView(MethodView):
    """Show approved companies for multi-company users to switch between."""

    def get(self) -> str:
        """Render the company picker for users with multiple approved companies."""
        companies = session.get("companies", {})
        approved = {cid: data for cid, data in companies.items() if data["role"] != "UNAPPROVED"}
        return catalog.render("auth.SelectCompany", companies=approved)

    def post(self) -> Response:
        """Switch the active company for the current session."""
        company_id = request.form.get("company_id", "")
        companies = session.get("companies", {})

        if company_id not in companies:
            flash("Invalid company selection.", "error")
            return redirect(url_for("auth.select_company"))

        data = companies[company_id]
        if data["role"] == "UNAPPROVED":
            flash("You are not approved for that company.", "error")
            return redirect(url_for("auth.select_company"))

        session["company_id"] = company_id
        session["user_id"] = data["user_id"]

        # Apply pending profile update if present
        pending = session.pop("pending_profile_update", None)
        if pending:
            provider = pending["provider"]
            provider_data = pending["data"]
            updaters = {
                "discord": update_discord_profile,
                "github": update_github_profile,
                "google": update_google_profile,
            }
            updater = updaters.get(provider)
            if updater:
                try:
                    updater(company_id, data["user_id"], provider_data)
                except (httpx.HTTPError, APIError):
                    logger.exception("Failed to update %s profile after company switch", provider)

        return redirect(url_for("index.index"))


bp.add_url_rule("/auth/discord", view_func=DiscordLoginView.as_view("discord_login"))
bp.add_url_rule("/auth/discord/callback", view_func=DiscordCallbackView.as_view("discord_callback"))
bp.add_url_rule("/auth/github", view_func=GitHubLoginView.as_view("github_login"))
bp.add_url_rule("/auth/github/callback", view_func=GitHubCallbackView.as_view("github_callback"))
bp.add_url_rule("/auth/google", view_func=GoogleLoginView.as_view("google_login"))
bp.add_url_rule("/auth/google/callback", view_func=GoogleCallbackView.as_view("google_callback"))
bp.add_url_rule("/auth/logout", view_func=LogoutView.as_view("logout"), methods=["POST"])
bp.add_url_rule("/pending-approval", view_func=PendingApprovalView.as_view("pending_approval"))
bp.add_url_rule(
    "/select-companies",
    view_func=SelectCompaniesView.as_view("select_companies"),
    methods=["GET", "POST"],
)
bp.add_url_rule(
    "/select-company",
    view_func=SelectCompanyView.as_view("select_company"),
    methods=["GET", "POST"],
)
