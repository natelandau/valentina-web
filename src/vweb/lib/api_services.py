"""API services scoped to the current request's company and signed-in user.

Request code calls these instead of the ``<name>_service()`` registry factories so the
company and On-Behalf-Of user always come from the session and are never threaded by hand.
Code that runs before a session exists, or for a company or user other than the session's
(auth flows, company selection, caches loaded with explicit ids), keeps the explicit
factories from ``vweb.api_client``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import session

from vweb.api_client import (
    books_service,
    campaigns_service,
    chapters_service,
    character_autogen_service,
    character_blueprint_service,
    character_traits_service,
    characters_service,
    dicerolls_service,
    dictionary_service,
    options_service,
    users_service,
)

if TYPE_CHECKING:
    from vweb.api_client.services import (
        BooksService,
        CampaignsService,
        ChaptersService,
        CharacterAutogenService,
        CharacterBlueprintService,
        CharactersService,
        CharacterTraitsService,
        DicerollService,
        DictionaryService,
        OptionsService,
        UsersService,
    )


class NoRequestScopeError(RuntimeError):
    """Raised when a request-scoped service is built without a signed-in user or company."""


def session_company_id() -> str:
    """Return the session's company id so request-scoped services and caches share one scope.

    Raises:
        NoRequestScopeError: If the session has no selected company.
    """
    company_id = session.get("company_id")
    if not company_id:
        msg = (
            "No company in the session; request-scoped API calls and caches need a selected company"
        )
        raise NoRequestScopeError(msg)
    return company_id


def session_user_id() -> str:
    """Return the session's signed-in user id, the On-Behalf-Of user for API calls.

    Raises:
        NoRequestScopeError: If the session has no signed-in user.
    """
    # The before-request hook resolves g.requesting_user from this same id, so it is the
    # On-Behalf-Of user in every request, including paths the hook skips.
    user_id = session.get("user_id")
    if not user_id:
        msg = "No signed-in user in the session; request-scoped API calls and caches need one"
        raise NoRequestScopeError(msg)
    return user_id


def users() -> UsersService:
    """Return the users service acting as the signed-in user in the session's company."""
    return users_service(on_behalf_of=session_user_id(), company_id=session_company_id())


def campaigns() -> CampaignsService:
    """Return the campaigns service acting as the signed-in user in the session's company."""
    return campaigns_service(on_behalf_of=session_user_id(), company_id=session_company_id())


def books(campaign_id: str) -> BooksService:
    """Return the books service for a campaign, acting as the signed-in user.

    Args:
        campaign_id: The campaign whose books the service manages.
    """
    return books_service(
        campaign_id=campaign_id, on_behalf_of=session_user_id(), company_id=session_company_id()
    )


def chapters(campaign_id: str, book_id: str) -> ChaptersService:
    """Return the chapters service for a book, acting as the signed-in user.

    Args:
        campaign_id: The campaign the book belongs to.
        book_id: The book whose chapters the service manages.
    """
    return chapters_service(
        campaign_id=campaign_id,
        book_id=book_id,
        on_behalf_of=session_user_id(),
        company_id=session_company_id(),
    )


def characters() -> CharactersService:
    """Return the characters service acting as the signed-in user in the session's company."""
    return characters_service(on_behalf_of=session_user_id(), company_id=session_company_id())


def character_traits(character_id: str) -> CharacterTraitsService:
    """Return the traits service for a character, acting as the signed-in user.

    Args:
        character_id: The character whose traits the service manages.
    """
    return character_traits_service(
        character_id=character_id, on_behalf_of=session_user_id(), company_id=session_company_id()
    )


def dicerolls() -> DicerollService:
    """Return the dice-roll service acting as the signed-in user in the session's company."""
    return dicerolls_service(on_behalf_of=session_user_id(), company_id=session_company_id())


def character_autogen() -> CharacterAutogenService:
    """Return the character autogen service acting as the signed-in user."""
    return character_autogen_service(
        on_behalf_of=session_user_id(), company_id=session_company_id()
    )


def character_blueprint() -> CharacterBlueprintService:
    """Return the session company's blueprint service, sent without an On-Behalf-Of user.

    Blueprint data is company-wide, so it is fetched the same way for every viewer.
    """
    return character_blueprint_service(company_id=session_company_id())


def dictionary() -> DictionaryService:
    """Return the session company's dictionary service, sent without an On-Behalf-Of user.

    Dictionary terms are company-wide, so they are fetched the same way for every viewer.
    """
    return dictionary_service(company_id=session_company_id())


def options() -> OptionsService:
    """Return the session company's options service, sent without an On-Behalf-Of user.

    Options also load on pages that render before the user is approved, so they must not
    depend on the user.
    """
    return options_service(company_id=session_company_id())
