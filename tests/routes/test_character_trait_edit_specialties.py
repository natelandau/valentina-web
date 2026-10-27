"""Tests for the ability specialty endpoints."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal
from unittest.mock import MagicMock

import pytest
from vclient._sync.services import SyncCharacterTraitsService
from vclient.exceptions import NotFoundError, ValidationError
from vclient.models import CharacterTraitSpecialty
from vclient.testing import (
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CompanyFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    Routes,
    TraitFactory,
)

from tests.conftest import get_csrf
from tests.helpers import build_global_context
from vweb.routes.character_trait_edit.services import specialty_help_text

if TYPE_CHECKING:
    from vclient.models import Character

SVC_PATH = "vweb.routes.character_trait_edit.views_specialties.sync_character_traits_service"


def _specialty(specialty_id: str, name: str) -> CharacterTraitSpecialty:
    return CharacterTraitSpecialty(
        id=specialty_id,
        name=name,
        date_created="2026-01-01T00:00:00Z",
        date_modified="2026-01-01T00:00:00Z",
    )


class _Base:
    """Shared setup for specialty endpoint tests."""

    def _setup(
        self,
        client,
        mocker,
        *,
        free: Literal["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"] = "UNRESTRICTED",
        owner_id: str = "test-user-id",
        specialty_name: str = "Knives",
        recoup: Literal["UNRESTRICTED", "DENIED"] = "UNRESTRICTED",
        real_service: bool = False,
    ) -> tuple[Character, MagicMock]:
        company = CompanyFactory.build(name="Test Company")
        company.settings.permission_free_trait_changes = free
        company.settings.specialty_xp_cost_enabled = True
        company.settings.permission_recoup_xp = recoup
        ctx = build_global_context(user_role="PLAYER", company=company)
        campaign = ctx.campaigns[0]
        character = CharacterFactory.build(
            id="pc-1", campaign_id=campaign.id, type="PLAYER", user_player_id=owner_id
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        melee = CharacterTraitFactory.build(
            id="ct-melee",
            value=3,
            trait=TraitFactory.build(name="melee", sheet_section_name="Abilities"),
            specialties=[_specialty("sp-1", specialty_name)],
        )
        strength = CharacterTraitFactory.build(
            id="ct-str",
            value=3,
            trait=TraitFactory.build(name="strength", sheet_section_name="Attributes"),
            specialties=[],
        )
        insight = CharacterTraitFactory.build(
            id="ct-insight",
            value=2,
            trait=TraitFactory.build(name="insight", sheet_section_name="Abilities"),
            specialties=[],
        )
        tech = CharacterTraitFactory.build(
            id="ct-tech",
            value=0,
            trait=TraitFactory.build(name="technology", sheet_section_name="Abilities"),
            specialties=[],
        )
        category = FullSheetTraitCategoryFactory.build(
            character_traits=[melee, strength, insight, tech], subcategories=[], available_traits=[]
        )
        section = FullSheetTraitSectionFactory.build(categories=[category])
        sheet = CharacterFullSheetFactory.build(character=character, sections=[section])
        self.sheet_get = mocker.patch("vweb.lib.cache.character_sheet.get", return_value=sheet)
        self.clear_sheet = mocker.patch("vweb.lib.cache.character_sheet.clear")
        self.clear_ctx = mocker.patch("vweb.lib.cache.global_context.clear_current")

        svc = MagicMock()
        if not real_service:
            mocker.patch(SVC_PATH, return_value=svc)
        return character, svc

    def _flashes(self, client) -> list[tuple[str, str]]:
        with client.session_transaction() as sess:
            return [(category, message) for category, message in sess.get("_flashes", [])]

    def _headers(self, client) -> dict[str, str]:
        return {"HX-Request": "true", "X-CSRFToken": get_csrf(client)}

    def _url(
        self, character, spend: str, trait: str = "ct-melee", specialty: str | None = None
    ) -> str:
        base = f"/character/{character.id}/traits/{spend}/{trait}/specialties"
        return f"{base}/{specialty}" if specialty else base


@pytest.mark.parametrize(
    ("recoup", "expected"),
    [
        ("DENIED", "Renaming is free. Removing refunds starting points but not XP."),
        ("UNRESTRICTED", "Renaming is free. Removing refunds whatever was paid for it."),
        (
            "WITHIN_SESSION",
            "Renaming is free. Removing refunds starting points, and XP only within the session.",
        ),
        ("STORYTELLER", "Renaming is free. Removing refunds whatever was paid for it."),
    ],
)
def test_specialty_help_text(recoup: str, expected: str) -> None:
    """Verify the help text follows the company's XP recoup permission."""
    settings = CompanyFactory.build().settings
    settings.permission_recoup_xp = recoup
    assert specialty_help_text(settings) == expected


class TestSpecialties(_Base):
    """Dialog and add endpoint."""

    def test_add_xp_calls_api_and_flashes_cost(self, client, mocker, fake_vclient) -> None:
        """Verify a paid add calls the API, flashes the cost, and clears caches."""
        character, _ = self._setup(client, mocker, real_service=True)
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_SPECIALTY_ADD, model=CharacterTraitFactory.build()
        )
        add = mocker.spy(SyncCharacterTraitsService, "add_specialty")
        response = client.post(
            self._url(character, "XP"), data={"name": "Swords"}, headers=self._headers(client)
        )
        add.assert_called_once()
        assert add.call_args.args[1:] == ("ct-melee", "Swords")
        assert add.call_args.kwargs == {"currency": "XP"}
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert ("success", "Added Swords to Melee. You spent 3 xp") in self._flashes(client)
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    def test_add_starting_points_flash(self, client, mocker) -> None:
        """Verify the starting points flash is humanized."""
        character, _ = self._setup(client, mocker)
        client.post(
            self._url(character, "STARTING_POINTS"),
            data={"name": "Swords"},
            headers=self._headers(client),
        )
        assert (
            "success",
            "Added Swords to Melee. You spent 3 starting points",
        ) in self._flashes(client)

    def test_add_no_cost_flash_has_no_cost(self, client, mocker) -> None:
        """Verify a free add has no cost suffix."""
        character, _ = self._setup(client, mocker)
        client.post(
            self._url(character, "NO_COST"), data={"name": "Swords"}, headers=self._headers(client)
        )
        assert ("success", "Added Swords to Melee.") in self._flashes(client)

    def test_add_strips_name(self, client, mocker) -> None:
        """Verify surrounding whitespace is stripped."""
        character, svc = self._setup(client, mocker)
        client.post(
            self._url(character, "XP"), data={"name": "  Swords "}, headers=self._headers(client)
        )
        svc.add_specialty.assert_called_once_with("ct-melee", "Swords", currency="XP")

    def test_add_to_non_ability_rejected(self, client, mocker) -> None:
        """Verify attributes cannot take specialties."""
        character, svc = self._setup(client, mocker)
        client.post(
            self._url(character, "XP", "ct-str"),
            data={"name": "Swords"},
            headers=self._headers(client),
        )
        svc.add_specialty.assert_not_called()
        assert (
            "warning",
            "Only abilities with at least one dot can have specialties",
        ) in self._flashes(client)

    def test_add_duplicate_flashes_api_detail(self, client, mocker) -> None:
        """Verify an API validation error is flashed and no cache is cleared."""
        character, svc = self._setup(client, mocker)
        detail = "A specialty with this name already exists"
        svc.add_specialty.side_effect = ValidationError(detail, response_data={"detail": detail})
        client.post(
            self._url(character, "XP"), data={"name": "Knives"}, headers=self._headers(client)
        )
        assert ("error", detail) in self._flashes(client)
        self.clear_sheet.assert_not_called()

    def test_no_cost_denied_without_free_permission(self, client, mocker) -> None:
        """Verify free specialty changes need the free-edit permission on every endpoint."""
        character, svc = self._setup(client, mocker, free="STORYTELLER")
        headers = self._headers(client)
        responses = [
            client.get(self._url(character, "NO_COST"), headers=headers),
            client.post(self._url(character, "NO_COST"), data={"name": "x"}, headers=headers),
            client.post(
                self._url(character, "NO_COST", specialty="sp-1"),
                data={"name": "x"},
                headers=headers,
            ),
            client.delete(self._url(character, "NO_COST", specialty="sp-1"), headers=headers),
        ]
        for response in responses:
            assert response.headers["HX-Redirect"] == f"/character/{character.id}"
        svc.assert_not_called()
        svc.add_specialty.assert_not_called()
        svc.update_specialty.assert_not_called()
        svc.delete_specialty.assert_not_called()

    def test_non_owner_denied_on_every_endpoint(self, client, mocker) -> None:
        """Verify a player who does not own the character is denied in paid mode."""
        character, svc = self._setup(client, mocker, owner_id="someone-else")
        service_factory = mocker.patch(SVC_PATH, return_value=svc)
        headers = self._headers(client)
        responses = [
            client.get(self._url(character, "XP"), headers=headers),
            client.post(self._url(character, "XP"), data={"name": "x"}, headers=headers),
            client.post(
                self._url(character, "XP", specialty="sp-1"),
                data={"name": "x"},
                headers=headers,
            ),
            client.delete(self._url(character, "XP", specialty="sp-1"), headers=headers),
        ]
        for response in responses:
            assert response.headers["HX-Redirect"] == f"/character/{character.id}"
        service_factory.assert_not_called()
        self.clear_sheet.assert_not_called()

    def test_dialog_get_ineligible_trait_redirects(self, client, mocker) -> None:
        """Verify the dialog refuses attributes with the same warning as add."""
        character, _ = self._setup(client, mocker)
        response = client.get(self._url(character, "XP", "ct-str"), headers={"HX-Request": "true"})
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert (
            "warning",
            "Only abilities with at least one dot can have specialties",
        ) in self._flashes(client)

    def test_add_empty_name_rejected(self, client, mocker) -> None:
        """Verify a blank name on add warns without calling the API."""
        character, svc = self._setup(client, mocker)
        client.post(self._url(character, "XP"), data={"name": "   "}, headers=self._headers(client))
        svc.add_specialty.assert_not_called()
        assert ("warning", "Specialty name is required") in self._flashes(client)

    @pytest.mark.parametrize("name", ["ab", "x" * 51])
    def test_add_bad_length_rejected(self, client, mocker, name: str) -> None:
        """Verify names outside 3 to 50 characters warn without calling the API."""
        character, svc = self._setup(client, mocker)
        client.post(self._url(character, "XP"), data={"name": name}, headers=self._headers(client))
        svc.add_specialty.assert_not_called()
        assert ("warning", "Specialty names must be 3 to 50 characters.") in self._flashes(client)

    def test_lookup_uses_warm_sheet_cache_key(self, client, mocker) -> None:
        """Verify the trait lookup reads the include_available_traits=True cache entry."""
        character, _ = self._setup(client, mocker)
        client.post(
            self._url(character, "XP"), data={"name": "Swords"}, headers=self._headers(client)
        )
        self.sheet_get.assert_called_with(
            character.id, "test-user-id", include_available_traits=True
        )

    def test_dialog_inputs_have_length_limits(self, client, mocker) -> None:
        """Verify the add and rename inputs carry the length bounds and disable on submit."""
        character, _ = self._setup(client, mocker)
        html = client.get(self._url(character, "XP"), headers={"HX-Request": "true"}).get_data(
            as_text=True
        )
        assert html.count('minlength="3"') == 2
        assert html.count('maxlength="50"') == 2
        assert html.count('hx-disabled-elt="find button"') == 2
        assert 'hx-disabled-elt="this"' in html

    def test_dialog_get_renders_for_ability(self, client, mocker) -> None:
        """Verify the dialog body renders title, label, and current specialties."""
        character, _ = self._setup(client, mocker)
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Melee specialties" in html
        assert "Add · 3 XP" in html
        assert 'value="Knives"' in html
        assert "Renaming is free. Removing refunds whatever was paid for it." in html

    def test_dialog_help_text_when_xp_recoup_denied(self, client, mocker) -> None:
        """Verify the help text says XP is not refunded when recouping XP is denied."""
        character, _ = self._setup(client, mocker, recoup="DENIED")
        html = client.get(self._url(character, "XP"), headers={"HX-Request": "true"}).get_data(
            as_text=True
        )
        assert "Renaming is free. Removing refunds starting points but not XP." in html
        assert "whatever was paid for it" not in html

    def test_dialog_get_unknown_trait_redirects(self, client, mocker) -> None:
        """Verify an unknown trait redirects back with an error flash."""
        character, _ = self._setup(client, mocker)
        response = client.get(
            self._url(character, "XP", "ct-missing"), headers={"HX-Request": "true"}
        )
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert ("error", "Trait not found") in self._flashes(client)


class TestSpecialty(_Base):
    """Rename and remove endpoint."""

    def test_rename_calls_api(self, client, mocker, fake_vclient) -> None:
        """Verify rename calls the API, flashes, and clears caches."""
        character, _ = self._setup(client, mocker, real_service=True)
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_SPECIALTY_UPDATE, model=CharacterTraitFactory.build()
        )
        update = mocker.spy(SyncCharacterTraitsService, "update_specialty")
        client.post(
            self._url(character, "XP", specialty="sp-1"),
            data={"name": "Daggers"},
            headers=self._headers(client),
        )
        update.assert_called_once()
        assert update.call_args.args[1:] == ("ct-melee", "sp-1", "Daggers")
        assert ("success", "Renamed Knives to Daggers.") in self._flashes(client)
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    def test_remove_calls_api(self, client, mocker, fake_vclient) -> None:
        """Verify remove calls the API, flashes, and clears caches."""
        character, _ = self._setup(client, mocker, real_service=True)
        fake_vclient.set_response(Routes.CHARACTER_TRAITS_SPECIALTY_DELETE)
        delete = mocker.spy(SyncCharacterTraitsService, "delete_specialty")
        client.delete(self._url(character, "XP", specialty="sp-1"), headers=self._headers(client))
        delete.assert_called_once()
        assert delete.call_args.args[1:] == ("ct-melee", "sp-1")
        assert ("success", "Removed Knives from Melee.") in self._flashes(client)
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    def test_rename_empty_name_rejected(self, client, mocker) -> None:
        """Verify a blank name on rename warns without calling the API."""
        character, svc = self._setup(client, mocker)
        client.post(
            self._url(character, "XP", specialty="sp-1"),
            data={"name": " "},
            headers=self._headers(client),
        )
        svc.update_specialty.assert_not_called()
        assert ("warning", "Specialty name is required") in self._flashes(client)

    @pytest.mark.parametrize("name", ["ab", "x" * 51])
    def test_rename_bad_length_rejected(self, client, mocker, name: str) -> None:
        """Verify renames outside 3 to 50 characters warn without calling the API."""
        character, svc = self._setup(client, mocker)
        client.post(
            self._url(character, "XP", specialty="sp-1"),
            data={"name": name},
            headers=self._headers(client),
        )
        svc.update_specialty.assert_not_called()
        assert ("warning", "Specialty names must be 3 to 50 characters.") in self._flashes(client)

    def test_rename_unknown_specialty_uses_generic_wording(self, client, mocker) -> None:
        """Verify the flash reads naturally when the old name is not in the cached sheet."""
        character, svc = self._setup(client, mocker)
        client.post(
            self._url(character, "XP", specialty="sp-other"),
            data={"name": "Daggers"},
            headers=self._headers(client),
        )
        svc.update_specialty.assert_called_once_with("ct-melee", "sp-other", "Daggers")
        assert ("success", "Renamed a specialty to Daggers.") in self._flashes(client)

    def test_remove_unknown_specialty_uses_generic_wording(self, client, mocker) -> None:
        """Verify the remove flash reads naturally for an unknown specialty."""
        character, _ = self._setup(client, mocker)
        client.delete(
            self._url(character, "XP", specialty="sp-other"), headers=self._headers(client)
        )
        assert ("success", "Removed a specialty from Melee.") in self._flashes(client)

    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_stale_specialty_flashes_error(self, client, mocker, method: str) -> None:
        """Verify a missing specialty flashes the API detail instead of raising."""
        character, svc = self._setup(client, mocker)
        error = NotFoundError(
            "Specialty not found", response_data={"detail": "Specialty not found"}
        )
        svc.update_specialty.side_effect = error
        svc.delete_specialty.side_effect = error
        response = getattr(client, method)(
            self._url(character, "XP", specialty="sp-gone"),
            data={"name": "Daggers"} if method == "post" else None,
            headers=self._headers(client),
        )
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert ("error", "Specialty not found") in self._flashes(client)
        self.clear_sheet.assert_not_called()


class TestSpecialtyUi(_Base):
    """Rendering of the specialty controls on the Manage Traits form."""

    def _form(self, client, mocker) -> tuple[Character, str]:
        character, _ = self._setup(client, mocker)
        response = client.get(f"/character/{character.id}/traits/XP")
        return character, response.get_data(as_text=True)

    def test_form_has_shared_specialty_dialog(self, client, mocker) -> None:
        """Verify the shared dialog and its body container render."""
        _, html = self._form(client, mocker)
        assert 'id="specialty-modal"' in html
        assert 'id="specialty-modal-body"' in html

    def test_trait_with_specialties_shows_line_and_pencil(self, client, mocker) -> None:
        """Verify a trait with specialties shows its names and an edit pencil."""
        character, html = self._form(client, mocker)
        url = self._url(character, "XP")
        assert re.search(
            r'<span class="text-sm text-base-content/60 font-normal">Knives</span>', html
        )
        pencil = html.split("fa-pencil")[0].rsplit("<button", 1)[1]
        assert f'hx-get="{url}"' in pencil
        assert 'aria-label="Edit Melee specialties"' in pencil

    def test_dialog_opens_itself_after_swap(self, client, mocker) -> None:
        """Verify the dialog opens on the bubbled swap event and no trigger carries a handler."""
        _, html = self._form(client, mocker)
        dialog = html.split('<dialog id="specialty-modal"')[1].split(">")[0]
        assert 'hx-on::after-swap="if (!this.open) this.showModal()"' in dialog
        assert html.count("after-swap") == 1
        assert "after-request" not in html
        assert 'aria-label="Add a specialty to Insight"' in html

    def test_eligible_trait_without_specialties_shows_add_link(self, client, mocker) -> None:
        """Verify an eligible trait without specialties shows the add link."""
        character, html = self._form(client, mocker)
        marker = f'hx-get="{self._url(character, "XP", "ct-insight")}"'
        assert marker in html
        button = html.split(marker)[1].split("</button>")[0]
        assert "fa-plus" in button
        assert "specialty" in button

    def test_ineligible_traits_have_no_specialty_controls(self, client, mocker) -> None:
        """Verify attributes and zero-dot abilities get no controls."""
        character, html = self._form(client, mocker)
        assert self._url(character, "XP", "ct-tech") not in html
        assert self._url(character, "XP", "ct-str") not in html

    def test_dialog_escapes_names(self, client, mocker) -> None:
        """Verify specialty names are escaped in the dialog inputs."""
        evil = '<b>"Edge"</b>'
        character, _ = self._setup(client, mocker, specialty_name=evil)
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})
        html = response.get_data(as_text=True)
        assert evil not in html
        assert 'value="&lt;b&gt;' in html

    def test_dialog_rows_post_and_delete(self, client, mocker) -> None:
        """Verify rows rename and remove, the add row posts, and help text shows."""
        character, _ = self._setup(client, mocker)
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})
        html = response.get_data(as_text=True)
        item = self._url(character, "XP", specialty="sp-1")
        assert f'hx-post="{item}"' in html
        assert f'hx-delete="{item}"' in html
        assert f'hx-post="{self._url(character, "XP")}"' in html
        assert "Renaming is free. Removing refunds whatever was paid for it." in html

    def test_dialog_without_specialties_has_no_divider(self, client, mocker) -> None:
        """Verify the divider is omitted when there is nothing above the add row."""
        character, _ = self._setup(client, mocker)
        response = client.get(
            self._url(character, "XP", "ct-insight"), headers={"HX-Request": "true"}
        )
        html = response.get_data(as_text=True)
        assert 'class="divider' not in html
        assert 'placeholder="New specialty"' in html

    def test_dialog_structure(self, client, mocker) -> None:
        """Verify row forms scope their own input, and the divider, close, and label render."""
        character, _ = self._setup(client, mocker)
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})
        html = response.get_data(as_text=True)
        item = self._url(character, "XP", specialty="sp-1")
        row_form = html.split(f'<form hx-post="{item}"')[1].split("</form>")[0]
        assert row_form.count('name="name"') == 1
        assert 'aria-label="Rename Knives"' in row_form
        assert 'aria-label="Save new name for Knives"' in row_form
        assert 'aria-label="Remove Knives"' in row_form
        assert 'class="divider' in html
        assert 'placeholder="New specialty"' in html
        assert "Close</button>" in html
        assert "this.closest('dialog').close()" in html
        assert ">Add · 3 XP</button>" in html
        assert 'id="specialty-dialog-heading"' in html
