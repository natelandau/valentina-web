"""Tests for character trait-edit route permission enforcement."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from vclient.exceptions import ConflictError, ValidationError
from vclient.models import CharacterTraitSpecialty
from vclient.testing import (
    CharacterFactory,
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CompanyFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    TraitFactory,
)

from tests.conftest import get_csrf
from tests.helpers import build_global_context

if TYPE_CHECKING:
    from vclient.models import Character, CharacterFullSheet


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

    def test_post_denied_for_restricted_player_on_npc(self, client, mocker) -> None:
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

        traits_svc = MagicMock()
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
        )
        csrf = get_csrf(client)

        # When submitting a trait change for the NPC
        response = client.post(
            f"/character/{npc.id}/traits/NO_COST",
            data={"some-trait-id": "3", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the user is redirected to the character view and no trait service is used
        assert response.headers.get("HX-Redirect") == f"/character/{npc.id}"
        traits_svc.assert_not_called()

    def test_post_no_cost_denied_without_free_trait_permission(self, client, mocker) -> None:
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

        traits_svc = MagicMock()
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
        )
        csrf = get_csrf(client)

        # When posting a DELETE sentinel on the free-edit form
        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the user is redirected to the character view and nothing is deleted
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}"
        traits_svc.delete.assert_not_called()


class TestCustomTraitCreation:
    """POST /character/<id>/traits/<spend_type> with a CUSTOM_<category> field."""

    def _setup(self, client, mocker) -> tuple[Character, MagicMock]:
        """Wire a PLAYER-owned player character and a mocked traits service.

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

        traits_svc = MagicMock()
        created = MagicMock()
        created.id = "new-trait-1"
        traits_svc.create.return_value = created
        options = MagicMock()
        options.xp_current = 4
        options.starting_points_current = 9
        options.options = {"DELETE": MagicMock(point_change=1)}
        traits_svc.get_value_options.return_value = options
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
        )
        return character, traits_svc

    def _flashes(self, client) -> list[str]:
        """Return the flashed message strings from the session cookie."""
        with client.session_transaction() as sess:
            return [message for _, message in sess.get("_flashes", [])]

    def test_create_custom_trait_xp_sends_currency_and_summary(self, client, mocker) -> None:
        """Verify an XP-mode custom trait sends currency=XP and flashes spent/remaining."""
        # Given a PLAYER editing their own character in XP mode
        character, traits_svc = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait in the "skills" category
        response = client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the trait is created with the XP currency and title-cased name
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/XP"
        sent = traits_svc.create.call_args.args[0]
        assert sent.currency == "XP"
        assert sent.name == "Street Smarts"
        assert sent.category_id == "skills"
        # And the flash reports the amount spent and the remaining balance
        assert any("You spent 1 xp, 4 remaining" in m for m in self._flashes(client))

    def test_create_custom_trait_category_id_with_underscores(self, client, mocker) -> None:
        """Verify a category id containing underscores is parsed intact from the field name."""
        # Given a PLAYER editing their own character
        character, traits_svc = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When the custom-trait field carries an underscore-laden category id
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills_category_id": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then the full category id is sent, not just its first segment
        assert traits_svc.create.call_args.args[0].category_id == "skills_category_id"

    def test_create_custom_trait_starting_points_summary(self, client, mocker) -> None:
        """Verify a STARTING_POINTS custom trait reports the starting-points balance."""
        # Given a PLAYER editing their own character in starting-points mode
        character, traits_svc = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait paid with starting points
        client.post(
            f"/character/{character.id}/traits/STARTING_POINTS",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then STARTING_POINTS is sent and the flash reports the starting-points balance
        assert traits_svc.create.call_args.args[0].currency == "STARTING_POINTS"
        assert any("You spent 1 starting points, 9 remaining" in m for m in self._flashes(client))

    def test_create_custom_trait_no_cost_omits_spend_summary(self, client, mocker) -> None:
        """Verify a NO_COST custom trait sends currency=NO_COST and omits the spend note."""
        # Given a PLAYER editing their own character in free mode
        character, traits_svc = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When adding a custom trait for free
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"CUSTOM_skills": "street smarts"},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then NO_COST is sent, no balance lookup happens, and no spend note appears
        assert traits_svc.create.call_args.args[0].currency == "NO_COST"
        traits_svc.get_value_options.assert_not_called()
        flashes = self._flashes(client)
        assert any("Created Street Smarts." in m for m in flashes)
        assert not any("You spent" in m for m in flashes)

    def test_create_custom_trait_balance_lookup_failure_falls_back(self, client, mocker) -> None:
        """Verify a failed balance lookup still flashes bare success without erroring."""
        # Given the post-create value-options lookup raises
        character, traits_svc = self._setup(client, mocker)
        traits_svc.get_value_options.side_effect = ValidationError("boom")
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
        # Given the create call raises an API error
        character, traits_svc = self._setup(client, mocker)
        traits_svc.create.side_effect = ValidationError("nope")
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
        character, traits_svc = self._setup(client, mocker)
        csrf = get_csrf(client)

        # When submitting a whitespace-only name
        client.post(
            f"/character/{character.id}/traits/XP",
            data={"CUSTOM_skills": "   "},
            headers={"HX-Request": "true", "X-CSRFToken": csrf},
        )

        # Then a warning is flashed and no trait is created
        assert any("Trait name is required" in m for m in self._flashes(client))
        traits_svc.create.assert_not_called()


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

    def _setup(self, mocker) -> tuple[Character, MagicMock]:
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

        traits_svc = MagicMock()
        options = MagicMock()
        options.options = {"DELETE": MagicMock(point_change=1)}
        traits_svc.get_value_options.return_value = options
        traits_svc.delete.return_value = None
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
        )
        return character, traits_svc

    def _flashes(self, client) -> list[str]:
        with client.session_transaction() as sess:
            return [message for _, message in sess.get("_flashes", [])]

    def test_delete_sentinel_deletes_trait_no_cost(self, client, mocker) -> None:
        """Verify a DELETE post removes the trait with NO_COST currency and flashes success."""
        # Given a storyteller on the free-edit form
        character, traits_svc = self._setup(mocker)
        csrf = get_csrf(client)

        # When posting the DELETE sentinel for a trait
        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the character trait is deleted with NO_COST and the form re-renders
        traits_svc.delete.assert_called_once_with("ct-1", currency="NO_COST")
        # Free deletes skip the refund lookup entirely.
        traits_svc.get_value_options.assert_not_called()
        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/NO_COST"
        assert any("Trait deleted." in m for m in self._flashes(client))

    def test_delete_api_error_flashes_error(self, client, mocker) -> None:
        """Verify an API error during delete flashes a failure message and does not raise."""
        # Given the delete call raises an API error
        character, traits_svc = self._setup(mocker)
        traits_svc.delete.side_effect = ValidationError("boom")
        csrf = get_csrf(client)

        # When posting the DELETE sentinel
        client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "DELETE", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        # Then the failure message is flashed
        assert any("Failed to delete trait" in m for m in self._flashes(client))


class TestChangeValuePost:
    """POST of a value change on the free-edit form."""

    def _setup(self, mocker) -> tuple[Character, MagicMock]:
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

        traits_svc = MagicMock()
        options = MagicMock()
        options.name = "strength"
        options.options = {
            "2": MagicMock(
                direction="increase", point_change=0, can_use_xp=True, can_use_starting_points=True
            )
        }
        traits_svc.get_value_options.return_value = options
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
        )
        return character, traits_svc

    def test_change_value_conflict_flashes_and_redirects(self, client, mocker) -> None:
        """Verify a concurrent-change conflict flashes the API detail and reloads the form."""
        character, traits_svc = self._setup(mocker)
        traits_svc.change_value.side_effect = ConflictError(
            "Conflict",
            status_code=409,
            response_data={
                "detail": "This trait was changed by another request. Reload it and try again."
            },
        )
        csrf = get_csrf(client)

        response = client.post(
            f"/character/{character.id}/traits/NO_COST",
            data={"ct-1": "2", "csrf_token": csrf},
            headers={"HX-Request": "true"},
        )

        assert response.headers.get("HX-Redirect") == f"/character/{character.id}/traits/NO_COST"
        with client.session_transaction() as sess:
            flashes = [message for _, message in sess.get("_flashes", [])]
        assert any("changed by another request" in m for m in flashes)

    def test_change_value_clears_sheet_cache(self, client, mocker) -> None:
        """Verify a value change drops the cached sheet so derived traits reload."""
        character, _ = self._setup(mocker)
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

    def _setup(self, mocker, names: tuple[str, ...] = ("Knives", "Swords")) -> Character:
        ctx = build_global_context(user_role="STORYTELLER")
        character = CharacterFactory.build(
            id="pc-1", campaign_id=ctx.campaigns[0].id, type="PLAYER", user_player_id="owner-1"
        )
        ctx.characters = [character]
        mocker.patch("vweb.lib.cache.global_context.load", return_value=ctx)
        melee = CharacterTraitFactory.build(
            id="ct-melee",
            value=3,
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
        traits_svc = MagicMock()
        options = MagicMock()
        options.name = "melee"
        options.options = {
            "0": MagicMock(
                direction="decrease", point_change=0, can_use_xp=True, can_use_starting_points=True
            )
        }
        traits_svc.get_value_options.return_value = options
        mocker.patch(
            "vweb.routes.character_trait_edit.views.sync_character_traits_service",
            return_value=traits_svc,
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

    def test_non_zero_change_skips_specialty_lookup(self, client, mocker) -> None:
        """Verify a non-zero value change does not read the cached sheet."""
        character = self._setup(mocker)
        sheet_get = mocker.patch("vweb.routes.character_trait_edit.views.cache.character_sheet.get")
        self._post(client, character, "ct-melee", "2")
        sheet_get.assert_not_called()

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
