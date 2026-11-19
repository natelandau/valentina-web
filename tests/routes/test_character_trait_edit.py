"""Tests for character trait-edit route permission enforcement."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from tests.conftest import get_csrf, htmx_post
from tests.helpers import (
    assert_redirects_to,
    build_global_context,
    build_specialty,
    session_flashes,
)
from vweb.api_client.exceptions import RequestValidationError
from vweb.api_client.models.character_trait import CharacterTraitValueOption
from vweb.api_client.testing import (
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
    from collections.abc import Callable

    from flask.testing import FlaskClient, TestResponse

    from vweb.api_client.constants import SpecialtyRules
    from vweb.api_client.models import (
        Character,
        CharacterFullSheet,
        CharacterTraitValueOptionsResponse,
    )


class _Currency(BaseModel):
    currency: Literal["NO_COST", "XP"]


def _value_options(
    name: str = "strength",
    *,
    xp_current: int = 0,
    starting_points_current: int = 0,
    affordable: bool = True,
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
                can_use_xp=affordable,
                xp_after=0,
                can_use_starting_points=affordable,
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


@pytest.fixture
def use_character(mocker, use_context) -> Callable[..., Character]:
    """Return a function that puts pc-1 in the global context and serves a one-trait sheet."""

    def _use(
        *,
        role: str = "STORYTELLER",
        character_type: str = "PLAYER",
        owner_id: str | None = "owner-1",
        free_changes: Literal["UNRESTRICTED", "WITHIN_24_HOURS", "STORYTELLER"] = "STORYTELLER",
    ) -> Character:
        company = CompanyFactory.build(name="Test Company")
        company.settings.permission_free_trait_changes = free_changes
        ctx = build_global_context(user_role=role, company=company)
        character = CharacterFactory.build(
            id="pc-1",
            campaign_id=ctx.campaigns[0].id,
            type=character_type,
            user_player_id=owner_id,
        )
        ctx.characters = [character]
        use_context(ctx)
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=_one_trait_sheet(character),
        )
        return character

    return _use


def _post(
    client: FlaskClient, spend: str, data: dict[str, str], character_id: str = "pc-1"
) -> TestResponse:
    return htmx_post(client, f"/character/{character_id}/traits/{spend}", data)


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


_DENIED = [
    pytest.param(
        {"role": "PLAYER", "character_type": "NPC", "owner_id": None},
        "NO_COST",
        id="restricted-player-on-npc",
    ),
    pytest.param(
        {"role": "PLAYER", "owner_id": "test-user-id"},
        "NO_COST",
        id="own-character-without-free-edit-permission",
    ),
    pytest.param(
        {"role": "PLAYER", "owner_id": "someone-else"},
        "XP",
        id="other-players-character",
    ),
]


class TestCharacterTraitsViewPermissions:
    """Permission enforcement for /character/<id>/traits/<spend_type>."""

    @pytest.mark.parametrize(("setup", "spend"), _DENIED)
    def test_post_denied(self, client, use_character, fake_vclient, setup, spend) -> None:
        """Verify a user who may not edit this way cannot change traits with a crafted POST."""
        # Given a character the user may not change this way
        use_character(**setup)

        # When submitting a trait change and a delete
        response = _post(client, spend, {"ct-1": "DELETE"})

        # Then the user is sent to the character view and nothing reaches the API
        assert response.headers.get("HX-Redirect") == "/character/pc-1"
        assert fake_vclient.requests == []

    @pytest.mark.parametrize(("setup", "spend"), _DENIED)
    def test_get_denied(self, client, use_character, setup, spend) -> None:
        """Verify the edit page refuses a user who may not edit this way."""
        # Given a character the user may not change this way
        use_character(**setup)

        # When opening the edit page
        response = client.get(f"/character/pc-1/traits/{spend}")

        # Then the user is sent to the character view with an error
        assert_redirects_to(response, "/character/pc-1")
        assert [category for category, _ in session_flashes(client)] == ["error"]

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_unknown_character_redirects_home(
        self, client, use_character, fake_vclient, method
    ) -> None:
        """Verify a character outside the user's context sends them home."""
        # Given a character the user cannot see
        use_character()

        # When opening or posting its edit page
        response = getattr(client, method)(
            "/character/missing/traits/XP",
            headers={"HX-Request": "true", "X-CSRFToken": get_csrf(client)},
        )

        # Then the user is sent home and nothing reaches the API
        assert response.headers.get("HX-Redirect") == "/"
        assert fake_vclient.requests == []

    def test_owner_opens_xp_page(self, client, use_character) -> None:
        """Verify a player can open the XP page for their own character."""
        # Given a player's own character
        use_character(role="PLAYER", owner_id="test-user-id")

        # When opening the XP edit page
        response = client.get("/character/pc-1/traits/XP")

        # Then the form renders and posts back to the XP endpoint
        assert response.status_code == 200
        assert "/character/pc-1/traits/XP" in response.get_data(as_text=True)

    def test_xp_page_for_character_without_player_redirects(self, client, use_character) -> None:
        """Verify the XP page refuses a character with no player to spend XP from."""
        # Given an NPC with no player
        use_character(character_type="NPC", owner_id=None)

        # When opening the XP edit page
        response = client.get("/character/pc-1/traits/XP")

        # Then the user is sent to the character view with an error
        assert response.headers["Location"] == "/character/pc-1"
        assert [category for category, _ in session_flashes(client)] == ["error"]

    def test_empty_post_changes_nothing(self, client, use_character, fake_vclient) -> None:
        """Verify a POST with no trait fields sends nothing and reports an error."""
        # Given an editable character
        use_character()

        # When posting an empty form
        response = _post(client, "XP", {})

        # Then nothing reaches the API and the form reloads with an error
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/XP"
        assert fake_vclient.requests == []
        assert [category for category, _ in session_flashes(client)] == ["error"]


class TestChangeValuePost:
    """POST of a value change."""

    @pytest.mark.parametrize(
        ("spend", "value", "affordable", "sent"),
        [
            ("NO_COST", "2", True, True),
            ("XP", "2", True, True),
            ("STARTING_POINTS", "2", True, True),
            ("XP", "2", False, False),
            ("STARTING_POINTS", "2", False, False),
            ("XP", "5", True, False),
        ],
        ids=[
            "no-cost",
            "xp",
            "starting-points",
            "xp-unaffordable",
            "starting-points-unaffordable",
            "value-not-offered",
        ],
    )
    def test_value_change_follows_value_options(  # noqa: PLR0917
        self, client, use_character, fake_vclient, spend, value, affordable, sent
    ) -> None:
        """Verify a change is sent with the page's currency only when the API offers and allows it."""
        # Given value options offering 2 dots for 7 points
        use_character()
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            model=_value_options(affordable=affordable, **{"2": ("increase", 7)}),
        )

        # When setting the trait value
        response = _post(client, spend, {"ct-1": value})

        # Then the change is sent with the currency only when offered and affordable
        requests = fake_vclient.requests_for(
            Routes.CHARACTER_TRAITS_VALUE_UPDATE, params=_trait_params()
        )
        expected = [{"target_value": int(value), "currency": spend}] if sent else []
        assert [r.json for r in requests] == expected
        assert response.headers.get("HX-Redirect") == f"/character/pc-1/traits/{spend}"

        # And a paid change reports the points spent, while a refused one warns
        [(category, message)] = session_flashes(client)
        assert category == ("success" if sent else "warning")
        if sent and spend != "NO_COST":
            assert "7" in message

    def test_change_value_conflict_flashes_and_redirects(
        self, client, use_character, fake_vclient
    ) -> None:
        """Verify a concurrent-change conflict flashes the API detail and reloads the form."""
        # Given an API that reports a concurrent change
        use_character()
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, model=_value_options(**{"2": ("increase", 0)})
        )
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_VALUE_UPDATE,
            status_code=409,
            detail="This trait was changed by another request. Reload it and try again.",
        )

        # When changing the value
        response = _post(client, "NO_COST", {"ct-1": "2"})

        # Then the form reloads with the API's message
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/NO_COST"
        assert any("changed by another request" in m for _, m in session_flashes(client))

    def test_change_value_on_missing_trait_flashes_and_redirects(
        self, client, use_character, fake_vclient
    ) -> None:
        """Verify a trait deleted elsewhere flashes the API detail instead of failing."""
        # Given a trait the API no longer has
        use_character()
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, status_code=404, detail="Trait not found"
        )

        # When changing its value
        response = _post(client, "NO_COST", {"ct-1": "2"})

        # Then the form reloads with the API's message
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/NO_COST"
        assert ("error", "Trait not found") in session_flashes(client)
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_UPDATE)

    def test_change_value_clears_sheet_cache(
        self, client, mocker, use_character, fake_vclient
    ) -> None:
        """Verify a value change drops the cached sheet so derived traits reload."""
        # Given an editable trait
        use_character()
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, model=_value_options(**{"2": ("increase", 0)})
        )
        clear = mocker.patch("vweb.routes.character_trait_edit.views.cache.character_sheet.clear")

        # When changing the value
        _post(client, "NO_COST", {"ct-1": "2"})

        # Then the character's cached sheet is dropped
        clear.assert_called_once_with("pc-1")


class TestTraitDeletePost:
    """POST of the DELETE sentinel."""

    @pytest.mark.parametrize("spend", ["NO_COST", "XP"])
    def test_delete_sends_currency(self, client, use_character, fake_vclient, spend) -> None:
        """Verify a delete is sent with the page's currency, reporting the refund when paid."""
        # Given a trait whose delete refunds 5 points
        use_character(free_changes="UNRESTRICTED")
        fake_vclient.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS, model=_value_options(DELETE=("decrease", 5))
        )

        # When posting the DELETE sentinel
        response = _post(client, spend, {"ct-1": "DELETE"})

        # Then the trait is deleted with the currency and the form reloads
        fake_vclient.assert_called(
            Routes.CHARACTER_TRAITS_DELETE,
            params=_trait_params(),
            query={"currency": spend},
            times=1,
        )
        assert response.headers.get("HX-Redirect") == f"/character/pc-1/traits/{spend}"
        [(category, message)] = session_flashes(client)
        assert category == "success"

        # And only a paid delete looks up and reports the refund
        if spend == "NO_COST":
            fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_OPTIONS)
        else:
            assert "5" in message

    @pytest.mark.parametrize(
        ("status_code", "detail", "expected"),
        [
            (400, "", None),
            (403, "Free trait changes are restricted", "Free trait changes are restricted"),
        ],
        ids=["unexplained-error", "refusal-with-reason"],
    )
    def test_delete_api_error_flashes_error(
        self, client, use_character, fake_vclient, status_code, detail, expected
    ) -> None:
        """Verify a failed delete flashes an error, with the API's reason when it gives one."""
        # Given the API refuses the delete
        use_character()
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_DELETE, status_code=status_code, detail=detail
        )

        # When posting the DELETE sentinel
        _post(client, "NO_COST", {"ct-1": "DELETE"})

        # Then an error is flashed, carrying the API's reason when there is one
        [(category, message)] = session_flashes(client)
        assert category == "error"
        if expected:
            assert expected in message

    def test_delete_request_validation_error_flashes_readable_text(
        self, client, mocker, use_character
    ) -> None:
        """Verify a client-side validation failure on delete flashes its message."""
        # Given the client rejects the request before it is sent, which the fake API cannot
        # produce because the route only accepts valid currencies
        use_character()
        with pytest.raises(PydanticValidationError) as info:
            _Currency(currency="BOGUS")
        traits_svc = mocker.patch(
            "vweb.routes.character_trait_edit.views.api_services.character_traits"
        ).return_value
        traits_svc.delete.side_effect = RequestValidationError(info.value)

        # When posting the DELETE sentinel
        _post(client, "NO_COST", {"ct-1": "DELETE"})

        # Then the flash names the failing field instead of only the generic failure
        assert any("Currency" in m for _, m in session_flashes(client))


class TestAssignUnassignedTrait:
    """POST of an ADD_UNASSIGNED field picks a standard trait from the blueprint."""

    def test_assigns_trait_at_minimum(self, client, mocker, use_character, fake_vclient) -> None:
        """Verify the chosen blueprint trait is assigned at its minimum with the page's currency."""
        # Given a blueprint trait
        use_character()
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.blueprint.trait",
            return_value=TraitFactory.build(id="t-occult", name="Occult", min_value=1),
        )

        # When adding it from the dropdown
        response = _post(client, "XP", {"ADD_UNASSIGNED_knowledges": "t-occult"})

        # Then it is assigned at its minimum value
        fake_vclient.assert_called(
            Routes.CHARACTER_TRAITS_ASSIGN,
            params={"character_id": "pc-1"},
            json={"trait_id": "t-occult", "value": 1, "currency": "XP"},
            times=1,
        )
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/XP"

    def test_unknown_trait_is_not_assigned(
        self, client, mocker, use_character, fake_vclient
    ) -> None:
        """Verify an id missing from the blueprint flashes an error and assigns nothing."""
        # Given a trait id the blueprint does not know
        use_character()
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.blueprint.trait", return_value=None
        )

        # When adding it
        _post(client, "XP", {"ADD_UNASSIGNED_knowledges": "t-missing"})

        # Then nothing is assigned and an error is shown
        fake_vclient.assert_not_called(Routes.CHARACTER_TRAITS_ASSIGN)
        assert [category for category, _ in session_flashes(client)] == ["error"]

    def test_assign_refusal_flashes_api_reason(
        self, client, mocker, use_character, fake_vclient
    ) -> None:
        """Verify an API refusal of the assign flashes its reason."""
        # Given an API that refuses the assign
        use_character()
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.blueprint.trait",
            return_value=TraitFactory.build(id="t-occult", min_value=1),
        )
        fake_vclient.set_error(
            Routes.CHARACTER_TRAITS_ASSIGN, status_code=400, detail="Not enough XP"
        )

        # When adding it
        _post(client, "XP", {"ADD_UNASSIGNED_knowledges": "t-occult"})

        # Then the API's reason is flashed as an error
        assert ("error", "Not enough XP") in session_flashes(client)


class TestCustomTraitCreation:
    """POST /character/<id>/traits/<spend_type> with a CUSTOM_<category> field."""

    @pytest.fixture(autouse=True)
    def _fake(self, fake_vclient, use_character) -> None:
        self.fake = fake_vclient
        self.use_character = use_character

    def _setup(self, mocker) -> Character:
        """Wire a PLAYER-owned player character and the API's create and balance responses.

        Free trait changes are pinned to UNRESTRICTED so the PLAYER passes the free-edit
        guard; `TestCharacterTraitsViewPermissions` covers the guard itself.
        """
        character = self.use_character(
            role="PLAYER", owner_id="test-user-id", free_changes="UNRESTRICTED"
        )
        self.fake.set_response(
            Routes.CHARACTER_TRAITS_CREATE, model=CharacterTraitFactory.build(id="new-trait-1")
        )
        self.fake.set_response(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            model=_value_options(xp_current=47, starting_points_current=93, DELETE=("decrease", 6)),
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

    @pytest.mark.parametrize(
        ("spend", "remaining"),
        [("XP", "47"), ("STARTING_POINTS", "93"), ("NO_COST", None)],
    )
    def test_create_custom_trait_sends_currency_and_reports_balance(
        self, client, mocker, spend, remaining
    ) -> None:
        """Verify a custom trait is created with the page's currency and paid ones report the balance."""
        # Given a PLAYER editing their own character
        self._setup(mocker)

        # When adding a custom trait in the "skills" category
        response = _post(client, spend, {"CUSTOM_skills": "street smarts"})

        # Then the trait is created with the currency and a title-cased name
        assert response.headers.get("HX-Redirect") == f"/character/pc-1/traits/{spend}"
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE,
            params={"company_id": "test-company-id", "character_id": "pc-1"},
            json={
                "name": "Street Smarts",
                "show_when_zero": True,
                "category_id": "skills",
                "currency": spend,
            },
            times=1,
        )
        # And the sheet is not fetched when no standard trait shares the name
        self.sheet_get.assert_not_called()

        # And a paid create reports what was spent and the remaining balance
        [(category, message)] = session_flashes(client)
        assert category == "success"
        if remaining:
            assert re.search(rf"\b6\b.*\b{remaining}\b", message)
        else:
            self.fake.assert_not_called(Routes.CHARACTER_TRAITS_VALUE_OPTIONS)
            assert not re.search(r"\d", message)

    def test_create_custom_trait_category_id_with_underscores(self, client, mocker) -> None:
        """Verify a category id containing underscores is parsed intact from the field name."""
        # Given a PLAYER editing their own character
        self._setup(mocker)

        # When the custom-trait field carries an underscore-laden category id
        _post(client, "XP", {"CUSTOM_skills_category_id": "street smarts"})

        # Then the full category id is sent, not just its first segment
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_CREATE, json_subset={"category_id": "skills_category_id"}
        )

    def test_create_custom_trait_balance_lookup_failure_falls_back(self, client, mocker) -> None:
        """Verify a failed balance lookup still reports success without a balance."""
        # Given the post-create value-options lookup fails
        self._setup(mocker)
        self.fake.set_error(
            Routes.CHARACTER_TRAITS_VALUE_OPTIONS,
            status_code=400,
            params={"character_trait_id": "new-trait-1"},
        )

        # When adding a custom trait in XP mode
        response = _post(client, "XP", {"CUSTOM_skills": "street smarts"})

        # Then the request still succeeds without a balance
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/XP"
        [(category, message)] = session_flashes(client)
        assert category == "success"
        assert "47" not in message

    def test_create_custom_trait_api_error_flashes_error(self, client, mocker) -> None:
        """Verify an API error during create flashes an error and does not raise."""
        # Given the create call fails with no reason a user could read
        self._setup(mocker)
        self.fake.set_error(Routes.CHARACTER_TRAITS_CREATE, status_code=400, detail="")

        # When adding a custom trait
        _post(client, "XP", {"CUSTOM_skills": "street smarts"})

        # Then an error is flashed
        assert [category for category, _ in session_flashes(client)] == ["error"]

    def test_create_custom_trait_empty_name_warns(self, client, mocker) -> None:
        """Verify a blank custom-trait name warns and never calls the service."""
        # Given a PLAYER editing their own character
        self._setup(mocker)

        # When submitting a whitespace-only name
        _post(client, "XP", {"CUSTOM_skills": "   "})

        # Then a warning is flashed and no trait is created
        assert [category for category, _ in session_flashes(client)] == ["warning"]
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_CREATE)

    @pytest.mark.parametrize(
        ("typed", "trait_kwargs"),
        [
            (
                "linguistics",
                {"name": "Linguistics", "category_id": "skills", "game_versions": ["V4"]},
            ),
            ("street smarts", {"name": "Street Smarts", "category_id": "merits"}),
        ],
        ids=["same-category-other-version", "other-category"],
    )
    def test_custom_name_matching_standard_trait_assigns_it(
        self, client, mocker, typed, trait_kwargs
    ) -> None:
        """Verify a typed name matching a standard trait assigns it instead of creating one."""
        # Given a standard trait with that name
        self._setup(mocker)
        standard = TraitFactory.build(
            id="std-1", custom_for_character_id=None, min_value=0, **trait_kwargs
        )
        self.blueprint_traits.return_value = {standard.id: standard}

        # When typing that name in the skills custom box
        response = _post(client, "XP", {"CUSTOM_skills": typed})

        # Then the standard trait is assigned and no custom trait is created
        assert response.headers.get("HX-Redirect") == "/character/pc-1/traits/XP"
        self.fake.assert_called(
            Routes.CHARACTER_TRAITS_ASSIGN,
            params={"character_id": "pc-1"},
            json={"trait_id": "std-1", "value": 0, "currency": "XP"},
            times=1,
        )
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_CREATE)

    def test_custom_name_already_on_character_does_not_assign(self, client, mocker) -> None:
        """Verify a name already on the sheet goes to create instead of assigning a duplicate."""
        # Given a character that already has Linguistics, and another same-named standard trait
        character = self._setup(mocker)
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

        # When typing that name in the custom box
        _post(client, "XP", {"CUSTOM_skills": "linguistics"})

        # Then no second trait is assigned and the create conflict is shown
        self.fake.assert_not_called(Routes.CHARACTER_TRAITS_ASSIGN)
        self.fake.assert_called(Routes.CHARACTER_TRAITS_CREATE, times=1)
        assert ("error", "Trait named 'Linguistics' already exists") in session_flashes(client)


class TestTraitEditRendering:
    """Controls the edit form offers for each trait."""

    @pytest.mark.parametrize(
        ("spend", "delete_offered"),
        [("NO_COST", True), ("STARTING_POINTS", False), ("XP", False)],
    )
    def test_delete_offered_only_on_free_edit(
        self, client, use_character, spend, delete_offered
    ) -> None:
        """Verify only the free-edit form lets a trait be deleted."""
        # Given a storyteller and a player character
        use_character()

        # When the edit form is requested
        html = client.get(f"/character/pc-1/traits/{spend}").get_data(as_text=True)

        # Then the trait has a delete control only in free-edit mode
        assert ('data-trait-id="ct-1"' in html) is delete_offered

    @pytest.mark.parametrize(
        ("game_version", "editable"),
        [("V5", False), ("V4", True)],
    )
    def test_willpower_editable_only_outside_v5(
        self, client, mocker, use_character, game_version, editable
    ) -> None:
        """Verify V5 Willpower, which the API derives, has no value or delete controls."""
        # Given a character with Willpower in the given game version
        character = use_character()
        character.game_version = game_version
        trait = TraitFactory.build(
            id="t-wp", name="Willpower", min_value=0, max_value=10, custom_for_character_id=None
        )
        category = FullSheetTraitCategoryFactory.build(
            character_traits=[CharacterTraitFactory.build(id="ct-wp", value=4, trait=trait)],
            subcategories=[],
            available_traits=[],
        )
        mocker.patch(
            "vweb.routes.character_trait_edit.views.cache.character_sheet.get",
            return_value=CharacterFullSheetFactory.build(
                character=character,
                sections=[FullSheetTraitSectionFactory.build(categories=[category])],
            ),
        )

        # When the free-edit form is requested
        html = client.get("/character/pc-1/traits/NO_COST").get_data(as_text=True)

        # Then Willpower's value and delete controls exist only outside V5
        assert ('name="ct-wp"' in html) is editable
        assert ('data-trait-id="ct-wp"' in html) is editable


class TestSpecialtyLossWarnings:
    """Confirmations and flashes for changes that remove an ability's specialties."""

    @pytest.fixture(autouse=True)
    def _fake(self, fake_vclient, use_context) -> None:
        self.fake = fake_vclient
        self.use_context = use_context

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
            id="pc-1", campaign_id=ctx.campaigns[0].id, user_player_id="owner-1"
        )
        ctx.characters = [character]
        self.use_context(ctx)
        melee = CharacterTraitFactory.build(
            id="ct-melee",
            value=melee_value,
            trait=TraitFactory.build(name="melee", sheet_section_name="Abilities", max_value=5),
            specialties=[build_specialty(f"sp-{i}", name) for i, name in enumerate(names)],
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

    def _html(self, client) -> str:
        return client.get("/character/pc-1/traits/NO_COST").get_data(as_text=True)

    @staticmethod
    def _value_button(html: str, trait_id: str, value: int) -> str:
        return re.search(rf'<button[^>]*name="{trait_id}"\s+value="{value}"[^>]*>', html).group(0)

    @pytest.mark.parametrize(
        ("trait_id", "confirms"),
        [("ct-melee", True), ("ct-str", False)],
        ids=["removes-specialties", "no-specialties"],
    )
    def test_value_button_confirms_specialty_loss(
        self, client, mocker, trait_id, *, confirms
    ) -> None:
        """Verify a value that removes specialties asks for confirmation naming them.

        Which values remove specialties under each rule is covered in test_trait_rules.py.
        """
        # Given an ability with specialties and an attribute without any
        self._setup(mocker)

        # When the free-edit form renders
        button = self._value_button(self._html(client), trait_id, 0)

        # Then dropping the ability to zero confirms, naming its specialties
        assert ("hx-confirm" in button) is confirms
        assert ("Knives, Swords" in button) is confirms

    def test_delete_trigger_carries_specialty_names(self, client, mocker) -> None:
        """Verify the delete control carries the specialty names for its confirmation."""
        # Given an ability with specialties
        self._setup(mocker)

        # When the free-edit form renders
        html = self._html(client)

        # Then the delete control names the specialties it will remove
        assert 'data-trait-specialties="Knives, Swords"' in html

    def test_confirm_escapes_names(self, client, mocker) -> None:
        """Verify specialty names are HTML-escaped in both attributes."""
        # Given a specialty name containing markup
        evil = '<b>"Edge"</b>'
        self._setup(mocker, names=(evil,))

        # When the free-edit form renders
        html = self._html(client)

        # Then the name is escaped in the confirmation and the delete control
        assert evil not in html
        escaped = "&lt;b&gt;&#34;Edge&#34;&lt;/b&gt;"
        assert escaped in self._value_button(html, "ct-melee", 0)
        assert f'data-trait-specialties="{escaped}"' in html

    @pytest.mark.parametrize(
        ("rules", "melee_value", "field", "value", "mentions_specialties"),
        [
            ("FIXED_COST", 3, "ct-melee", "0", True),
            ("FIXED_COST", 3, "ct-melee", "3", False),
            ("FIXED_COST", 3, "ct-melee", "DELETE", True),
            ("FIXED_COST", 3, "ct-str", "0", False),
            ("RATING_BASED", 5, "ct-melee", "3", True),
        ],
        ids=[
            "drop-to-zero",
            "fixed-cost-drop-above-zero",
            "delete",
            "trait-without-specialties",
            "rating-based-below-minimum",
        ],
    )
    def test_flash_reports_removed_specialties(  # noqa: PLR0917
        self, client, mocker, rules, melee_value, field, value, mentions_specialties
    ) -> None:
        """Verify the success message says when the change removed the trait's specialties."""
        # Given an ability with specialties under the given rules
        self._setup(mocker, rules=rules, melee_value=melee_value)

        # When posting the change
        _post(client, "NO_COST", {field: value})

        # Then the success message mentions specialties only when they were removed
        [(category, message)] = session_flashes(client)
        assert category == "success"
        assert ("specialties" in message) is mentions_specialties
