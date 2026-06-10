"""Authentication routes for OAuth login, callback, and logout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Blueprint, flash, redirect, request, session, url_for
from flask.views import MethodView
from vclient import sync_companies_service
from vclient.exceptions import ServerError, UnprocessableEntityError

from vweb.extensions import csrf
from vweb.lib.catalog import catalog
from vweb.lib.jinja import approved_companies
from vweb.routes.auth.services import identify_in_companies
from vweb.routes.auth.views_identity import LinkIdentityView, UnlinkIdentityView
from vweb.routes.auth.views_oauth import (
    AppleCallbackView,
    AppleLoginView,
    DiscordCallbackView,
    DiscordLoginView,
    GitHubCallbackView,
    GitHubLoginView,
    GoogleCallbackView,
    GoogleLoginView,
    flash_identify_error,
)

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response

bp = Blueprint("auth", __name__)


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
            flash_identify_error(exc, provider)
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
        return catalog.render("auth.SelectCompany", companies=approved_companies())

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
        # The remembered campaign belongs to the previous company; drop it so
        # the index entry rules re-evaluate against the new company's campaigns.
        session.pop("last_campaign_id", None)
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
bp.add_url_rule("/auth/apple", view_func=AppleLoginView.as_view("apple_login"))
# Apple POSTs the callback cross-site with no CSRF token, so exempt this one view.
# The OAuth state parameter (validated by Authlib) is what protects the exchange.
_apple_callback_view = AppleCallbackView.as_view("apple_callback")
csrf.exempt(_apple_callback_view)
bp.add_url_rule("/auth/apple/callback", view_func=_apple_callback_view, methods=["POST"])
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
