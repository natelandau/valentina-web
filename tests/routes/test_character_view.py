"""Tests for character view routes."""

from __future__ import annotations

import html as html_lib
from datetime import date
from typing import TYPE_CHECKING

import pytest

from tests.conftest import get_csrf, htmx_delete
from tests.helpers import build_specialty
from vweb.api_client.testing import (
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
    Routes,
    TraitFactory,
)

if TYPE_CHECKING:
    from vweb.api_client.models import CharacterTraitSpecialty


@pytest.fixture
def own_character(use_context, mock_character, mock_campaign):
    """Put the session user's own player character and its campaign in the context."""
    use_context(user_role="PLAYER", campaign=mock_campaign, characters=[mock_character])
    return mock_character, mock_campaign


class TestCharacterDelete:
    """Tests for DELETE /character/<character_id>."""

    def test_owner_can_delete_character(self, client, mocker, fake_vclient, own_character) -> None:
        """Verify the owner can delete, which clears the cached context and redirects home."""
        # Given an owned character
        char, _ = own_character
        mock_clear = mocker.patch("vweb.lib.cache.global_context.clear")

        # When sending a delete request
        response = htmx_delete(client, f"/character/{char.id}")

        # Then the character is deleted, the cached context dropped, and the user sent home
        fake_vclient.assert_called(
            Routes.CHARACTERS_DELETE,
            params={"company_id": "test-company-id", "character_id": char.id},
            times=1,
        )
        mock_clear.assert_called_once()
        assert response.headers.get("HX-Redirect") == "/"

    @pytest.mark.parametrize("found", [True, False], ids=["other-players-character", "not-found"])
    def test_non_owner_gets_403(
        self, client, use_context, fake_vclient, mock_campaign, found
    ) -> None:
        """Verify a player cannot delete another player's or an unknown character."""
        # Given a character owned by someone else, or none at all
        char = CharacterFactory.build(
            id="char-123", user_player_id="different-user-id", campaign_id="camp-1"
        )
        use_context(user_role="PLAYER", campaign=mock_campaign, characters=[char] if found else [])

        # When sending a delete request
        response = htmx_delete(client, "/character/char-123")

        # Then a 403 is returned and nothing is deleted
        assert response.status_code == 403
        fake_vclient.assert_not_called(Routes.CHARACTERS_DELETE)


class TestCharacterSectionGet:
    """Tests for GET /character/<id>/<section>."""

    @pytest.mark.parametrize(
        ("section", "expected"),
        [
            ("", None),
            ("profile", None),
            ("unknown-section", None),
            ("inventory", "/character/char-123/inventory/items?editable=true"),
            ("notes", "/character/char-123/notes/items?editable=true"),
            ("stats", "/cards/statistics?character_id=char-123"),
        ],
    )
    def test_htmx_section_returns_fragment(
        self, client, mocker, own_character, section, expected
    ) -> None:
        """Verify an HTMX section request returns only the tab content, with lazy loads wired."""
        # Given the user's own character
        char, _ = own_character
        mocker.patch(
            "vweb.lib.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(character=char, sections=[]),
        )

        # When requesting a section via HTMX
        path = f"/character/{char.id}/{section}" if section else f"/character/{char.id}"
        response = client.get(path, headers={"HX-Request": "true"})

        # Then the response is the tab fragment without page chrome
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'id="character-nav"' not in body
        # And a lazily loaded tab points at its data endpoint
        if expected:
            assert expected in html_lib.unescape(body)

    def test_other_players_tables_load_read_only(self, client, use_context, mock_campaign) -> None:
        """Verify another player's inventory loads its table without edit controls."""
        # Given another player's character
        other = CharacterFactory.build(
            id="char-123", user_player_id="someone-else", campaign_id="camp-1"
        )
        use_context(user_role="PLAYER", campaign=mock_campaign, characters=[other])

        # When opening the inventory tab
        response = client.get("/character/char-123/inventory", headers={"HX-Request": "true"})

        # Then the table is requested read-only
        assert "/character/char-123/inventory/items?editable=false" in response.get_data(
            as_text=True
        )

    @pytest.mark.parametrize("htmx", [True, False])
    def test_unknown_character_redirects_home(self, client, htmx) -> None:
        """Verify a character the user cannot see sends them home."""
        # When opening a character that is not in the user's context
        response = client.get("/character/bad-id", headers={"HX-Request": "true"} if htmx else {})

        # Then the user is sent home
        target = response.headers["HX-Redirect"] if htmx else response.headers["Location"]
        assert target == "/"

    @pytest.mark.parametrize("htmx", [True, False])
    def test_info_section_redirects_to_inventory(self, client, own_character, htmx) -> None:
        """Verify the legacy info URL redirects to the inventory tab."""
        # Given a valid character
        char, _ = own_character

        # When hitting the legacy info URL
        response = client.get(
            f"/character/{char.id}/info", headers={"HX-Request": "true"} if htmx else {}
        )

        # Then the user is sent to the inventory tab
        target = response.headers["HX-Redirect"] if htmx else response.headers["Location"]
        assert target.endswith(f"/character/{char.id}/inventory")


class TestImageViewsUnknownCharacter:
    """Image upload and delete refuse a character the user cannot see."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [("post", "/character/bad-id/images"), ("delete", "/character/bad-id/images/asset-1")],
        ids=["upload", "delete"],
    )
    def test_returns_404_without_api_call(self, client, fake_vclient, method, path) -> None:
        """Verify an unknown character returns 404 and touches no asset."""
        # When uploading or deleting an image of a character not in the user's context
        response = getattr(client, method)(
            path, headers={"X-CSRFToken": get_csrf(client), "HX-Request": "true"}
        )

        # Then 404 is returned and the API is not called
        assert response.status_code == 404
        assert fake_vclient.requests == []


class TestSheetSidebarOwnerLink:
    """Tests for the character sheet sidebar's player-profile link."""

    def test_npc_without_owner_renders_without_profile_link(self, app) -> None:
        """Verify an ownerless NPC renders the sheet sidebar without a profile link or crash."""
        from flask import g

        from tests.helpers import build_global_context
        from vweb.lib.catalog import catalog

        # Given an NPC with no owning player, viewed by a storyteller
        npc = CharacterFactory.build(
            name="Sentinel", type="NPC", user_player_id=None, character_class="MORTAL"
        )
        ctx = build_global_context(user_role="STORYTELLER")

        # When rendering the sheet sidebar
        with app.test_request_context():
            g.global_context = ctx
            g.requesting_user = ctx.users[0]
            html = catalog.render("character_view.components.SheetSidebar", character=npc)

        # Then it renders without building a profile URL (no owner to link to)
        assert "/profile/" not in html


class TestSheetSpecialties:
    """Tests for ability specialties on the character sheet tab."""

    @staticmethod
    def _sheet(mocker, *, melee_names: list[str], pistol_names: list[str] | None = None) -> None:
        """Patch the cached full sheet with a Melee trait and an optional subcategory trait."""

        def specialties(names: list[str]) -> list[CharacterTraitSpecialty]:
            return [build_specialty(f"spec-{index}", name) for index, name in enumerate(names)]

        melee = CharacterTraitFactory.build(
            value=3,
            trait=TraitFactory.build(name="Melee", max_value=5),
            specialties=specialties(melee_names),
        )
        subcategories = []
        if pistol_names is not None:
            pistols = CharacterTraitFactory.build(
                value=2,
                trait=TraitFactory.build(name="Firearms", max_value=5),
                specialties=specialties(pistol_names),
            )
            subcategories = [
                FullSheetTraitSubcategoryFactory.build(name="Guns", character_traits=[pistols])
            ]
        category = FullSheetTraitCategoryFactory.build(
            name="Skills",
            show_when_empty=True,
            character_traits=[melee],
            subcategories=subcategories,
        )
        section = FullSheetTraitSectionFactory.build(name="Abilities", categories=[category])
        sheet = CharacterFullSheetFactory.build(sections=[section])
        mocker.patch(
            "vweb.routes.character_view.views.cache.character_sheet.get", return_value=sheet
        )

    def test_sheet_shows_specialties(self, client, mocker, own_character) -> None:
        """Verify specialties show for category and subcategory traits."""
        # Given a sheet with specialties on a category trait and a subcategory trait
        char, _ = own_character
        self._sheet(mocker, melee_names=["Knives", "Swords"], pistol_names=["Pistols"])

        # When viewing the sheet
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then both traits' specialties are shown
        assert "Knives, Swords" in html
        assert "Pistols" in html

    def test_sheet_escapes_specialty_names(self, client, mocker, own_character) -> None:
        """Verify specialty names are HTML-escaped."""
        # Given a specialty containing markup
        char, _ = own_character
        self._sheet(mocker, melee_names=['<b>"Edge"</b>'])

        # When viewing the sheet
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then the markup is escaped
        assert "&lt;b&gt;" in html
        assert '<b>"Edge"</b>' not in html


class TestDateOfBirthBanner:
    """The banner asking for a date of birth appears only where the age could follow it."""

    @pytest.mark.parametrize(
        ("in_game_date", "date_of_birth", "status", "owner", "shown"),
        [
            (date(1990, 6, 1), None, "ALIVE", "test-user-id", True),
            (None, None, "ALIVE", "test-user-id", False),
            (date(1990, 6, 1), date(1960, 3, 15), "ALIVE", "test-user-id", False),
            (date(1990, 6, 1), None, "DEAD", "test-user-id", False),
            (date(1990, 6, 1), None, "ALIVE", "someone-else", False),
        ],
        ids=["shown", "undated-campaign", "has-birth-date", "dead", "not-an-editor"],
    )
    def test_banner_needs_dated_campaign_and_living_character_without_birth_date(  # noqa: PLR0917
        self,
        client,
        mocker,
        own_character,
        in_game_date,
        date_of_birth,
        status,
        owner,
        shown,
    ) -> None:
        """Verify an editor is asked for a living character's birth date in a dated campaign."""
        # Given the campaign's in-game date and the character's birth, status, and owner
        char, campaign = own_character
        campaign.in_game_date = in_game_date
        char.date_of_birth = date_of_birth
        char.status = status
        char.user_player_id = owner
        mocker.patch(
            "vweb.lib.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(character=char, sections=[]),
        )

        # When viewing the character
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then the banner's own link to the profile editor appears only in the expected case;
        # an editor always has one more link to it in the actions menu
        edit_url = html_lib.escape(
            f"/campaign/{campaign.id}/characters/profile_edit?character_id={char.id}"
        )
        editor = owner == "test-user-id"
        assert html.count(edit_url) == int(editor) + int(shown)
