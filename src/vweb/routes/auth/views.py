"""Authentication routes for OAuth login, callback, and logout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, redirect, session, url_for
from flask.views import MethodView

from vweb import catalog
from vweb.extensions import oauth
from vweb.routes.auth.services import (
    resolve_or_create_discord_user,
    resolve_or_create_github_user,
    resolve_or_create_google_user,
)

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response

bp = Blueprint("auth", __name__)


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
        token = oauth.discord.authorize_access_token()
        resp = oauth.discord.get("users/@me", token=token)
        discord_data = resp.json()

        user = resolve_or_create_discord_user(discord_data)

        session["user_id"] = user.id
        session.permanent = True

        if user.role == "UNAPPROVED":
            return redirect(url_for("auth.pending_approval"))

        return redirect(url_for("index.index"))


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
        return catalog.render("auth.PendingApproval")


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
        token = oauth.github.authorize_access_token()
        resp = oauth.github.get("user", token=token)
        github_data = resp.json()

        # GitHub may return email as null; fetch from /user/emails as fallback
        if not github_data.get("email"):
            emails_resp = oauth.github.get("user/emails", token=token)
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    github_data["email"] = entry["email"]
                    break

        user = resolve_or_create_github_user(github_data)

        session["user_id"] = user.id
        session.permanent = True

        if user.role == "UNAPPROVED":
            return redirect(url_for("auth.pending_approval"))

        return redirect(url_for("index.index"))


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
        token = oauth.google.authorize_access_token()
        google_data = token["userinfo"]

        user = resolve_or_create_google_user(google_data)

        session["user_id"] = user.id
        session.permanent = True

        if user.role == "UNAPPROVED":
            return redirect(url_for("auth.pending_approval"))

        return redirect(url_for("index.index"))


bp.add_url_rule("/auth/discord", view_func=DiscordLoginView.as_view("discord_login"))
bp.add_url_rule("/auth/discord/callback", view_func=DiscordCallbackView.as_view("discord_callback"))
bp.add_url_rule("/auth/github", view_func=GitHubLoginView.as_view("github_login"))
bp.add_url_rule("/auth/github/callback", view_func=GitHubCallbackView.as_view("github_callback"))
bp.add_url_rule("/auth/google", view_func=GoogleLoginView.as_view("google_login"))
bp.add_url_rule("/auth/google/callback", view_func=GoogleCallbackView.as_view("google_callback"))
bp.add_url_rule("/auth/logout", view_func=LogoutView.as_view("logout"))
bp.add_url_rule("/pending-approval", view_func=PendingApprovalView.as_view("pending_approval"))
