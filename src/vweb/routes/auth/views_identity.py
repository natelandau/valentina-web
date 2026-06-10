"""Views for linking and unlinking OAuth provider identities on an existing account."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import httpx
from flask import abort, flash, redirect, session, url_for
from flask.views import MethodView
from vclient import sync_users_service
from vclient.exceptions import (
    APIError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServerError,
    UnprocessableEntityError,
)

from vweb.extensions import oauth
from vweb.lib import cache
from vweb.lib.catalog import catalog
from vweb.lib.htmx import htmx_response_with_flash, hx_redirect

if TYPE_CHECKING:
    from vclient.constants import IdentityProvider
    from vclient.models import User
    from werkzeug.wrappers.response import Response

logger = logging.getLogger(__name__)

_LINKABLE_PROVIDERS = ("discord", "github", "google", "apple")


def link_redirect_target() -> str:
    """Resolve where a link-mode flow should land: the user's profile when known."""
    user_id = session.get("user_id")
    return url_for("profile.profile", user_id=user_id) if user_id else url_for("index.index")


def handle_link(provider: IdentityProvider, credential: str) -> Response:
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
        # Provider-specific authorize params (e.g. Apple's response_mode=form_post)
        # are configured at registration in oauth_setup, keeping this view generic.
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
