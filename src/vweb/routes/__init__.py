"""Route blueprints.

``get_blueprints()`` is the single registration list consumed by ``create_app()``.
Registration order is preserved exactly because route matching and
before_request hooks can be order-sensitive. Imports happen inside the
function so that importing one route module does not eagerly load every
view module in the package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Blueprint


def get_blueprints() -> tuple[Blueprint, ...]:
    """Assemble every route blueprint in registration order for create_app().

    Returns:
        tuple[Blueprint, ...]: Blueprints in the exact order they must be
            registered on the Flask app.
    """
    from vweb.routes.admin.views import bp as admin_bp
    from vweb.routes.auth.views import bp as auth_bp
    from vweb.routes.book.views import bp as book_view_bp
    from vweb.routes.campaign.views import bp as campaign_bp
    from vweb.routes.campaign_notes.views import bp as campaign_notes_bp
    from vweb.routes.chapter.views import bp as chapter_view_bp
    from vweb.routes.character_create import bp as character_create_bp
    from vweb.routes.character_list.views import bp as character_list_bp
    from vweb.routes.character_trait_edit.views import bp as character_trait_edit_bp
    from vweb.routes.character_view.views import bp as character_view_bp
    from vweb.routes.company_hub.views import bp as company_hub_bp
    from vweb.routes.diceroll.views import bp as diceroll_bp
    from vweb.routes.dictionary.views import bp as dictionary_bp
    from vweb.routes.fragments_shared_cards.views import bp as shared_cards_bp
    from vweb.routes.index.views import bp as index_bp
    from vweb.routes.player_list.views import bp as player_list_bp
    from vweb.routes.profile.views import bp as profile_bp
    from vweb.routes.static_files.views import bp as static_files_bp

    return (
        auth_bp,
        index_bp,
        company_hub_bp,
        campaign_bp,
        shared_cards_bp,
        campaign_notes_bp,
        character_view_bp,
        character_trait_edit_bp,
        book_view_bp,
        chapter_view_bp,
        profile_bp,
        diceroll_bp,
        dictionary_bp,
        character_create_bp,
        character_list_bp,
        player_list_bp,
        admin_bp,
        static_files_bp,
    )
