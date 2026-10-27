"""Tests for character view routes."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from vclient.models import CharacterTraitSpecialty
from vclient.testing import (
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
    TraitFactory,
)

from tests.conftest import get_csrf


@pytest.fixture
def mock_character_lookup(mocker, mock_character, mock_campaign):
    """Mock get_character_and_campaign to return test character and campaign."""
    mocker.patch(
        "vweb.routes.character_view.views.get_character_and_campaign",
        return_value=(mock_character, mock_campaign),
    )
    return mock_character, mock_campaign


class TestCharacterDelete:
    """Tests for DELETE /character/<character_id>."""

    def test_owner_can_delete_character(self, client, mocker, mock_character_lookup) -> None:
        """Verify character owner can delete and gets HX-Redirect to home."""
        # Given a mocked vclient delete
        char, _ = mock_character_lookup
        mock_svc = mocker.patch(
            "vweb.routes.character_view.views.sync_characters_service",
        ).return_value
        mocker.patch("vweb.lib.cache.global_context.clear")

        csrf = get_csrf(client)

        # When sending a delete request
        response = client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the response redirects to home and delete was called
        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/"
        mock_svc.delete.assert_called_once_with(char.id)

    def test_non_owner_gets_403(self, client, mocker, mock_campaign) -> None:
        """Verify non-owner cannot delete a character."""
        # Given a character owned by a different user
        char = CharacterFactory.build(
            id="char-123",
            user_player_id="different-user-id",
            campaign_id="camp-1",
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(char, mock_campaign),
        )

        csrf = get_csrf(client)

        # When a non-owner sends a delete request
        response = client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_not_found_gets_403(self, client, mocker) -> None:
        """Verify delete returns 403 when character not found."""
        # Given no character found
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(None, None),
        )

        csrf = get_csrf(client)

        # When deleting a nonexistent character
        response = client.delete(
            "/character/bad-id",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then a 403 is returned
        assert response.status_code == 403

    def test_clears_cache_on_delete(self, client, mocker, mock_character_lookup) -> None:
        """Verify global context cache is cleared after deletion."""
        # Given a mocked vclient delete
        char, _ = mock_character_lookup
        mocker.patch("vweb.routes.character_view.views.sync_characters_service")
        mock_clear = mocker.patch("vweb.lib.cache.global_context.clear")

        csrf = get_csrf(client)

        # When deleting a character
        client.delete(
            f"/character/{char.id}",
            headers={"X-CSRFToken": csrf, "HX-Request": "true"},
        )

        # Then the cache is cleared
        mock_clear.assert_called_once()


class TestCharacterSectionGet:
    """Tests for GET /character/<id>/<section> via HTMX."""

    def test_htmx_section_returns_inner_content_only(self, client, mock_character_lookup) -> None:
        """Verify HTMX section request returns the inner content fragment without an OOB nav swap."""
        # Given a valid character
        char, _ = mock_character_lookup

        # When requesting a section via HTMX
        response = client.get(
            f"/character/{char.id}/profile",
            headers={"HX-Request": "true"},
        )

        # Then the response is the inner content fragment, no OOB CharacterNav
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="character-nav"' not in body
        assert 'hx-swap-oob="true"' not in body

    def test_stats_section_renders_lazy_statistics_url(self, client, mock_character_lookup) -> None:
        """Verify the stats section renders the /cards/statistics lazy-load URL scoped by character."""
        # Given a character from the mocked context
        char, _ = mock_character_lookup

        # When requesting the stats section
        response = client.get(f"/character/{char.id}/stats")

        # Then the rendered HTML includes the lazy-load URL scoped to the character
        assert b"/cards/statistics?" in response.data
        assert f"character_id={char.id}".encode() in response.data

    def test_info_section_redirects_to_inventory(self, client, mock_character_lookup) -> None:
        """Verify legacy /character/<id>/info redirects to /character/<id>/inventory."""
        # Given a valid character
        char, _ = mock_character_lookup

        # When hitting the legacy info URL
        response = client.get(f"/character/{char.id}/info", follow_redirects=False)

        # Then a 302 to /character/<id>/inventory is returned
        assert response.status_code == 302
        assert response.headers["Location"].endswith(f"/character/{char.id}/inventory")

    def test_info_section_redirects_to_inventory_for_htmx(
        self, client, mock_character_lookup
    ) -> None:
        """Verify legacy /character/<id>/info under HTMX returns HX-Redirect to inventory."""
        # Given a valid character
        char, _ = mock_character_lookup

        # When hitting the legacy info URL via HTMX
        response = client.get(
            f"/character/{char.id}/info",
            headers={"HX-Request": "true"},
        )

        # Then an HX-Redirect to inventory is sent
        assert response.status_code == 200
        assert response.headers["HX-Redirect"].endswith(f"/character/{char.id}/inventory")


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
        now = datetime.now(UTC)

        def specialties(names: list[str]) -> list[CharacterTraitSpecialty]:
            return [
                CharacterTraitSpecialty(
                    id=f"spec-{index}", name=name, date_created=now, date_modified=now
                )
                for index, name in enumerate(names)
            ]

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

    def test_sheet_shows_specialties_joined(self, client, mocker, mock_character_lookup) -> None:
        """Verify specialties render comma-joined for category and subcategory traits."""
        # Given a sheet with specialties on a category trait and a subcategory trait
        char, _ = mock_character_lookup
        self._sheet(mocker, melee_names=["Knives", "Swords"], pistol_names=["Pistols"])

        # When viewing the sheet
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then both specialty lines are shown
        lines = re.findall(r'<div class="trait-specialties([^"]*)">([^<]*)</div>', html)
        assert len(lines) == 2
        category_classes, category_text = lines[0]
        assert "text-sm text-base-content/60 font-normal" in category_classes
        assert category_text == "Knives, Swords"
        assert lines[1][1] == "Pistols"

    def test_sheet_escapes_specialty_names(self, client, mocker, mock_character_lookup) -> None:
        """Verify specialty names are HTML-escaped."""
        # Given a specialty containing markup
        char, _ = mock_character_lookup
        self._sheet(mocker, melee_names=['<b>"Edge"</b>'])

        # When viewing the sheet
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then the markup is escaped
        assert "&lt;b&gt;" in html
        assert '<b>"Edge"</b>' not in html

    def test_sheet_without_specialties_has_no_line(
        self, client, mocker, mock_character_lookup
    ) -> None:
        """Verify a trait with no specialties renders no specialty line."""
        # Given a sheet whose traits have no specialties
        char, _ = mock_character_lookup
        self._sheet(mocker, melee_names=[], pistol_names=[])

        # When viewing the sheet
        html = client.get(f"/character/{char.id}").get_data(as_text=True)

        # Then no specialty element is rendered
        assert "trait-specialties" not in html
