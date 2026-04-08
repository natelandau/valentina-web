"""Dictionary browsing and CRUD blueprint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import Blueprint, abort, request
from flask.views import MethodView
from vclient.exceptions import APIError

from vweb import catalog
from vweb.lib.jinja import htmx_response
from vweb.routes.dictionary.cache import (
    clear_dictionary_cache,
    get_all_terms,
    get_term,
    search_terms,
)
from vweb.routes.dictionary.services import create_term as svc_create_term
from vweb.routes.dictionary.services import delete_term as svc_delete_term
from vweb.routes.dictionary.services import update_term as svc_update_term
from vweb.routes.dictionary.services import validate_term

if TYPE_CHECKING:
    from vclient.models import DictionaryTerm
from vweb.lib.blueprint_cache import get_subcategory, get_trait

logger = logging.getLogger(__name__)

bp = Blueprint("dictionary", __name__)


def _mutation_success_response(term: DictionaryTerm | None) -> str:
    """Render detail + OOB term list after a successful create/update/delete.

    Args:
        term: The created/updated term to display, or None for empty detail (delete).
    """
    clear_dictionary_cache()
    terms = get_all_terms()
    active_id = term.id if term else ""
    detail = catalog.render("dictionary.partials.TermDetail", term=term)
    term_list = catalog.render(
        "dictionary.partials.TermList", terms=terms, active_term_id=active_id, oob=True
    )
    return htmx_response(detail, term_list)


class DictionaryIndexView(MethodView):
    """Dictionary landing page with master-detail layout."""

    def get(self) -> str:
        """Render the dictionary index page."""
        terms = get_all_terms()
        return catalog.render("dictionary.Index", terms=terms)


class DictionarySearchView(MethodView):
    """HTMX active search endpoint returning filtered term list fragment."""

    def get(self) -> str:
        """Return filtered term list HTML fragment."""
        query = request.args.get("search", "").strip()
        include_synonyms = request.args.get("include_synonyms") == "on"
        terms = search_terms(query, include_synonyms=include_synonyms)
        return catalog.render("dictionary.partials.TermList", terms=terms)


class TermDetailView(MethodView):
    """Term definition detail view."""

    def get(self, term_id: str) -> str:
        """Render term detail as fragment (HTMX) or full page (direct nav)."""
        term = get_term(term_id)
        if term is None:
            abort(404)

        trait = None
        if (
            term.source_type is not None
            and term.source_id is not None
            and term.source_type == "trait"
        ):
            # get the trait from the trait service
            trait = get_trait(term.source_id)

        subcategory = None
        if (
            term.source_type is not None
            and term.source_id is not None
            and term.source_type == "trait_subcategory"
        ):
            # get the trait subcategory from the trait service
            subcategory = get_subcategory(term.source_id)

        is_htmx = request.headers.get("HX-Request")
        if is_htmx:
            return catalog.render(
                "dictionary.partials.TermDetail", term=term, trait=trait, subcategory=subcategory
            )

        terms = get_all_terms()
        return catalog.render(
            "dictionary.Index",
            terms=terms,
            active_term=term,
            trait=trait,
            subcategory=subcategory,
        )


class TermEmptyView(MethodView):
    """Return the empty-state placeholder for the detail panel."""

    def get(self) -> str:
        """Render empty detail placeholder."""
        return catalog.render("dictionary.partials.TermDetail")


class DictionaryFormView(MethodView):
    """Render add/edit form for a dictionary term."""

    def get(self, term_id: str | None = None) -> str:
        """Render the term form as fragment (HTMX) or full page (mobile).

        Args:
            term_id: If present, render edit form for this term. Otherwise, add form.
        """
        term = None
        if term_id:
            term = get_term(term_id)
            if term is None:
                abort(404)

        is_htmx = request.headers.get("HX-Request")
        if is_htmx:
            return catalog.render("dictionary.partials.TermForm", term=term)

        return catalog.render("dictionary.TermFormPage", term=term)


class DictionaryCreateView(MethodView):
    """Handle dictionary term creation."""

    def post(self) -> str:
        """Create a new dictionary term from form data."""
        form_data = dict(request.form)

        errors = validate_term(form_data)
        if errors:
            return catalog.render(
                "dictionary.partials.TermForm", errors=errors, form_data=form_data
            )

        try:
            created = svc_create_term(form_data)
        except APIError:
            logger.exception("Dictionary term creation failed")
            return catalog.render(
                "dictionary.partials.TermForm",
                errors=["An error occurred. Please try again."],
                form_data=form_data,
            )

        return _mutation_success_response(created)


class DictionaryUpdateView(MethodView):
    """Handle dictionary term update."""

    def post(self, term_id: str) -> str:
        """Update an existing dictionary term.

        Args:
            term_id: The ID of the term to update.
        """
        term = get_term(term_id)
        if term is None:
            abort(404)
        if term.source_type is not None:
            abort(403)

        form_data = dict(request.form)

        errors = validate_term(form_data)
        if errors:
            return catalog.render(
                "dictionary.partials.TermForm", term=term, errors=errors, form_data=form_data
            )

        try:
            updated = svc_update_term(term_id, form_data)
        except APIError:
            logger.exception("Dictionary term update failed")
            return catalog.render(
                "dictionary.partials.TermForm",
                term=term,
                errors=["An error occurred. Please try again."],
                form_data=form_data,
            )

        return _mutation_success_response(updated)


class DictionaryDeleteView(MethodView):
    """Handle dictionary term deletion."""

    def delete(self, term_id: str) -> str:
        """Delete a dictionary term.

        Args:
            term_id: The ID of the term to delete.
        """
        term = get_term(term_id)
        if term is None:
            abort(404)
        if term.source_type is not None:
            abort(403)

        try:
            svc_delete_term(term_id)
        except APIError:
            logger.exception("Dictionary term deletion failed")
            return catalog.render(
                "dictionary.partials.TermDetail",
                term=term,
                errors=["Failed to delete. Please try again."],
            )

        return _mutation_success_response(None)


bp.add_url_rule(
    "/dictionary",
    view_func=DictionaryIndexView.as_view("index"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/search",
    view_func=DictionarySearchView.as_view("search"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/term/<string:term_id>",
    view_func=TermDetailView.as_view("term_detail"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/term/empty",
    view_func=TermEmptyView.as_view("term_empty"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/term/form",
    defaults={"term_id": None},
    view_func=DictionaryFormView.as_view("term_form"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/term/form/<string:term_id>",
    endpoint="term_form_edit",
    view_func=DictionaryFormView.as_view("term_form_edit"),
    methods=["GET"],
)
bp.add_url_rule(
    "/dictionary/term",
    view_func=DictionaryCreateView.as_view("term_create"),
    methods=["POST"],
)
bp.add_url_rule(
    "/dictionary/term/<string:term_id>",
    view_func=DictionaryUpdateView.as_view("term_update"),
    methods=["POST"],
)
bp.add_url_rule(
    "/dictionary/term/<string:term_id>",
    view_func=DictionaryDeleteView.as_view("term_delete"),
    methods=["DELETE"],
)
