"""Tests for character trait-edit route permission enforcement."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from tests.conftest import get_csrf
from tests.helpers import build_global_context
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models import CharacterTraitSpecialty
from vweb.api_client.models.character_trait import CharacterTraitValueOption
from vweb.api_client.testing import (
    CharacterConceptFactory,
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CharacterTraitValueOptionsResponseFactory,
    CompanyFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    Routes,
    TraitFactory,
)

if TYPE_CHECKING:
    from vweb.api_client.constants import SpecialtyRules
    from vweb.api_client.models import (
        Character,
        CharacterFullSheet,
        CharacterTraitValueOptionsResponse,
    )
    from vweb.api_client.testing import FakeVClient


class _Currency(BaseModel):
    currency: Literal["NO_COST", "XP"]


def _value_options(
    name: str = "strength",
    *,
    xp_current: int = 0,
    starting_points_current: int = 0,
    **options: tuple[str, int],
) -> CharacterTraitValueOptionsResponse:
    """Build a value-options response whose options map a value to (direction, point_change)."""
    return CharacterTraitValueOptionsResponseFactory.build(
        name=name,
        xp_current=xp_current,
        starting_points_current=starting_points_current,
        options={
            value: CharacterTraitValueOption(
                direction=direction,
                point_change=point_change,
                can_use_xp=True,
                xp_after=0,
                can_use_starting_points=True,
                starting_points_after=0,
            )
            for value, (direction, point_change) in options.items()
        },
    )


def _trait_params(character_trait_id: str = "ct-1") -> dict[str, str]:
    """Return the path params of a request about one of pc-1's traits."""
    return {
        "company_id": "test-company-id",
        "character_id": "pc-1",
        "character_trait_id": character_trait_id,
    }


def _one_trait_sheet(character: Character) -> CharacterFullSheet:
    """Build a deterministic full sheet with a single Strength trait (ct-1)."""
    trait = TraitFactory.build(id="t-str", name="strength", min_value=0, max_value=5)
    character_trait = CharacterTraitFactory.build(id="ct-1", value=3, trait=trait)
    category = FullSheetTraitCategoryFactory.build(
        character_traits=[character_trait],
        subcategories=[],
        available_traits=[],
    )
    section = FullSheetTraitSectionFactory.build(categories=[category])
    return CharacterFullSheetFactory.build(character=character, sections=[section])


class TestCharacterTraitsViewPermissions:
    """Permission enforcement for POST /character/<id>/traits/<spend_type>."""

    def test_post_denied_for_restricted_player_on_npc(self, client, mocker, fake_vclient) -> None:
        """Verify a restricted player cannot mutate an NPC's traits via a crafted POST."""
        # Given a PLAYER and an NPC under the default storyteller-only NPC setting
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        npc = CharacterFactory.build(
            id="npc-1",
            campaign_id=campaign.id,
            type="NPC",
            user_player_id=None,
        )
        ctx.characters = [npc]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        csrf = get_csrf(client)

        # When submitting a trait change for the NPC
        response = client.post(
            f"/character/{npc.id}/traits/NO_COST",
            data={"some-trait-id": "3", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the user is redirected to the character view and nothing reaches the API
        assert response.headers.get("HX-Redirect") == f"/character/{npc.id}"
        assert fake_vclient.requests == []

    def test_get_free_edit_npc_denied_for_restricted_player(self, client, mocker) -> None:
        """Verify the free-edit page still refuses a player who cannot manage NPCs."""
        # Given a PLAYER, an NPC, and the default storyteller-only NPC and free-edit settings
        ctx = build_global_context(user_role="PLAYER")
        npc = CharacterFactory.build(
            id="npc-1", campaign_id=ctx.campaigns[0].id, type="NPC", user_player_id=None
        )
        ctx.characters = [npc]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        # When opening the free-edit page for the NPC
        response = client.get(f"/character/{npc.id}/traits/NO_COST")

        # Then the user is sent to the character view with the character-level refusal
        assert response.status_code == 302
        with client.session_transaction() as sess:
            flashes = [message for _, message in sess.get("_flashes", [])]
        assert flashes == ["You are not authorized to update this character"]

    def test_post_no_cost_denied_without_free_trait_permission(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a player without free-trait permission cannot delete via the free-edit POST."""
        # Given a PLAYER who owns their character but the company restricts free edits
        ctx = build_global_context(user_role="PLAYER")
        campaign = ctx.campaigns[0]
        character = CharacterFactory.build(
            id="pc-1",
            campaign_id=campaign.id,
            type="PLAYER",
            user_player_id="test-user-id",
        )
        # Default test company setting is permission_free_trait_changes="STORYTELLER"
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        csrf = get_csrf(client)

        # When posting a DELETE sentinel on the free-edit form
        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the user is redirected to the character view and nothing is deleted
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}"
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_DELETE)


class TestCustomTraitCreation:
    """POST /character/<id>/traits/<spend_type> with a CUSTOM_<category> field."""

    @pytest.fixture(autouse=True)
    def _fake(self, fake_vclient) -> None:
        self.fake = fake_vclient

    def _setup(self, client, mocker) -> Character:
        """Wire a PLAYER-owned player character and the API's create and balance responses.

        `conftest.py` monkeypatches `CompanyFactory.build` to set
        `permission_free_trait_changes="STORYTELLER"` by default, which denies
        free trait changes to players. Pin `UNRESTRICTED` here so the PLAYER
        can pass the `can_edit_traits_free` guard and exercise the NO_COST
        custom-trait flow; `TestCharacterTraitsViewPermissions` covers the
        guard itself.
        """
        # conftest hands each company its own settings copy, so mutating one
        # field here cannot leak into other tests.
        company = CompanyFactory.build(name="Test Company")
        company.settings.permission_free_trait_changes = "UNRESTRICTED"
        ctx = build_global_context(user_role="PLAYER", company=company)
        campaign = ctx.campaigns[0]
        character = CharacterFactory.build(
            id="pc-1",
            campaign_id=campaign.id,
            type="PLAYER",
            user_player_id="test-user-id",
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        self.fake.set_response(
            Routes.CHARACTER_TRAITS_CREATE, model=CharacterTraitFactory.build(id="new-trait-1")
        )
        self.fake.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            model=_value_options(xp_current=4, starting_points_current=9, DELETE=("decrease", 1)),
            params={"character_trait_id": "new-trait-1"},
        )
        self.blueprint_traits = mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.blueprint.traits", return_value={}
        )
        self.sheet_get = mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(character=character, sections=[]),
        )
        return character

    def _flashes(self, client) -> list[str]:
        """Return the flashed message strings from the session cookie."""
        with client.session_transaction() as sess:
            return [message for _, message in sess.get("_flashes", [])]

    def test_create_custom_trait_xp_sends_currency_and_summary(self, client, mocker) -> None:
        """Verify an XP-mode custom trait sends currency=XP and flashes spent/remaining."""
        # Given a PLAYER editing their own character in XP mode
        character = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait in the "skills" category
        response = client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the trait is created with the XP currency and title-cased name
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/XP"
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE,
            params={"company_id": "test-company-id", "character_id": "pc-1"},
            json={
                "name": "Street Smarts",
                "show_when_zero": True,
                "category_id": "skills",
                "currency": "XP",
            },
            times=1,
        )
        # And the sheet is not fetched when no standard trait shares the name
        self.sheet_get.assert_not_called()
        # And the flash reports the amount spent and the remaining balance
        assert any("You spent 1 xp, 4 remaining" in m for m in self._flashes(client))

    def test_create_custom_trait_category_id_with_underscores(self, client, mocker) -> None:
        """Verify a category id containing underscores is parsed intact from the field name."""
        # Given a PLAYER editing their own character
        character = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When the custom-trait field carries an underscore-laden category id
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills_category_id": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the full category id is sent, not just its first segment
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE, json_subset={"category_id": "skills_category_id"}
        )

    def test_create_custom_trait_starting_points_summary(self, client, mocker) -> None:
        """Verify a STARTING_POINTS custom trait reports the starting-points balance."""
        # Given a PLAYER editing their own character in starting-points mode
        character = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait paid with starting points
        client.post(
            f"/character/{character.id}/traits/STARTING_POINTS",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then STARTING_POINTS is sent and the flash reports the starting-points balance
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE, json_subset={"currency": "STARTING_POINTS"}, times=1
        )
        assert any("You spent 1 starting points, 9 remaining" in m for m in self._flashes(client))

    def test_create_custom_trait_no_cost_omits_spend_summary(self, client, mocker) -> None:
        """Verify a NO_COST custom trait sends currency=NO_COST and omits the spend note."""
        # Given a PLAYER editing their own character in free mode
        character = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait for free
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then NO_COST is sent, no balance lookup happens, and no spend note appears
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE, json_subset={"currency": "NO_COST"}, times=1
        )
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_OPTIONS)
        flashes = self._flashes(client)
        assert any("Created Street Smarts." in m for m in flashes)
        assert not any("You spent" in m for m in flashes)

    def test_create_custom_trait_balance_lookup_failure_falls_back(self, client, mocker) -> None:
        """Verify a failed balance lookup still flashes bare success without erroring."""
        # Given the post-create value-options lookup raises
        character = self._setup(client, mocker)
        self.fake.set_error(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            status_code=400,
            params={"character_trait_id": "new-trait-1"},
        )
        csrf = get_csrf(client)

        # When adding a custom trait in XP mode
        response = client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the request still succeeds with the bare "Created" message
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/XP"
        flashes = self._flashes(client)
        assert any("Created Street Smarts." in m for m in flashes)
        assert not any("You spent" in m for m in flashes)

    def test_create_custom_trait_api_error_flashes_error(self, client, mocker) -> None:
        """Verify an API error during create flashes an error and does not raise."""
        # Given the create call fails with no reason a user could read
        character = self._setup(client, mocker)
        self.fake.set_error(Routes.CHARACTER_TRAITS_CREATE, status_code=400, detail="")
        csrf = get_csrf(client)

        # When adding a custom trait
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the failure message is flashed
        assert any("Failed to create custom trait" in m for m in self._flashes(client))

    def test_create_custom_trait_empty_name_warns(self, client, mocker) -> None:
        """Verify a blank custom-trait name warns and never calls the service."""
        # Given a PLAYER editing their own character
        character = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When submitting a whitespace-only name
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "   "},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then a warning is flashed and no trait is created
        assert any("Trait name is required" in m for m in self._flashes(client))
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_CREATE)

    def test_custom_name_matching_standard_trait_assigns_it(self, client, mocker) -> None:
        """Verify a typed name matching a standard trait in the category assigns that trait."""
        # Given a standard trait in the category that the character's dropdown leaves out
        character = self._setup(client, mocker)
        standard = TraitFactory.build(
            id="ling-v4",
            name="Linguistics",
            category_id="skills",
            custom_for_character_id=None,
            game_versions=["V4"],
            min_value=0,
        )
        self.blueprint_traits.return_value = {standard.id: standard}
        csrf = get_csrf(client)

        # When typing that name in the custom box
        response = client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "linguistics"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the standard trait is assigned instead of creating a custom one
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/XP"
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_ASSIGN,
            params={"character_id": "pc-1"},
            json={"trait_id": "ling-v4", "value": 0, "currency": "XP"},
            times=1,
        )
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_CREATE)
        assert any("Assigned Linguistics" in m for m in self._flashes(client))

    def test_custom_name_matching_other_category_assigns_it(self, client, mocker) -> None:
        """Verify a name matching a trait in another category assigns that trait."""
        # Given a same-named standard trait in a different category
        character = self._setup(client, mocker)
        merit = TraitFactory.build(
            id="merit-1", name="Street Smarts", category_id="merits", custom_for_character_id=None
        )
        self.blueprint_traits.return_value = {merit.id: merit}
        csrf = get_csrf(client)

        # When typing that name in the skills box
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the existing trait is assigned and no custom trait is created
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_ASSIGN, json_subset={"trait_id": "merit-1"}, times=1
        )
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_CREATE)

    def test_custom_name_already_on_character_does_not_assign(self, client, mocker) -> None:
        """Verify a name already on the sheet goes to create instead of assigning a duplicate."""
        # Given a character that already has Linguistics, and another same-named standard trait
        character = self._setup(client, mocker)
        owned = CharacterTraitFactory.build(trait=TraitFactory.build(name="Linguistics"))
        category = FullSheetTraitCategoryFactory.build(
            character_traits=[owned], subcategories=[], available_traits=[]
        )
        section = FullSheetTraitSectionFactory.build(categories=[category])
        self.sheet_get.return_value = CharacterFullSheetFactory.build(
            character=character, sections=[section]
        )
        other = TraitFactory.build(
            id="ling-other", name="Linguistics", category_id="skills", custom_for_character_id=None
        )
        self.blueprint_traits.return_value = {other.id: other}
        self.fake.set_error(
            Routes.CHARACTER_TRAITS_CREATE,
            status_code=409,
            detail="Trait named 'Linguistics' already exists",
        )
        csrf = get_csrf(client)

        # When typing that name in the custom box
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "linguistics"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then no second trait is assigned and the create conflict is shown
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_ASSIGN)
        self.fake.assert_called(Routes.CHARACTER_TRAITS_CREATE, times=1)


class TestTraitDeleteRendering:
    """The free-edit form renders a delete button + modal; paid forms do not."""

    def _setup(self, mocker, character: Character) -> None:
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        character.campaign_id = campaign.id
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=_one_trait_sheet(character),
        )

    def test_no_cost_form_renders_delete_button_and_modal(self, client, mocker) -> None:
        """Verify the NO_COST form shows a right-aligned red trash button and the modal."""
        # Given a storyteller viewing the free-edit form for a player character
        character = CharacterFactory.build(id="pc-1", type="PLAYER", user_player_id="test-user-id")
        self._setup(mocker, character)

        # When the free-edit form is requested
        html = client.get(f"/character/{character.id}/traits/NO_COST").get_data(as_text=True)

        # Then the shared confirmation modal and a trash button for ct-1 are present
        assert 'id="trait-delete-modal"' in html
        assert 'id="trait-delete-confirm"' in html
        assert 'data-trait-id="ct-1"' in html
        assert "fa-trash" in html
        # And the trash button sits to the right of the value buttons (later in the row markup)
        assert html.index('data-trait-id="ct-1"') > html.index('value="1"')

    def test_starting_points_form_has_no_delete_button_or_modal(self, client, mocker) -> None:
        """Verify a paid form renders neither the delete button nor the modal."""
        # Given a storyteller viewing the starting-points form
        character = CharacterFactory.build(id="pc-1", type="PLAYER", user_player_id="test-user-id")
        self._setup(mocker, character)

        # When the starting-points form is requested
        html = client.get(f"/character/{character.id}/traits/STARTING_POINTS").get_data(
            as_text=True
        )

        # Then no delete affordance is present
        assert 'id="trait-delete-modal"' not in html
        assert 'data-trait-id="ct-1"' not in html


class TestDerivedWillpower:
    """V5 Willpower is derived server-side and must not be editable."""

    def _render(self, client, mocker, game_version: str) -> str:
        ctx = build_global_context(user_role="STORYTELLER")
        character = CharacterFactory.build(
            id="pc-1",
            type="PLAYER",
            user_player_id="test-user-id",
            game_version=game_version,
            campaign_id=ctx.campaigns[0].id,
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        trait = TraitFactory.build(
            id="t-wp", name="Willpower", min_value=0, max_value=10, custom_for_character_id=None
        )
        character_trait = CharacterTraitFactory.build(id="ct-wp", value=4, trait=trait)
        category = FullSheetTraitCategoryFactory.build(
            character_traits=[character_trait], subcategories=[], available_traits=[]
        )
        section = FullSheetTraitSectionFactory.build(categories=[category])
        sheet = CharacterFullSheetFactory.build(character=character, sections=[section])
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=sheet,
        )
        return client.get(f"/character/{character.id}/traits/NO_COST").get_data(as_text=True)

    def test_v5_willpower_has_no_value_or_delete_controls(self, client, mocker) -> None:
        """Verify V5 Willpower shows its value without value or delete buttons."""
        html = self._render(client, mocker, "V5")

        assert 'name="ct-wp"' not in html
        assert 'data-trait-id="ct-wp"' not in html
        assert re.search(r"btn-active[^>]*disabled>4</button>", html)

    def test_v4_willpower_keeps_controls(self, client, mocker) -> None:
        """Verify V4 Willpower stays editable."""
        html = self._render(client, mocker, "V4")

        assert 'name="ct-wp"' in html


class TestTraitDeletePost:
    """POST of the DELETE sentinel on the free-edit form."""

    def _setup(self, mocker, fake_vclient: FakeVClient) -> Character:
        ctx = build_global_context(user_role="STORYTELLER")
        campaign = ctx.campaigns[0]
        character = CharacterFactory.build(
            id="pc-1", campaign_id=campaign.id, type="PLAYER", user_player_id="owner-1"
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=_one_trait_sheet(character),
        )

        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, model=_value_options(DELETE=("decrease", 1))
        )
        return character

    def _flashes(self, client) -> list[str]:
        with client.session_transaction() as sess:
            return [message for _, message in sess.get("_flashes", [])]

    def test_delete_sentinel_deletes_trait_no_cost(self, client, mocker, fake_vclient) -> None:
        """Verify a DELETE post removes the trait with NO_COST currency and flashes success."""
        # Given a storyteller on the free-edit form
        character = self._setup(mocker, fake_vclient)
        csrf = get_csrf(client)

        # When posting the DELETE sentinel for a trait
        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the character trait is deleted with NO_COST and the form re-renders
        fake_vclient.assert_called(
            Routes.CHARACTER_TRAITS_DELETE,
            params=_trait_params(),
            query={"currency": "NO_COST"},
            times=1,
        )
        # Free deletes skip the refund lookup entirely.
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_OPTIONS)
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/NO_COST"
        assert any("Trait deleted." in m for m in self._flashes(client))

    def test_delete_api_error_flashes_error(self, client, mocker, fake_vclient) -> None:
        """Verify an API error during delete flashes a failure message and does not raise."""
        # Given the delete call fails with no reason a user could read
        character = self._setup(mocker, fake_vclient)
        fake_vclient.set_error(Routes.CHARACTER_TRAITS_DELETE, status_code=400, detail="")
        csrf = get_csrf(client)

        # When posting the DELETE sentinel
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the failure message is flashed
        assert any("Failed to delete trait" in m for m in self._flashes(client))

    def test_delete_forbidden_flashes_api_detail(self, client, mocker, fake_vclient) -> None:
        """Verify a 403 on free delete flashes the API's own reason."""
        # Given the API refuses the free delete
        character = self._setup(mocker, fake_vclient)
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_DELETE,
            status_code=403,
            detail="Free trait changes are restricted",
        )
        csrf = get_csrf(client)

        # When posting the DELETE sentinel
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the flash carries the API detail
        assert any("Free trait changes are restricted" in m for m in self._flashes(client))

    def test_delete_request_validation_error_flashes_readable_text(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a client-side validation failure on delete flashes its message."""
        # Given the client rejects the request before it is sent, which the fake API cannot
        # produce because the route only accepts valid currencies
        character = self._setup(mocker, fake_vclient)
        with pytest.raises(PydanticValidationError) as info:
            _Currency(currency="BOGUS")
        traits_svc = mocker.patch(
            "vweb.routes.character_trait_edit.views.api_services.character_traits"
        ).return_value
        traits_svc.delete.side_effect = RequestValidationError(info.value)
        csrf = get_csrf(client)

        # When posting the DELETE sentinel
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the flash names the failing field instead of only the generic failure
        flashes = self._flashes(client)
        assert any("Currency" in m for m in flashes)


class TestChangeValuePost:
    """POST of a value change on the free-edit form."""

    def _setup(self, mocker, fake_vclient: FakeVClient) -> Character:
        ctx = build_global_context(user_role="STORYTELLER")
        character = CharacterFactory.build(
            id="pc-1", campaign_id=ctx.campaigns[0].id, type="PLAYER", user_player_id="owner-1"
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)

        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=_one_trait_sheet(character),
        )

        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            model=_value_options("strength", **{"2": ("increase", 0)}),
        )
        return character

    def test_change_value_conflict_flashes_and_redirects(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a concurrent-change conflict flashes the API detail and reloads the form."""
        character = self._setup(mocker, fake_vclient)
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_VALUE_UPDATE,
            status_code=409,
            detail="This trait was changed by another request. Reload it and try again.",
        )
        csrf = get_csrf(client)

        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "2", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        fake_vclient.assert_called(
            Routes.CHARACTER_TRAITS_VALUE_UPDATE,
            params=_trait_params(),
            json={"target_value": 2, "currency": "NO_COST"},
            times=1,
        )
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/NO_COST"
        with client.session_transaction() as sess:
            flashes = [message for _, message in sess.get("_flashes", [])]
        assert any("changed by another request" in m for m in flashes)

    def test_change_value_on_missing_trait_flashes_and_redirects(
        self, client, mocker, fake_vclient
    ) -> None:
        """Verify a trait deleted elsewhere flashes the API detail instead of failing."""
        # Given a trait the API no longer has
        character = self._setup(mocker, fake_vclient)
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, status_code=404, detail="Trait not found"
        )
        csrf = get_csrf(client)

        # When changing its value
        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "2", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the form reloads with the API's message
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/NO_COST"
        with client.session_transaction() as sess:
            flashes = list(sess.get("_flashes", []))
        assert ("error", "Trait not found") in flashes
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_UPDATE)

    def test_change_value_clears_sheet_cache(self, client, mocker, fake_vclient) -> None:
        """Verify a value change drops the cached sheet so derived traits reload."""
        character = self._setup(mocker, fake_vclient)
        clear = mocker.patch("vweb.routes.character_trait_edit.views.cache.character_sheet.clear")
        csrf = get_csrf(client)

        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "2", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        clear.assert_called_once_with(character.id)


def _specialty(specialty_id: str, name: str) -> CharacterTraitSpecialty:
    return CharacterTraitSpecialty(
        id=specialty_id,
        name=name,
        date_created="2026-01-01T00:00:00Z",
        date_modified="2026-01-01T00:00:00Z",
    )


class TestSpecialtyLossWarnings:
    """Confirmations and flashes for changes that remove an ability's specialties."""

    @pytest.fixture(autouse=True)
    def _fake(self, fake_vclient) -> None:
        self.fake = fake_vclient

    def _setup(
        self,
        mocker,
        names: tuple[str, ...] = ("Knives", "Swords"),
        *,
        rules: SpecialtyRules = "FIXED_COST",
        melee_value: int = 3,
    ) -> Character:
        ctx = build_global_context(user_role="STORYTELLER")
        ctx.company.settings.specialty_rules = rules
        character = CharacterFactory.build(
            id="pc-1", campaign_id=ctx.campaigns[0].id, type="PLAYER", user_player_id="owner-1"
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        melee = CharacterTraitFactory.build(
            id="ct-melee",
            value=melee_value,
            trait=TraitFactory.build(name="melee", sheet_section_name="Abilities", max_value=5),
            specialties=[_specialty(f"sp-{i}", name) for i, name in enumerate(names)],
        )
        strength = CharacterTraitFactory.build(
            id="ct-str",
            value=3,
            trait=TraitFactory.build(name="strength", sheet_section_name="Attributes", max_value=5),
            specialties=[],
        )
        category = FullSheetTraitCategoryFactory.build(
            character_traits=[melee, strength], subcategories=[], available_traits=[]
        )
        section = FullSheetTraitSectionFactory.build(categories=[category])
        sheet = CharacterFullSheetFactory.build(character=character, sections=[section])
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get", return_value=sheet
        )
        mocker.patch("vweb.lib.cache.character_sheet.clear")
        self.fake.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            model=_value_options("melee", **{"0": ("decrease", 0), "3": ("decrease", 0)}),
        )
        return character

    def _html(self, client, character) -> str:
        return client.get(f"/character/{character.id}/traits/NO_COST").get_data(as_text=True)

    def _post(self, client, character, field: str, value: str) -> list[str]:
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={field: value, "csrf_token": get_csrf(client)},
            headers={"HX-Request": "true"},
        )
        with client.session_transaction() as sess:
            return [message for _, message in sess.get("_flashes", [])]

    @staticmethod
    def _zero_button(html: str, trait_id: str) -> str:
        return re.search(rf'<button[^>]*name="{trait_id}"\s+value="0"[^>]*>', html).group(0)

    def test_zero_button_confirms_when_trait_has_specialties(self, client, mocker) -> None:
        """Verify the 0 button asks for confirmation naming the specialties."""
        character = self._setup(mocker)
        button = self._zero_button(self._html(client, character), "ct-melee")
        assert 'hx-confirm="Lowering Melee to 0 removes its specialties: Knives, Swords."' in button

    def test_delete_modal_specialty_line_is_hidden_when_empty_and_ends_with_period(
        self, client, mocker
    ) -> None:
        """Verify the modal line collapses when empty and the handler text ends in a period."""
        character = self._setup(mocker)
        html = self._html(client, character)
        assert 'id="trait-delete-specialties" class="pb-4 -mt-2 empty:hidden"' in html
        assert "this.dataset.traitSpecialties + '.'" in html

    @staticmethod
    def _value_button(html: str, trait_id: str, value: int) -> str:
        return re.search(rf'<button[^>]*name="{trait_id}"\s+value="{value}"[^>]*>', html).group(0)

    def test_rating_based_confirms_below_minimum(self, client, mocker) -> None:
        """Verify RATING_BASED rules confirm any drop below 4 dots, not only a drop to 0."""
        character = self._setup(mocker, rules="RATING_BASED", melee_value=5)
        html = self._html(client, character)
        below = self._value_button(html, "ct-melee", 3)
        assert 'hx-confirm="Lowering Melee to 3 removes its specialties: Knives, Swords."' in below
        assert "hx-confirm" not in self._value_button(html, "ct-melee", 4)

    def test_rating_based_favored_ability_confirms_below_three(self, client, mocker) -> None:
        """Verify an ability the concept favors keeps its specialties at 3 dots."""
        character = self._setup(mocker, rules="RATING_BASED", melee_value=5)
        mocker.patch(
            "vweb.lib.character_profile.cache.blueprint.concept",
            return_value=CharacterConceptFactory.build(favored_ability_names=["Melee"]),
        )
        html = self._html(client, character)
        assert "hx-confirm" not in self._value_button(html, "ct-melee", 3)
        assert "hx-confirm" in self._value_button(html, "ct-melee", 2)

    def test_rating_based_drop_below_minimum_flash_mentions_specialties(
        self, client, mocker
    ) -> None:
        """Verify lowering below the RATING_BASED minimum appends the specialties note."""
        character = self._setup(mocker, rules="RATING_BASED", melee_value=5)
        flashes = self._post(client, character, "ct-melee", "3")
        assert any(m.endswith(" Its specialties were removed.") for m in flashes)

    def test_fixed_cost_drop_above_zero_flash_omits_specialties(self, client, mocker) -> None:
        """Verify FIXED_COST rules keep specialties on any rated ability."""
        character = self._setup(mocker)
        flashes = self._post(client, character, "ct-melee", "3")
        assert not any("specialties" in m for m in flashes)

    def test_zero_change_looks_up_warm_sheet_key(self, client, mocker) -> None:
        """Verify a zero change reads the include_available_traits=True cache entry."""
        character = self._setup(mocker)
        sheet_get = mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=_one_trait_sheet(character),
        )
        self._post(client, character, "ct-melee", "0")
        assert sheet_get.call_args.kwargs == {"include_available_traits": True}

    def test_zero_button_has_no_confirm_without_specialties(self, client, mocker) -> None:
        """Verify the 0 button has no confirmation for a trait without specialties."""
        character = self._setup(mocker)
        button = self._zero_button(self._html(client, character), "ct-str")
        assert "hx-confirm" not in button

    def test_delete_trigger_carries_specialty_names(self, client, mocker) -> None:
        """Verify the trash button carries the names and the modal has the target line."""
        character = self._setup(mocker)
        html = self._html(client, character)
        assert 'data-trait-specialties="Knives, Swords"' in html
        assert 'id="trait-delete-specialties"' in html

    def test_confirm_escapes_names(self, client, mocker) -> None:
        """Verify specialty names are HTML-escaped in both attributes."""
        evil = '<b>"Edge"</b>'
        character = self._setup(mocker, names=(evil,))
        html = self._html(client, character)
        assert evil not in html
        escaped = "&lt;b&gt;&#34;Edge&#34;&lt;/b&gt;"
        button = self._zero_button(html, "ct-melee")
        assert escaped in button
        assert f'data-trait-specialties="{escaped}"' in html

    def test_drop_to_zero_flash_mentions_specialties(self, client, mocker) -> None:
        """Verify lowering to zero appends the specialties note."""
        character = self._setup(mocker)
        flashes = self._post(client, character, "ct-melee", "0")
        assert any(m.endswith(" Its specialties were removed.") for m in flashes)

    def test_delete_flash_mentions_specialties(self, client, mocker) -> None:
        """Verify deleting appends the specialties note."""
        character = self._setup(mocker)
        flashes = self._post(client, character, "ct-melee", "DELETE")
        assert any("Trait deleted." in m and "Its specialties were removed." in m for m in flashes)

    def test_drop_without_specialties_flash_unchanged(self, client, mocker) -> None:
        """Verify no note when the trait had no specialties."""
        character = self._setup(mocker)
        flashes = self._post(client, character, "ct-str", "0")
        assert flashes
        assert not any("specialties" in m for m in flashes)
