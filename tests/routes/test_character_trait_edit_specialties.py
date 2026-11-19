"""Tests for the ability specialty endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

from tests.conftest import get_csrf, htmx_delete, htmx_post
from tests.helpers import build_global_context, build_specialty, session_flashes
from vweb.api_client.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CompanyFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    Routes,
    TraitFactory,
)

if TYPE_CHECKING:
    from vweb.api_client.constants import SpecialtyRules
    from vweb.api_client.models import Character


class _Base:
    """Shared setup for specialty endpoint tests."""

    @pytest.fixture(autouse=True)
    def _fake(self, fake_vclient, use_context) -> None:
        self.fake = fake_vclient
        self.use_context = use_context

    def _setup(
        self,
        client,
        mocker,
        *,
        free: Literal["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"] = "UNRESTRICTED",
        owner_id: str = "test-user-id",
        specialty_name: str = "Knives",
        recoup: Literal["UNRESTRICTED", "DENIED"] = "UNRESTRICTED",
        rules: SpecialtyRules = "FIXED_COST",
        strength_value: int = 3,
    ) -> Character:
        company = CompanyFactory.build(name="Test Company")
        company.settings.specialty_rules = rules
        company.settings.permission_free_trait_changes = free
        company.settings.specialty_xp_cost_enabled = True
        company.settings.permission_recoup_xp = recoup
        ctx = build_global_context(user_role="PLAYER", company=company)
        campaign = ctx.campaigns[0]
        character = CharacterFactory.build(
            id="pc-1", campaign_id=campaign.id, user_player_id=owner_id
        )
        ctx.characters = [character]
        self.use_context(ctx)

        melee = CharacterTraitFactory.build(
            id="ct-melee",
            value=3,
            trait=TraitFactory.build(name="melee", sheet_section_name="Abilities"),
            specialties=[build_specialty("sp-1", specialty_name)],
        )
        strength = CharacterTraitFactory.build(
            id="ct-str",
            value=strength_value,
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
        return character

    def _headers(self, client) -> dict[str, str]:
        return {"HX-Request": "true", "X-CSRFToken": get_csrf(client)}

    def _trait_params(self, specialty_id: str | None = None) -> dict[str, str]:
        params = {
            "company_id": "test-company-id",
            "character_id": "pc-1",
            "character_trait_id": "ct-melee",
        }
        if specialty_id:
            params["specialty_id"] = specialty_id
        return params

    def _url(
        self, character, spend: str, trait: str = "ct-melee", specialty: str | None = None
    ) -> str:
        base = f"/character/{character.id}/traits/{spend}/{trait}/specialties"
        return f"{base}/{specialty}" if specialty else base


class TestSpecialties(_Base):
    """Dialog and add endpoint."""

    @pytest.mark.parametrize("spend", ["XP", "STARTING_POINTS", "NO_COST"])
    def test_add_sends_name_and_currency(self, client, mocker, spend: str) -> None:
        """Verify an add sends the stripped name with the page's currency and clears caches."""
        # Given an ability the user may edit
        character = self._setup(client, mocker)

        # When adding a specialty with padded whitespace
        response = htmx_post(client, self._url(character, spend), {"name": "  Swords "})

        # Then the stripped name is sent with the currency and the stale sheet is dropped
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_SPECIALTY_ADD,
            params=self._trait_params(),
            json={"name": "Swords", "currency": spend},
            times=1,
        )
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/{spend}"
        assert [category for category, _ in session_flashes(client)] == ["success"]
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    def test_add_to_non_ability_rejected(self, client, mocker) -> None:
        """Verify attributes cannot take specialties under FIXED_COST rules."""
        # Given an attribute
        character = self._setup(client, mocker)

        # When adding a specialty to it
        htmx_post(client, self._url(character, "XP", "ct-str"), {"name": "Swords"})

        # Then nothing is sent and the user is warned
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_SPECIALTY_ADD)
        assert [category for category, _ in session_flashes(client)] == ["warning"]

    def test_add_duplicate_flashes_api_detail(self, client, mocker) -> None:
        """Verify an API validation error is flashed and no cache is cleared."""
        # Given an API that rejects the name
        character = self._setup(client, mocker)
        detail = "A specialty with this name already exists"
        self.fake.set_error(Routes.CHARACTER_TRAITS_SPECIALTY_ADD, status_code=400, detail=detail)

        # When adding the specialty
        htmx_post(client, self._url(character, "XP"), {"name": "Knives"})

        # Then the API's reason is flashed and the sheet cache is kept
        assert ("error", detail) in session_flashes(client)
        self.clear_sheet.assert_not_called()

    @pytest.mark.parametrize(
        ("setup_kwargs", "spend"),
        [
            ({"free": "STORYTELLER"}, "NO_COST"),
            ({"owner_id": "someone-else"}, "XP"),
        ],
        ids=["no-free-edit-permission", "not-the-owner"],
    )
    def test_denied_on_every_endpoint(self, client, mocker, setup_kwargs, spend: str) -> None:
        """Verify a user who may not edit the character is refused by every specialty endpoint."""
        # Given a character the user may not change this way
        character = self._setup(client, mocker, **setup_kwargs)
        headers = self._headers(client)

        # When calling each specialty endpoint
        responses = [
            client.get(self._url(character, spend), headers=headers),
            client.post(self._url(character, spend), data={"name": "Swords"}, headers=headers),
            client.post(
                self._url(character, spend, specialty="sp-1"),
                data={"name": "Daggers"},
                headers=headers,
            ),
            client.delete(self._url(character, spend, specialty="sp-1"), headers=headers),
        ]

        # Then each is sent back to the character and nothing reaches the API
        for response in responses:
            assert response.headers["HX-Redirect"] == f"/character/{character.id}"
        assert self.fake.requests == []
        self.clear_sheet.assert_not_called()

    def test_unknown_character_redirects_home(self, client, mocker) -> None:
        """Verify a character outside the user's context sends them home without an API call."""
        # Given a character id the user cannot see
        self._setup(client, mocker)

        # When opening its specialty dialog
        response = client.get(
            "/character/missing/traits/XP/ct-melee/specialties", headers={"HX-Request": "true"}
        )

        # Then the user is sent home
        assert response.headers["HX-Redirect"] == "/"
        assert self.fake.requests == []

    @pytest.mark.parametrize(
        ("trait", "category"),
        [("ct-str", "warning"), ("ct-missing", "error")],
        ids=["ineligible-trait", "unknown-trait"],
    )
    def test_dialog_refuses_trait(self, client, mocker, trait: str, category: str) -> None:
        """Verify the dialog sends the user back for a trait that cannot take specialties."""
        # Given an attribute or an unknown trait
        character = self._setup(client, mocker)

        # When opening its dialog
        response = client.get(self._url(character, "XP", trait), headers={"HX-Request": "true"})

        # Then the user returns to the form with a message
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert [c for c, _ in session_flashes(client)] == [category]

    @pytest.mark.parametrize(
        ("specialty", "route"),
        [
            (None, Routes.CHARACTER_TRAITS_SPECIALTY_ADD),
            ("sp-1", Routes.CHARACTER_TRAITS_SPECIALTY_UPDATE),
        ],
        ids=["add", "rename"],
    )
    @pytest.mark.parametrize("name", ["   ", "ab", "x" * 51], ids=["blank", "short", "long"])
    def test_invalid_name_rejected(
        self, client, mocker, specialty: str | None, route, name: str
    ) -> None:
        """Verify a blank name or one outside 3 to 50 characters warns without calling the API."""
        # Given an ability with a specialty
        character = self._setup(client, mocker)

        # When adding or renaming with an invalid name
        htmx_post(client, self._url(character, "XP", specialty=specialty), {"name": name})

        # Then nothing is sent and the user is warned
        self.fake.assert_not_called(route)
        assert [category for category, _ in session_flashes(client)] == ["warning"]

    def test_dialog_lists_specialties_and_wires_actions(self, client, mocker) -> None:
        """Verify the dialog shows current specialties with rename, remove, and add wired up."""
        # Given an ability with a specialty
        character = self._setup(client, mocker)

        # When opening its dialog
        html = client.get(self._url(character, "XP"), headers={"HX-Request": "true"}).get_data(
            as_text=True
        )

        # Then the specialty is shown, each row renames and removes it, and the add row posts
        item = self._url(character, "XP", specialty="sp-1")
        assert 'value="Knives"' in html
        assert f'hx-delete="{item}"' in html
        assert f'hx-post="{self._url(character, "XP")}"' in html
        # And the rename row submits only its own name input
        row_form = html.split(f'<form hx-post="{item}"')[1].split("</form>")[0]
        assert row_form.count('name="name"') == 1


class TestSpecialty(_Base):
    """Rename and remove endpoint."""

    def test_rename_calls_api(self, client, mocker) -> None:
        """Verify rename sends the new name and clears caches."""
        # Given an ability with a specialty
        character = self._setup(client, mocker)

        # When renaming the specialty
        htmx_post(client, self._url(character, "XP", specialty="sp-1"), {"name": "Daggers"})

        # Then the new name is sent and the stale sheet is dropped
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_SPECIALTY_UPDATE,
            params=self._trait_params(specialty_id="sp-1"),
            json={"name": "Daggers"},
            times=1,
        )
        assert [category for category, _ in session_flashes(client)] == ["success"]
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    def test_remove_calls_api(self, client, mocker) -> None:
        """Verify remove deletes the specialty and clears caches."""
        # Given an ability with a specialty
        character = self._setup(client, mocker)

        # When removing the specialty
        htmx_delete(client, self._url(character, "XP", specialty="sp-1"))

        # Then the delete is sent and the stale sheet is dropped
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_SPECIALTY_DELETE,
            params=self._trait_params(specialty_id="sp-1"),
            times=1,
        )
        assert [category for category, _ in session_flashes(client)] == ["success"]
        self.clear_sheet.assert_called_once_with(character.id)
        self.clear_ctx.assert_called_once()

    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_stale_specialty_flashes_error(self, client, mocker, method: str) -> None:
        """Verify a missing specialty flashes the API detail instead of raising."""
        # Given an API that no longer has the specialty
        character = self._setup(client, mocker)
        for route in (
            Routes.CHARACTER_TRAITS_SPECIALTY_UPDATE,
            Routes.CHARACTER_TRAITS_SPECIALTY_DELETE,
        ):
            self.fake.set_error(route, status_code=404, detail="Specialty not found")

        # When renaming or removing it
        response = getattr(client, method)(
            self._url(character, "XP", specialty="sp-gone"),
            data={"name": "Daggers"} if method == "post" else None,
            headers=self._headers(client),
        )

        # Then the API's reason is flashed and the sheet cache is kept
        assert response.headers["HX-Redirect"] == f"/character/{character.id}/traits/XP"
        assert ("error", "Specialty not found") in session_flashes(client)
        self.clear_sheet.assert_not_called()


class TestSpecialtyUi(_Base):
    """Rendering of the specialty controls on the Manage Traits form."""

    def _form(self, client, mocker, **setup_kwargs) -> tuple[Character, str]:
        character = self._setup(client, mocker, **setup_kwargs)
        response = client.get(f"/character/{character.id}/traits/XP")
        return character, response.get_data(as_text=True)

    def test_eligible_traits_link_to_their_dialog(self, client, mocker) -> None:
        """Verify abilities show their specialties and open their dialog, with or without any."""
        # When the Manage Traits form renders
        character, html = self._form(client, mocker)

        # Then the existing specialty is shown and both rated abilities link to their dialog
        assert "Knives" in html
        assert f'hx-get="{self._url(character, "XP")}"' in html
        assert f'hx-get="{self._url(character, "XP", "ct-insight")}"' in html

    def test_ineligible_traits_have_no_specialty_controls(self, client, mocker) -> None:
        """Verify attributes and zero-dot abilities get no controls."""
        # When the Manage Traits form renders
        character, html = self._form(client, mocker)

        # Then attributes and zero-dot abilities do not link to a dialog
        assert self._url(character, "XP", "ct-tech") not in html
        assert self._url(character, "XP", "ct-str") not in html

    def test_dialog_escapes_names(self, client, mocker) -> None:
        """Verify specialty names are escaped in the dialog inputs."""
        # Given a specialty name containing markup
        evil = '<b>"Edge"</b>'
        character = self._setup(client, mocker, specialty_name=evil)

        # When opening the dialog
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})

        # Then the markup is escaped
        html = response.get_data(as_text=True)
        assert evil not in html
        assert 'value="&lt;b&gt;' in html


class TestRatingBasedSpecialties(_Base):
    """Specialty eligibility under RATING_BASED rules."""

    @pytest.mark.parametrize(
        ("strength_value", "accepted"),
        [(3, False), (4, True)],
        ids=["below-four", "at-four"],
    )
    def test_attribute_needs_four_dots(
        self, client, mocker, strength_value: int, *, accepted: bool
    ) -> None:
        """Verify an attribute takes a specialty only at 4 dots or more."""
        # Given an attribute at the given rating
        character = self._setup(client, mocker, rules="RATING_BASED", strength_value=strength_value)

        # When adding a specialty to it
        htmx_post(client, self._url(character, "XP", "ct-str"), {"name": "Lifting"})

        # Then the add is sent only at 4 dots, and refused with a warning below
        sent = self.fake.requests_for(Routes.CHARACTER_TRAITS_SPECIALTY_ADD)
        assert [r.json for r in sent] == (
            [{"name": "Lifting", "currency": "XP"}] if accepted else []
        )
        assert [c for c, _ in session_flashes(client)] == ["success" if accepted else "warning"]

    @pytest.mark.parametrize("favored", [True, False], ids=["favored", "not-favored"])
    def test_three_dot_ability_needs_concept_favor(self, client, mocker, *, favored: bool) -> None:
        """Verify an ability at 3 dots can take a specialty only when the concept favors it."""
        # Given a 3-dot ability, favored or not by the character's concept
        character = self._setup(client, mocker, rules="RATING_BASED")
        mocker.patch(
            "vweb.lib.character_profile.cache.blueprint.concept",
            return_value=CharacterConceptFactory.build(favored_ability_names=["Melee"])
            if favored
            else None,
        )

        # When opening its dialog
        response = client.get(self._url(character, "XP"), headers={"HX-Request": "true"})

        # Then the dialog opens with the add form only for a favored ability
        html = response.get_data(as_text=True)
        assert (f'hx-post="{self._url(character, "XP")}"' in html) is favored
        assert ("HX-Redirect" in response.headers) is not favored
