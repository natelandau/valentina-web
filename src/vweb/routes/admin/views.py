"""Admin routes: audit log, company settings, user management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from flask import Blueprint, flash, g, redirect, request, session, url_for
from flask.views import MethodView
from pydantic import ValidationError
from vclient import sync_companies_service
from vclient.models.companies import CompanySettingsUpdate, CompanyUpdate

from vweb import catalog
from vweb.lib.global_context import clear_global_context_cache
from vweb.lib.guards import is_admin, is_self
from vweb.lib.jinja import htmx_response, hx_redirect
from vweb.routes.admin import audit_log_services
from vweb.routes.admin import services as admin_services
from vweb.routes.admin.audit_log_services import ENTITY_TYPES

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def _require_admin() -> Response | None:
    """Allow only users with role 'ADMIN' to access this blueprint."""
    if not is_admin():
        flash("You do not have permission to view that page.", "error")
        return redirect(url_for("index.index"))
    return None


def _empty_to_none(value: str | None) -> str | None:
    """Treat empty/whitespace-only strings as None for optional fields."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class _FieldValueError(ValueError):
    """Raised when a form field value fails parsing; carries the field key."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _parse_optional_int(value: str | None, name: str, label: str) -> int | None:
    """Parse a non-empty string as int, returning None for blank values.

    Args:
        value: Raw string from the form field.
        name: Form field name (used as the error key in the template).
        label: Human-readable label for the error message.

    Raises:
        _FieldValueError: If the value is non-empty but cannot be parsed as an integer.
    """
    s = _empty_to_none(value)
    if s is None:
        return None
    try:
        return int(s)
    except ValueError as exc:
        msg = f"{label} must be a whole number."
        raise _FieldValueError(name, msg) from exc


def _build_update(form: dict[str, Any]) -> CompanyUpdate:
    """Build a CompanyUpdate from raw form data.

    Args:
        form: Raw key/value pairs from the submitted form.

    Raises:
        ValueError: If a numeric field contains a non-integer value.
    """
    settings_payload: dict[str, Any] = {
        "character_autogen_xp_cost": _parse_optional_int(
            form.get("character_autogen_xp_cost"),
            "character_autogen_xp_cost",
            "Autogen XP Cost",
        ),
        "character_autogen_num_choices": _parse_optional_int(
            form.get("character_autogen_num_choices"),
            "character_autogen_num_choices",
            "Number of Choices",
        ),
        "character_autogen_starting_points": _parse_optional_int(
            form.get("character_autogen_starting_points"),
            "character_autogen_starting_points",
            "Starting Points",
        ),
        "permission_manage_campaign": _empty_to_none(form.get("permission_manage_campaign")),
        "permission_grant_xp": _empty_to_none(form.get("permission_grant_xp")),
        "permission_free_trait_changes": _empty_to_none(form.get("permission_free_trait_changes")),
        "permission_recoup_xp": _empty_to_none(form.get("permission_recoup_xp")),
    }
    return CompanyUpdate(
        name=form.get("name", "").strip(),
        email=_empty_to_none(form.get("email")),
        description=_empty_to_none(form.get("description")),
        settings=CompanySettingsUpdate(**settings_payload),
    )


def _format_pydantic_errors(exc: ValidationError) -> dict[str, str]:
    """Convert a pydantic ValidationError into a {field_name: message} dict.

    Errors on nested CompanySettings come back with a location like
    ('settings', 'character_autogen_xp_cost'); surface the leaf field name so the
    template can render them under the matching <fieldset>.
    """
    errors: dict[str, str] = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        field = str(loc[-1]) if loc else "_form"
        errors[field] = err.get("msg", "Invalid value.")
    return errors


PAGE_SIZE = 20


class AuditLogView(MethodView):
    """Display the full audit log page with filters and lazy-loaded table."""

    def get(self) -> str:
        """Render the audit log page shell with empty table that loads via HTMX."""
        users = g.global_context.users
        return catalog.render(
            "admin.AuditLogPage",
            users=users,
            entity_types=ENTITY_TYPES,
            pending_count=admin_services.pending_user_count(g.requesting_user.id),
        )


class AuditLogTableView(MethodView):
    """HTMX endpoint returning audit log table rows with pagination."""

    def get(self) -> str:
        """Return rendered table rows for the current filter/offset combination."""
        offset = request.args.get("offset", 0, type=int)
        is_initial = offset == 0
        entity_type = request.args.get("entity_type", "")
        operation = request.args.get("operation", "")
        acting_user_id = request.args.get("acting_user_id", "")
        date_from = request.args.get("date_from", "")
        date_to = request.args.get("date_to", "")

        page = audit_log_services.get_audit_log_page(
            limit=PAGE_SIZE,
            offset=offset,
            entity_type=entity_type,
            operation=operation,
            acting_user_id=acting_user_id,
            date_from=date_from,
            date_to=date_to,
        )

        context = g.global_context
        rows = []
        for log in page.items:
            entities = audit_log_services.resolve_entities(log, context)
            acting_name, acting_url = audit_log_services.resolve_acting_user(
                log.acting_user_id, context
            )

            rows.append(
                {
                    "log": log,
                    "entities": entities,
                    "acting_user_name": acting_name,
                    "acting_user_url": acting_url,
                }
            )

        filters = {
            "entity_type": entity_type,
            "operation": operation,
            "acting_user_id": acting_user_id,
            "date_from": date_from,
            "date_to": date_to,
        }
        new_offset = offset + PAGE_SIZE

        return catalog.render(
            "admin.partials.AuditLogTable",
            rows=rows,
            total=page.total,
            offset=new_offset,
            has_more=page.has_more,
            filter_params=urlencode({k: v for k, v in filters.items() if v}),
            is_initial=is_initial,
        )


class SettingsView(MethodView):
    """Display and edit company settings (admin only)."""

    def get(self) -> str:
        """Render the company settings page with current company values pre-populated."""
        company_id = session["company_id"]
        company = sync_companies_service().get(company_id)
        return catalog.render(
            "admin.SettingsPage",
            company=company,
            errors={},
            form_values=None,
            pending_count=admin_services.pending_user_count(g.requesting_user.id),
        )

    def post(self) -> Response | tuple[str, int]:
        """Validate the form and update the company."""
        company_id = session["company_id"]
        form = request.form.to_dict()

        errors: dict[str, str] = {}
        update: CompanyUpdate | None = None
        try:
            update = _build_update(form)
        except ValidationError as exc:
            errors = _format_pydantic_errors(exc)
        except _FieldValueError as exc:
            errors[exc.field] = str(exc)

        if errors or update is None:
            company = sync_companies_service().get(company_id)
            page = catalog.render(
                "admin.SettingsPage",
                company=company,
                errors=errors,
                form_values=form,
                pending_count=admin_services.pending_user_count(g.requesting_user.id),
            )
            return page, 400

        sync_companies_service().update(company_id, request=update)
        clear_global_context_cache(session["company_id"], session["user_id"])
        flash("Settings updated.", "success")
        return redirect(url_for("admin.settings"))


class UsersView(MethodView):
    """Display the user management page."""

    def get(self) -> str:
        """Render pending and approved users for the current company."""
        pending, approved = admin_services.list_pending_and_approved(g.requesting_user.id)
        return catalog.render(
            "admin.UsersPage",
            pending=pending,
            approved=approved,
            pending_count=len(pending),
        )


class ApproveUserView(MethodView):
    """POST endpoint to approve a pending user with a chosen role."""

    def post(self, user_id: str) -> tuple[str, int] | str:
        """Approve a pending user after validating self and role.

        Prevent self-approval (admins cannot modify their own account) and reject
        UNAPPROVED so approval cannot reset a user back to pending.
        """
        if is_self(user_id):
            return "Cannot modify your own account.", 403

        role = request.form.get("role", "")
        try:
            admin_services.approve(user_id, role, g.requesting_user.id)
        except ValueError as exc:
            return str(exc), 400

        flash("User approved.", "success")
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response("", flash_html)


class ChangeRoleView(MethodView):
    """POST endpoint to change an approved user's role inline."""

    def post(self, user_id: str) -> tuple[str, int] | str:
        """Update the user's role and return the swapped ApprovedUserRow.

        Prevent self-modification and reject UNAPPROVED so this path cannot
        re-pend a user.
        """
        if is_self(user_id):
            return "Cannot modify your own account.", 403

        role = request.form.get("role", "")
        try:
            user = admin_services.change_role(user_id, role, g.requesting_user.id)
        except ValueError as exc:
            return str(exc), 400

        flash("Role updated.", "success")
        row = catalog.render("admin.components.ApprovedUserRow", user=user)
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response(row, flash_html)


class DenyUserView(MethodView):
    """POST endpoint to deny a pending user."""

    def post(self, user_id: str) -> tuple[str, int] | str:
        """Deny the user and return an empty swap with a flashed success."""
        if is_self(user_id):
            return "Cannot modify your own account.", 403

        admin_services.deny(user_id, g.requesting_user.id)
        flash("User denied.", "success")
        flash_html = catalog.render("shared.layout.FlashMessage", oob=True)
        return htmx_response("", flash_html)


class MergeFormView(MethodView):
    """GET endpoint that returns the merge modal for a pending user."""

    def get(self, user_id: str) -> tuple[str, int] | str:
        """Return the modal HTML with a picker of approved users."""
        pending, candidates = admin_services.list_pending_and_approved(g.requesting_user.id)
        pending_user = next((u for u in pending if u.id == user_id), None)
        if pending_user is None:
            return "", 404
        return catalog.render(
            "admin.partials.MergeModal",
            pending_user=pending_user,
            candidates=candidates,
        )


class MergeUserView(MethodView):
    """POST endpoint that merges a pending user into a primary user."""

    def post(self, user_id: str) -> tuple[str, int] | Response:
        """Merge and return an HX-Redirect to /admin/users."""
        target_id = request.form.get("target_user_id", "")
        if is_self(user_id) or is_self(target_id):
            return "Cannot modify your own account.", 403
        if not target_id:
            return "target_user_id is required.", 400

        admin_services.merge(target_id, user_id, g.requesting_user.id)
        flash("Users merged.", "success")
        return hx_redirect(url_for("admin.users"))


bp.add_url_rule("", view_func=AuditLogView.as_view("audit_log"), methods=["GET"])
bp.add_url_rule(
    "/audit-log", view_func=AuditLogTableView.as_view("audit_log_table"), methods=["GET"]
)
bp.add_url_rule("/settings", view_func=SettingsView.as_view("settings"), methods=["GET", "POST"])
bp.add_url_rule("/users", view_func=UsersView.as_view("users"), methods=["GET"])
bp.add_url_rule(
    "/users/<user_id>/approve",
    view_func=ApproveUserView.as_view("approve_user"),
    methods=["POST"],
)
bp.add_url_rule(
    "/users/<user_id>/role",
    view_func=ChangeRoleView.as_view("change_role"),
    methods=["POST"],
)
bp.add_url_rule(
    "/users/<user_id>/deny",
    view_func=DenyUserView.as_view("deny_user"),
    methods=["POST"],
)
bp.add_url_rule(
    "/users/<user_id>/merge",
    view_func=MergeFormView.as_view("merge_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/users/<user_id>/merge",
    view_func=MergeUserView.as_view("merge_user"),
    methods=["POST"],
)
