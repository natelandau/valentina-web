"""Authentication routes for OAuth login, callback, and logout."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import httpx
from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, abort, flash, redirect, request, session, url_for
from flask.views import MethodView
from vclient import sync_companies_service, sync_users_service
from vclient.exceptions import (
    APIError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServerError,
    UnprocessableEntityError,
)
from werkzeug.wrappers.response import Response

from vweb import catalog
from vweb.extensions import oauth
from vweb.lib import cache
from vweb.lib.jinja import htmx_response_with_flash, hx_redirect
from vweb.routes.auth.services import (
    build_companies_mapping,
    identify_in_companies,
    lookup_user_companies,
)

if TYPE_CHECKING:
    from vclient.constants import IdentityProvider
    from vclient.models import User, UserLookupResult

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


def _flash_identify_error(exc: APIError, provider: str) -> None:
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


_LINKABLE_PROVIDERS = ("discord", "github", "google")


def _link_redirect_target() -> str:
    """Resolve where a link-mode flow should land: the user's profile when known."""
    user_id = session.get("user_id")
    return url_for("profile.profile", user_id=user_id) if user_id else url_for("index.index")


def _handle_link(provider: IdentityProvider, credential: str) -> Response:
    """Attach a verified provider identity to the logged-in user's account."""
    user_id = session.get("user_id")
    company_id = session.get("company_id")
    if not user_id or not company_id:
        flash("Please log in before connecting accounts.", "error")
        return redirect(url_for("index.index"))

    profile_url = url_for("profile.profile", user_id=user_id)
    try:
        sync_users_service(on_behalf_of=user_id, company_id=company_id).link_identity(
            user_id,
            provider=provider,
            token=credential,
        )
    except ConflictError:
        flash(
            f"That {provider.title()} account is already linked to a different user.",
            "error",
        )
        return redirect(profile_url)
    except (UnprocessableEntityError, ServerError) as exc:
        if isinstance(exc, ServerError) and exc.code == "PROVIDER_UNAVAILABLE":
            flash(
                f"{provider.title()} is currently unreachable. Please try again in a few minutes.",
                "error",
            )
        else:
            flash(f"Could not verify your {provider.title()} login. Please try again.", "error")
        return redirect(profile_url)
    except (httpx.HTTPError, APIError):
        logger.exception("Failed to link %s identity", provider)
        flash(
            f"Connecting your {provider.title()} account failed. Please try again later.",
            "error",
        )
        return redirect(profile_url)

    # Refresh g.requesting_user so the new connection shows up immediately
    cache.global_context.clear(company_id, user_id)
    flash(f"Your {provider.title()} account is now connected.", "success")
    return redirect(profile_url)


class LinkIdentityView(MethodView):
    """Start an OAuth flow that connects an additional provider to the current user."""

    def get(self, provider: str) -> Response:
        """Flag the session as a link flow and redirect to the provider."""
        # 404 unknown providers and ones this deployment did not configure — without
        # the registration check, `oauth.<provider>` below raises AttributeError (500).
        if provider not in _LINKABLE_PROVIDERS or getattr(oauth, provider, None) is None:
            abort(404)
        if not session.get("user_id") or not session.get("company_id"):
            # /auth/ paths bypass the require_auth hook, so guard here. Require an
            # active company too, since linking targets it — fail before the round-trip.
            flash("Please log in before connecting accounts.", "error")
            return redirect(url_for("index.index"))

        session["oauth_link_mode"] = True
        redirect_uri = url_for(f"auth.{provider}_callback", _external=True)
        return getattr(oauth, provider).authorize_redirect(redirect_uri)


def _connections_card(user: User) -> str:
    """Render the connections card fragment with the flash container OOB-swapped.

    Unlinking swaps the card in place over HTMX, so both the refreshed card and
    any flash toast must travel in the same response.
    """
    return htmx_response_with_flash(catalog.render("profile.components.ConnectionsCard", user=user))


def _current_connections_card(user_id: str, company_id: str) -> str:
    """Re-render the card from cached context when an unlink leaves state unchanged.

    The /auth/ paths skip the global-context hook, so error branches load the
    user themselves rather than reading g.requesting_user.
    """
    ctx = cache.global_context.load(company_id, user_id)
    user = next((u for u in ctx.users if u.id == user_id), None)
    if user is None:
        abort(404)
    return _connections_card(user)


class UnlinkIdentityView(MethodView):
    """Disconnect an OAuth provider from the current user's account."""

    def post(self, provider: str) -> str | Response:
        """Unlink a provider identity and return the refreshed connections card."""
        if provider not in _LINKABLE_PROVIDERS:
            abort(404)
        user_id = session.get("user_id")
        company_id = session.get("company_id")
        if not user_id or not company_id:
            # /auth/ paths bypass the require_auth hook, so guard here like linking does.
            flash("Please log in before managing connections.", "error")
            return hx_redirect(url_for("index.index"))

        try:
            user = sync_users_service(on_behalf_of=user_id, company_id=company_id).unlink_identity(
                user_id, provider=cast("IdentityProvider", provider)
            )
        except ConflictError:
            # LAST_IDENTITY — the API refuses to remove the only sign-in method.
            flash(
                f"You can't disconnect {provider.title()} because it's your only "
                "sign-in method. Connect another provider first.",
                "error",
            )
            return _current_connections_card(user_id, company_id)
        except NotFoundError:
            flash(f"{provider.title()} is not connected to your account.", "warning")
            return _current_connections_card(user_id, company_id)
        except AuthorizationError:
            flash("You are not allowed to change these connections.", "error")
            return _current_connections_card(user_id, company_id)
        except (httpx.HTTPError, APIError):
            logger.exception("Failed to unlink %s identity", provider)
            flash(
                f"Disconnecting your {provider.title()} account failed. Please try again later.",
                "error",
            )
            return _current_connections_card(user_id, company_id)

        # Invalidate the cached context so the removed connection is gone on next load
        cache.global_context.clear(company_id, user_id)
        flash(f"Your {provider.title()} account has been disconnected.", "success")
        return _connections_card(user)


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
        _flash_identify_error(exc, provider)
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
            return redirect(_link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return _handle_link("discord", token["access_token"])

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
            return redirect(_link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return _handle_link("github", token["access_token"])

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
            return redirect(_link_redirect_target() if link_mode else url_for("index.index"))

        if link_mode:
            return _handle_link("google", token["id_token"])

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


class SelectCompaniesView(MethodView):
    """Show available companies for new users to join."""

    def get(self) -> str:
        """Render the company selection form for new users."""
        companies = sync_companies_service().list_all()
        return catalog.render("auth.SelectCompanies", companies=companies)

    def post(self) -> Response:
        """Register the user in selected companies via verified identity resolution."""
        pending = session.get("pending_oauth")
        # Require the verified credential. A pre-upgrade session may carry the old
        # {provider, data} shape with no token; treat that as an expired session
        # rather than letting pending["token"] raise a KeyError.
        if not pending or "token" not in pending:
            session.pop("pending_oauth", None)
            flash("Session expired. Please log in again.", "error")
            return redirect(url_for("index.index"))

        company_ids = request.form.getlist("company_ids")
        if not company_ids:
            flash("Please select at least one company.", "warning")
            return redirect(url_for("auth.select_companies"))

        provider = pending["provider"]
        try:
            resolutions = identify_in_companies(
                company_ids,
                provider=provider,
                token=pending["token"],
                username=pending.get("username"),
                email=pending.get("email"),
            )
        except (UnprocessableEntityError, ServerError) as exc:
            session.pop("pending_oauth", None)
            _flash_identify_error(exc, provider)
            return redirect(url_for("index.index"))

        if not resolutions:
            session.pop("pending_oauth", None)
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("index.index"))

        company_names = {c.id: c.name for c in sync_companies_service().list_all()}
        companies_mapping = {
            company_id: {
                "user_id": resolution.user.id,
                "company_name": company_names.get(company_id, company_id),
                "role": resolution.user.role,
            }
            for company_id, resolution in resolutions.items()
        }

        # All freshly registered users land on /pending-approval regardless of
        # which company is active, so the first successfully resolved company
        # (submission order is preserved through identify_in_companies) is fine.
        first_company_id = next(iter(companies_mapping))
        session.pop("pending_oauth", None)
        session["companies"] = companies_mapping
        session["company_id"] = first_company_id
        session["user_id"] = companies_mapping[first_company_id]["user_id"]
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
        return redirect(url_for("index.index"))


bp.add_url_rule(
    "/auth/<string:provider>/link",
    view_func=LinkIdentityView.as_view("link_identity"),
)
bp.add_url_rule(
    "/auth/<string:provider>/unlink",
    view_func=UnlinkIdentityView.as_view("unlink_identity"),
    methods=["POST"],
)
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
