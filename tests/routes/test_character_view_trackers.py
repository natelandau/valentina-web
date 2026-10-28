"""Tests for trait trackers and health on the character sheet tab."""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx2
import pytest
from vclient.models import CharacterTraitSpecialty, StainsTracker
from vclient.testing import (
    CharacterFullSheetFactory,
    CharacterTraitFactory,
    CounterTrackerFactory,
    FullSheetTraitCategoryFactory,
    FullSheetTraitSectionFactory,
    FullSheetTraitSubcategoryFactory,
    HealthFactory,
    HealthLevelFactory,
    Routes,
    StainsTrackerFactory,
    TraitFactory,
)

from tests.conftest import get_csrf
from tests.helpers import build_mock_options_service
from vweb.routes.character_view import views_trackers

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from vclient.models import CharacterFullSheet, CharacterTrait
    from werkzeug.test import TestResponse

TRACKER_RULES = {
    "V4": {
        "COUNTER": {"actions": ["spend", "gain", "reset"]},
        "DAMAGE": {"actions": ["damage", "heal", "reset"]},
    },
    "V5": {
        "COUNTER": {"actions": ["spend", "gain", "reset"]},
        "STAINS": {"actions": ["add_stain", "remove_stain", "reset"]},
        "DAMAGE": {"actions": ["damage", "heal", "reset"]},
    },
}

SQUARE = re.compile(
    r"<(?:span|button)[^>]*data-tracker-square[^>]*>(.*?)</(?:span|button)>", re.DOTALL
)
SQUARE_TAG = re.compile(r"<(?:span|button)[^>]*data-tracker-square[^>]*>", re.DOTALL)


@pytest.fixture(autouse=True)
def tracker_rules(mocker) -> dict:
    """Serve tracker rules through the options cache; tests may edit the returned rules."""
    rules = json.loads(json.dumps(TRACKER_RULES))
    service = build_mock_options_service()
    service.get_options.return_value["characters"]["TrackerRules"] = rules
    mocker.patch("vweb.lib.cache.options.sync_options_service", return_value=service)
    return rules


def _sheet(character, *, traits=(), health=None) -> CharacterFullSheet:
    """Build a sheet with one section and category holding ``traits``."""
    category = FullSheetTraitCategoryFactory.build(
        name="Skills", show_when_empty=True, character_traits=list(traits), subcategories=[]
    )
    section = FullSheetTraitSectionFactory.build(name="Abilities", categories=[category])
    return CharacterFullSheetFactory.build(
        sections=[section], character=character.model_copy(update={"health": health})
    )


@pytest.fixture
def show_sheet(client, mocker, mock_campaign):
    """Return a callable that renders the sheet tab for a character."""

    def _show(character, *, traits=(), health=None, sheet=None) -> str:
        if sheet is None:
            sheet = _sheet(character, traits=traits, health=health)
        mocker.patch(
            "vweb.routes.character_view.views.cache.character_sheet.get", return_value=sheet
        )
        mocker.patch(
            "vweb.routes.character_view.views.get_character_and_campaign",
            return_value=(character, mock_campaign),
        )
        return client.get(f"/character/{character.id}").get_data(as_text=True)

    return _show


def _trait(
    tracker, *, value: int = 3, max_value: int = 5, name: str = "Willpower"
) -> CharacterTrait:
    return CharacterTraitFactory.build(
        id="ct-1",
        value=value,
        trait=TraitFactory.build(name=name, max_value=max_value),
        tracker=tracker,
    )


def _slot(html: str, slot_id: str) -> str:
    match = re.search(
        rf'<div id="{slot_id}"\s+data-tracker-slot[^>]*>(.*?)</div>\s*(?=</td>|</aside)',
        html,
        re.DOTALL,
    )
    assert match, f"slot {slot_id} not found"
    return match.group(1)


def _marks(html: str) -> list[str]:
    return [text.strip() for text in SQUARE.findall(html)]


@pytest.fixture
def v5_character(mock_character):
    """Return the test character on game version V5."""
    return mock_character.model_copy(update={"game_version": "V5"})


@pytest.fixture
def v4_character(mock_character):
    """Return the test character on game version V4."""
    return mock_character.model_copy(update={"game_version": "V4"})


def test_counter_renders_one_square_per_circle_with_cap_disabled(show_sheet, v4_character) -> None:
    """Verify a counter draws max(value, max) squares, marking current and disabling past size."""
    # Given a trait with value 7, max 10 and current 4 of size 7
    trait = _trait(CounterTrackerFactory.build(size=7, current=4), value=7, max_value=10)

    # When viewing the sheet
    html = show_sheet(v4_character, traits=[trait])

    # Then there are 10 squares, 4 marked, 3 disabled
    squares = SQUARE_TAG.findall(_slot(html, "tracker-ct-1"))
    assert len(squares) == 10
    assert sum('data-marked="true"' in tag for tag in squares) == 4
    assert sum('data-disabled="true"' in tag for tag in squares) == 3


def test_v5_willpower_is_a_tappable_counter(show_sheet, v5_character) -> None:
    """Verify V5 Willpower draws counter squares that post set actions."""
    # Given V5 Willpower with 2 of 4 available
    trait = _trait(CounterTrackerFactory.build(size=4, current=2), value=4)

    # When viewing the sheet
    html = show_sheet(v5_character, traits=[trait])

    # Then the squares are counter squares that set current, with no stain stepper
    slot = _slot(html, "tracker-ct-1")
    controls = _controls(slot)
    assert [control["vals"] for control in controls] == [
        {"action": "set", "current": 0},
        {"action": "set", "current": 1},
        {"action": "set", "current": 3},
        {"action": "set", "current": 4},
    ]
    assert "Stains" not in slot


@pytest.mark.parametrize(
    ("tracker", "expected_actions"),
    [
        (CounterTrackerFactory.build(size=7, current=7), {"set"}),
        (
            StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=1),
            {"add_stain", "remove_stain"},
        ),
    ],
    ids=["non-vampire-counter", "vampire-stains"],
)
def test_v5_humanity_control_follows_tracker_type(
    show_sheet, v5_character, tracker, expected_actions
) -> None:
    """Verify V5 Humanity draws a counter or a stain stepper from the trait's tracker type."""
    # Given Humanity with a counter (mortal) or a stains tracker (vampire)
    trait = _trait(tracker, value=7, max_value=10, name="Humanity")

    # When viewing the sheet
    html = show_sheet(v5_character, traits=[trait])

    # Then the controls match the tracker type
    controls = _controls(_slot(html, "tracker-ct-1"))
    assert {control["vals"]["action"] for control in controls} == expected_actions


def test_stains_fill_from_right(show_sheet, v5_character) -> None:
    """Verify stains mark the last squares and humanity squares are disabled."""
    # Given humanity 7 with 2 stains
    tracker = StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=2)

    # When viewing the sheet
    html = show_sheet(v5_character, traits=[_trait(tracker, name="Humanity")])

    # Then the last two of ten squares are slashes and the first seven are disabled
    squares = SQUARE_TAG.findall(_slot(html, "tracker-ct-1"))
    assert len(squares) == 10
    assert _marks(_slot(html, "tracker-ct-1"))[-2:] == ["/", "/"]
    assert all('data-disabled="true"' in tag for tag in squares[:7])
    assert not any('data-disabled="true"' in tag for tag in squares[7:])


def test_v4_health_marks_levels_from_marked(show_sheet, v4_character) -> None:
    """Verify V4 health draws one row per level, marked when the level is marked."""
    # Given a V4 health track with the first two of three levels marked
    levels = [
        HealthLevelFactory.build(name="Bruised", marked=True),
        HealthLevelFactory.build(name="Hurt", marked=True),
        HealthLevelFactory.build(name="Crippled", marked=False),
    ]
    health = HealthFactory.build(size=3, damage=2, levels=levels)

    # When viewing the sheet
    html = show_sheet(v4_character, health=health)

    # Then each level appears with its mark, and no penalty or impairment is drawn
    block = _health_block(html)
    for name in ("Bruised", "Hurt", "Crippled"):
        assert name in block
    squares = SQUARE_TAG.findall(block)
    assert ['data-marked="true"' in tag for tag in squares] == [True, True, False]
    assert "penalty" not in block.lower()
    assert "Impaired" not in block
    assert "Incapacitated" not in block


@pytest.mark.parametrize(("damage", "marked"), [(2, 2), (None, 0)], ids=["damage", "none"])
def test_v5_health_marks_first_damage_squares(show_sheet, v5_character, damage, marked) -> None:
    """Verify V5 health marks the first ``damage`` squares, treating None as no damage."""
    # Given a V5 health track of 5 boxes
    health = HealthFactory.build(size=5, damage=damage, levels=None)

    # When viewing the sheet
    html = show_sheet(v5_character, health=health)

    # Then five squares appear with the first ``damage`` marked
    squares = SQUARE_TAG.findall(_health_block(html))
    assert len(squares) == 5
    assert ['data-marked="true"' in tag for tag in squares] == [i < marked for i in range(5)]


def test_trait_without_tracker_renders_no_squares(show_sheet, v5_character) -> None:
    """Verify a trait with no tracker gets no tracker slot."""
    html = show_sheet(v5_character, traits=[_trait(None)])

    assert "data-tracker-slot" not in html
    assert "data-tracker-square" not in html


def test_character_without_health_renders_no_health_block(show_sheet, v5_character) -> None:
    """Verify no health block appears when the character has no health."""
    html = show_sheet(v5_character, health=None)

    assert 'id="health-track"' not in html


def _health_block(html: str) -> str:
    return html[html.index('id="health-track"') : html.index("</aside")]


def test_non_editor_sees_no_tracker_controls(show_sheet, mock_character) -> None:
    """Verify a player viewing someone else's character gets squares only."""
    # Given a character owned by another user, with a counter and health
    other = mock_character.model_copy(
        update={"user_player_id": "someone-else", "game_version": "V5"}
    )
    health = HealthFactory.build(size=5, damage=1, levels=None)
    trait = _trait(CounterTrackerFactory.build(size=3, current=2))

    # When viewing the sheet
    html = show_sheet(other, traits=[trait], health=health)

    # Then no control is rendered inside any tracker slot or the health block
    assert "data-tracker-slot" in html
    for fragment in (_slot(html, "tracker-ct-1"), _health_block(html)):
        assert "<button" not in fragment
        assert "@click" not in fragment
        assert "htmx.ajax" not in fragment
        assert "hx-post" not in fragment


def _wrapper_tag(html: str, slot_id: str) -> str:
    match = re.search(rf'<div id="{slot_id}"\s+data-tracker-slot[^>]*>', html)
    assert match, f"wrapper {slot_id} not found"
    return match.group(0)


def test_stable_wrappers_issue_and_queue_every_request(show_sheet, v5_character) -> None:
    """Verify each control sends from its stable wrapper, which targets and queues itself."""
    # Given an editable counter and health
    trait = _trait(CounterTrackerFactory.build(size=3, current=1))
    health = HealthFactory.build(**HEALTH_V5)

    # When viewing the sheet
    html = show_sheet(v5_character, traits=[trait], health=health)

    # Then both wrappers carry the target, swap and queue, and a bare Alpine scope
    for slot_id in ("tracker-ct-1", "health-track"):
        wrapper = _wrapper_tag(html, slot_id)
        assert 'hx-target="this"' in wrapper
        assert 'hx-swap="innerHTML"' in wrapper
        assert 'hx-sync="this:queue all"' in wrapper
        assert re.search(r"\sx-data\s", wrapper)
        assert "x-data=" not in wrapper
    assert "x-data" not in _slot(html, "tracker-ct-1")

    # Then no control inside carries its own htmx request attributes
    for fragment in (_slot(html, "tracker-ct-1"), _health_block(html)):
        controls = _controls(fragment)
        assert controls
        assert all(control["source"] == "[data-tracker-slot]" for control in controls)
        for attribute in ("hx-post", "hx-target", "hx-swap", "hx-sync", "hx-vals"):
            assert attribute not in fragment.split(">", 1)[1]


SEND = re.compile(
    r"htmx\.ajax\('POST', '(?P<url>[^']+)', "
    r"\{source: \$el\.closest\('(?P<source>[^']+)'\), values: (?P<vals>\{.*\})\}\)",
    re.DOTALL,
)


def _controls(fragment: str) -> list[dict]:
    """Return each control in ``fragment`` that sends a request, with its URL, source and values."""
    controls = []
    for tag in re.findall(r"<button[^>]*htmx\.ajax[^>]*>.*?</button>", fragment, re.DOTALL):
        click = html_lib.unescape(re.search(r'@click="([^"]*)"', tag).group(1))
        send = SEND.fullmatch(click)
        assert send, f"unexpected click handler: {click}"
        controls.append(
            {
                "tag": tag,
                "url": send["url"],
                "source": send["source"],
                "vals": json.loads(send["vals"]),
                "disabled": bool(re.search(r"\sdisabled[\s>]", tag.split(">")[0])),
                "text": re.sub(r"<[^>]+>", "", tag).strip(),
            }
        )
    return controls


def test_counter_squares_post_set_with_toggled_current(show_sheet, v4_character) -> None:
    """Verify marked squares post their own index and unmarked squares post index + 1."""
    # Given a counter with 2 of 4 available
    trait = _trait(CounterTrackerFactory.build(size=4, current=2), value=4)

    # When viewing the sheet
    html = show_sheet(v4_character, traits=[trait])

    # Then each square posts action=set to the tracker URL
    controls = _controls(_slot(html, "tracker-ct-1"))
    assert {control["url"] for control in controls} == {
        f"/character/{v4_character.id}/traits/ct-1/tracker"
    }
    assert [control["vals"] for control in controls] == [
        {"action": "set", "current": 0},
        {"action": "set", "current": 1},
        {"action": "set", "current": 3},
        {"action": "set", "current": 4},
    ]


def test_stains_stepper_posts_and_disables_at_limits(show_sheet, v5_character) -> None:
    """Verify the stains stepper posts add/remove, disables at 0 and 10, and allows overflow."""
    # Given no stains, stains past the free boxes, then all ten boxes stained
    empty = StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=0)
    overflow = StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=3)
    full = StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=10)

    # When viewing each sheet
    def controls(tracker: StainsTracker) -> dict:
        html = show_sheet(v5_character, traits=[_trait(tracker)])
        return {c["vals"]["action"]: c for c in _controls(_slot(html, "tracker-ct-1"))}

    empty_controls = controls(empty)
    overflow_controls = controls(overflow)
    full_controls = controls(full)

    # Then the requests are right and only the 0 and 10 limits disable a button
    assert set(empty_controls) == {"add_stain", "remove_stain"}
    assert empty_controls["remove_stain"]["disabled"] is True
    assert empty_controls["add_stain"]["disabled"] is False
    assert overflow_controls["add_stain"]["disabled"] is False
    assert full_controls["add_stain"]["disabled"] is True
    assert full_controls["remove_stain"]["disabled"] is False


@pytest.mark.parametrize(
    ("damage", "damage_disabled", "heal_disabled"),
    [(0, False, True), (2, False, False), (3, True, False)],
    ids=["unhurt", "hurt", "full"],
)
def test_health_buttons_post_damage_and_heal(
    show_sheet, v4_character, damage, damage_disabled, heal_disabled
) -> None:
    """Verify Damage and Heal post their action to the health URL and disable at the limits."""
    # Given a V4 health track of three levels with some damage
    levels = [HealthLevelFactory.build(name=f"L{i}", marked=i < damage) for i in range(3)]
    health = HealthFactory.build(size=3, damage=damage, levels=levels)

    # When viewing the sheet
    html = show_sheet(v4_character, health=health)

    # Then exactly two buttons post damage and heal with no menu
    block = _health_block(html)
    controls = {c["text"]: c for c in _controls(block)}
    assert set(controls) == {"Damage", "Heal"}
    assert {c["url"] for c in controls.values()} == {f"/character/{v4_character.id}/health"}
    assert controls["Damage"]["vals"] == {"action": "damage"}
    assert controls["Heal"]["vals"] == {"action": "heal"}
    assert "btn-error" in controls["Damage"]["tag"]
    assert "btn-success" in controls["Heal"]["tag"]
    assert controls["Damage"]["disabled"] is damage_disabled
    assert controls["Heal"]["disabled"] is heal_disabled
    assert "x-show" not in block


def test_health_buttons_follow_tracker_rules(show_sheet, v5_character, tracker_rules) -> None:
    """Verify a health action missing from the tracker rules gets no button."""
    # Given rules that allow damage but not heal on V5 health
    tracker_rules["V5"]["DAMAGE"]["actions"] = ["damage"]
    health = HealthFactory.build(size=5, damage=2, levels=None)

    # When viewing the sheet
    html = show_sheet(v5_character, health=health)

    # Then only the Damage button is drawn
    assert [c["text"] for c in _controls(_health_block(html))] == ["Damage"]


def test_stain_stepper_follows_tracker_rules(show_sheet, v5_character, tracker_rules) -> None:
    """Verify stain stepper buttons appear only for actions the tracker rules list."""
    # Given rules that list no stain actions
    tracker_rules["V5"]["STAINS"]["actions"] = []
    trait = _trait(StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=1))

    # When viewing the sheet
    html = show_sheet(v5_character, traits=[trait])

    # Then the stains are drawn without controls
    slot = _slot(html, "tracker-ct-1")
    assert len(SQUARE_TAG.findall(slot)) == 10
    assert not _controls(slot)


HEALTH_V5 = {"size": 5, "damage": 0, "levels": None}


@pytest.fixture
def post_tracker(client, mocker, mock_campaign):
    """Return a callable that posts a form to a tracker endpoint with the given sheet loaded."""

    def _post(
        character,
        url_suffix,
        data,
        *,
        traits=(),
        health=None,
        htmx: bool = True,
        character_found: bool = True,
    ) -> TestResponse:
        mocker.patch(
            "vweb.routes.character_view.views_trackers.cache.character_sheet.get",
            return_value=_sheet(character, traits=traits, health=health),
        )
        mocker.patch(
            "vweb.routes.character_view.views_trackers.get_character_and_campaign",
            return_value=(character, mock_campaign) if character_found else (None, None),
        )
        headers = {"X-CSRFToken": get_csrf(client)}
        if htmx:
            headers["HX-Request"] = "true"
        return client.post(f"/character/{character.id}{url_suffix}", data=data, headers=headers)

    return _post


@pytest.fixture
def sheet_cache(mocker) -> dict[str, MagicMock]:
    """Spy on the sheet cache writes the endpoints make."""
    prefix = "vweb.routes.character_view.views_trackers.cache"
    return {
        "update": mocker.patch(f"{prefix}.character_sheet.update"),
        "clear": mocker.patch(f"{prefix}.character_sheet.clear"),
    }


def _apply_update(
    sheet_cache: dict[str, MagicMock], sheet: CharacterFullSheet
) -> CharacterFullSheet:
    """Run every recorded sheet-cache update against ``sheet`` and return it."""
    for call in sheet_cache["update"].call_args_list:
        call.args[1](sheet)
    return sheet


def _assert_no_cache_change(sheet_cache: dict[str, MagicMock]) -> None:
    for spy in sheet_cache.values():
        spy.assert_not_called()


def _record_requests(fake_vclient, mocker) -> list:
    """Record every API request the vclient services send as (method, json body) pairs."""
    from vclient._sync.services.base import SyncBaseService

    seen: list = []
    original = SyncBaseService._request

    def _spy(self, method, path, **kwargs) -> object:
        seen.append((method, kwargs.get("json")))
        return original(self, method, path, **kwargs)

    mocker.patch.object(SyncBaseService, "_request", _spy)
    return seen


def test_counter_set_rerenders_partial_and_writes_cached_sheet(
    post_tracker, fake_vclient, sheet_cache, v4_character
) -> None:
    """Verify a set re-renders from the API result and writes it into the cached sheet."""
    # Given the API stores current=2 of size 4
    stored = CounterTrackerFactory.build(size=4, current=2)
    fake_vclient.set_response(Routes.CHARACTER_TRAITS_TRACKER_SET, model=stored)
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    # When setting current to 2
    response = post_tracker(
        v4_character, "/traits/ct-1/tracker", {"action": "set", "current": "2"}, traits=[trait]
    )

    # Then the partial shows 2 marked squares
    assert response.status_code == 200
    squares = SQUARE_TAG.findall(response.get_data(as_text=True))
    assert sum('data-marked="true"' in tag for tag in squares) == 2

    # Then the cached sheet is updated in place, not cleared
    sheet_cache["clear"].assert_not_called()
    sheet_cache["update"].assert_called_once()
    assert sheet_cache["update"].call_args.args[0] == v4_character.id
    cached = _apply_update(sheet_cache, _sheet(v4_character, traits=[trait.model_copy()]))
    assert cached.sections[0].categories[0].character_traits[0].tracker == stored


def test_stain_action_posts_action_and_amount(
    post_tracker, fake_vclient, sheet_cache, mocker, v5_character
) -> None:
    """Verify a stain action reaches the API with amount 1 and the result is stored."""
    # Given the API returns a tracker with two stains
    stored = StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=2)
    fake_vclient.set_response(Routes.CHARACTER_TRAITS_TRACKER_ACTION, model=stored)
    seen = _record_requests(fake_vclient, mocker)
    trait = _trait(StainsTrackerFactory.build(humanity=7, stain_capacity=3, stains=1))

    # When adding a stain
    response = post_tracker(
        v5_character, "/traits/ct-1/tracker", {"action": "add_stain"}, traits=[trait]
    )

    # Then the API received only the action and amount
    assert response.status_code == 200
    body = next(payload for method, payload in seen if method == "POST")
    assert body == {"action": "add_stain", "amount": 1}
    assert _marks(response.get_data(as_text=True))[-2:] == ["/", "/"]
    cached = _apply_update(sheet_cache, _sheet(v5_character, traits=[trait.model_copy()]))
    assert cached.sections[0].categories[0].character_traits[0].tracker == stored


def test_health_damage_rerenders_health(
    post_tracker, fake_vclient, sheet_cache, v5_character
) -> None:
    """Verify a health action renders the API's health and writes it into the cached sheet."""
    # Given the API returns health with one point of damage
    stored = HealthFactory.build(**{**HEALTH_V5, "damage": 1})
    fake_vclient.set_response(Routes.CHARACTERS_HEALTH_ACTION, model=stored)

    # When damaging health
    response = post_tracker(
        v5_character, "/health", {"action": "damage"}, health=HealthFactory.build(**HEALTH_V5)
    )

    # Then five squares are drawn with the first one marked
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    squares = SQUARE_TAG.findall(body)
    assert ['data-marked="true"' in tag for tag in squares] == [True, False, False, False, False]

    # Then the full sheet was never read, and the cached sheet now holds the new health
    views_trackers.cache.character_sheet.get.assert_not_called()
    sheet_cache["clear"].assert_not_called()
    cached = _apply_update(sheet_cache, _sheet(v5_character))
    assert cached.character.health == stored


@pytest.mark.parametrize("character_type", ["PLAYER", "NPC"])
def test_non_owner_gets_403_on_both_endpoints(
    post_tracker, fake_vclient, mocker, v5_character, character_type
) -> None:
    """Verify a player who does not own the character is refused, NPC or not."""
    # Given a character owned by someone else, and an API that must not be called
    other = v5_character.model_copy(
        update={"user_player_id": "someone-else", "type": character_type}
    )
    seen = _record_requests(fake_vclient, mocker)
    trait = _trait(CounterTrackerFactory.build(size=3, current=1))

    # When posting to both endpoints
    tracker = post_tracker(
        other, "/traits/ct-1/tracker", {"action": "set", "current": "2"}, traits=[trait]
    )
    health = post_tracker(other, "/health", {"action": "damage"})

    # Then both leave the page as it is, flash the refusal and make no API change
    for response in (tracker, health):
        assert response.status_code == 200
        assert response.headers["HX-Reswap"] == "none"
        assert "You cannot change this character&#39;s trackers." in response.get_data(as_text=True)
    assert not [call for call in seen if call[0] in ("PUT", "POST")]


def test_non_owner_without_htmx_gets_403(post_tracker, fake_vclient, mocker, v5_character) -> None:
    """Verify a non-htmx request from a non-owner keeps the plain 403."""
    other = v5_character.model_copy(update={"user_player_id": "someone-else"})
    seen = _record_requests(fake_vclient, mocker)

    response = post_tracker(other, "/health", {"action": "damage"}, htmx=False)

    assert response.status_code == 403
    assert "HX-Reswap" not in response.headers
    assert not [call for call in seen if call[0] == "POST"]


def test_npc_non_owner_with_unrestricted_setting_gets_403(
    post_tracker, fake_vclient, mocker, v5_character, mock_global_context
) -> None:
    """Verify opening NPC management to everyone does not open tracker edits."""
    # Given an ownerless NPC in a company with unrestricted NPC management
    settings = mock_global_context.company.settings.model_copy(
        update={"permission_manage_npc": "UNRESTRICTED"}
    )
    mock_global_context.company = mock_global_context.company.model_copy(
        update={"settings": settings}
    )
    npc = v5_character.model_copy(update={"user_player_id": None, "type": "NPC"})
    seen = _record_requests(fake_vclient, mocker)

    # When posting a health action
    response = post_tracker(npc, "/health", {"action": "damage"})

    # Then it is refused with no API call
    assert response.headers["HX-Reswap"] == "none"
    assert "You cannot change this character&#39;s trackers." in response.get_data(as_text=True)
    assert not [call for call in seen if call[0] == "POST"]


@pytest.mark.parametrize(
    ("suffix", "data"),
    [
        ("/traits/ct-1/tracker", {"action": "explode"}),
        ("/traits/ct-1/tracker", {"action": "set", "current": "abc"}),
        ("/traits/ct-1/tracker", {"action": "damage"}),
        ("/traits/ct-1/tracker", {"action": "heal"}),
        ("/traits/ct-1/tracker", {"action": "spend"}),
        ("/health", {"action": "set", "current": "1"}),
        ("/health", {"action": "reset"}),
        ("/health", {}),
    ],
)
def test_garbage_form_returns_400_without_api_call(
    post_tracker, fake_vclient, mocker, v5_character, suffix, data
) -> None:
    """Verify an invalid form is rejected before any API call."""
    seen = _record_requests(fake_vclient, mocker)
    trait = _trait(CounterTrackerFactory.build(size=3, current=1))

    response = post_tracker(v5_character, suffix, data, traits=[trait])

    assert response.status_code == 400
    assert not seen


def test_unknown_trait_flashes_without_swap(
    post_tracker, fake_vclient, mocker, v5_character
) -> None:
    """Verify a trait missing from the sheet flashes, keeps the page and changes nothing."""
    seen = _record_requests(fake_vclient, mocker)

    response = post_tracker(
        v5_character, "/traits/nope/tracker", {"action": "set", "current": "1"}, traits=[]
    )

    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert "That trait is no longer on the sheet." in response.get_data(as_text=True)
    assert not seen


def test_unknown_trait_without_htmx_returns_404(post_tracker, v5_character) -> None:
    """Verify a non-htmx request for a trait missing from the sheet keeps the plain 404."""
    response = post_tracker(
        v5_character,
        "/traits/nope/tracker",
        {"action": "set", "current": "1"},
        traits=[],
        htmx=False,
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("suffix", "data"),
    [
        ("/traits/ct-1/tracker", {"action": "set", "current": "1"}),
        ("/health", {"action": "damage"}),
    ],
)
def test_missing_character_flashes_without_swap(
    post_tracker, fake_vclient, mocker, v5_character, suffix, data
) -> None:
    """Verify a character missing from the global context is refused with no API call."""
    seen = _record_requests(fake_vclient, mocker)

    response = post_tracker(v5_character, suffix, data, character_found=False)

    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert "Character not found." in response.get_data(as_text=True)
    assert not seen


def test_api_validation_error_rerenders_from_fresh_fetch_with_flash(
    post_tracker, fake_vclient, sheet_cache, v4_character
) -> None:
    """Verify an API rejection flashes and redraws the tracker from a fresh fetch."""
    # Given the set is rejected and a GET returns current=3
    fake_vclient.set_error(
        Routes.CHARACTER_TRAITS_TRACKER_SET, status_code=400, detail="Current is above the size"
    )
    fake_vclient.set_response(
        Routes.CHARACTER_TRAITS_TRACKER_GET, model=CounterTrackerFactory.build(size=4, current=3)
    )
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    # When posting a set
    response = post_tracker(
        v4_character, "/traits/ct-1/tracker", {"action": "set", "current": "9"}, traits=[trait]
    )

    # Then the fresh state and the API's message are returned, and the cache holds the fresh state
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="flash-messages"' in body
    assert "Current is above the size" in body
    assert sum('data-marked="true"' in tag for tag in SQUARE_TAG.findall(body)) == 3
    sheet_cache["clear"].assert_not_called()
    cached = _apply_update(sheet_cache, _sheet(v4_character, traits=[trait.model_copy()]))
    assert cached.sections[0].categories[0].character_traits[0].tracker.current == 3


def test_refetch_failure_after_api_error_falls_back_to_sheet_tracker(
    post_tracker, fake_vclient, sheet_cache, v4_character
) -> None:
    """Verify a failing re-fetch still returns the cached tracker with the flash."""
    # Given both the set and the re-fetch fail
    fake_vclient.set_error(Routes.CHARACTER_TRAITS_TRACKER_SET, status_code=400)
    fake_vclient.set_error(Routes.CHARACTER_TRAITS_TRACKER_GET, status_code=404)
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    # When posting a set
    response = post_tracker(
        v4_character, "/traits/ct-1/tracker", {"action": "set", "current": "2"}, traits=[trait]
    )

    # Then the sheet's state is drawn with the flash container, and no cache changes
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="flash-messages"' in body
    assert sum('data-marked="true"' in tag for tag in SQUARE_TAG.findall(body)) == 1
    _assert_no_cache_change(sheet_cache)


def test_health_api_error_rerenders_from_fresh_fetch_with_flash(
    post_tracker, fake_vclient, sheet_cache, v5_character
) -> None:
    """Verify a rejected health action flashes the API's message and redraws fresh health."""
    fake_vclient.set_error(
        Routes.CHARACTERS_HEALTH_ACTION, status_code=400, detail="Nothing to heal"
    )
    fake_vclient.set_response(
        Routes.CHARACTERS_HEALTH_GET,
        model=HealthFactory.build(**{**HEALTH_V5, "damage": 1}),
    )

    response = post_tracker(v5_character, "/health", {"action": "heal"})

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Nothing to heal" in body
    assert 'data-marked="true"' in SQUARE_TAG.findall(body)[0]
    assert "HX-Reswap" not in response.headers
    sheet_cache["clear"].assert_not_called()
    cached = _apply_update(sheet_cache, _sheet(v5_character))
    assert cached.character.health.damage == 1


def test_health_refetch_failure_flashes_without_swap(
    post_tracker, fake_vclient, sheet_cache, v5_character
) -> None:
    """Verify a failing health re-fetch returns only the flash and keeps the page as it is."""
    fake_vclient.set_error(Routes.CHARACTERS_HEALTH_ACTION, status_code=400)
    fake_vclient.set_error(Routes.CHARACTERS_HEALTH_GET, status_code=404)

    response = post_tracker(
        v5_character,
        "/health",
        {"action": "damage"},
        health=HealthFactory.build(**HEALTH_V5),
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert 'id="flash-messages"' in body
    assert not SQUARE_TAG.findall(body)
    views_trackers.cache.character_sheet.get.assert_not_called()
    _assert_no_cache_change(sheet_cache)


@pytest.fixture
def _no_retry_delay(mocker) -> None:
    """Skip vclient's retry backoff so retried errors fail fast."""
    mocker.patch("vclient._sync.services.base.time.sleep")


@pytest.mark.usefixtures("_no_retry_delay")
@pytest.mark.parametrize("status_code", [429, 500, 503])
@pytest.mark.parametrize(
    "endpoint",
    [
        (
            "/traits/ct-1/tracker",
            Routes.CHARACTER_TRAITS_TRACKER_SET,
            {"action": "set", "current": "2"},
        ),
        (
            "/health",
            Routes.CHARACTERS_HEALTH_ACTION,
            {"action": "damage"},
        ),
    ],
)
def test_unexpected_api_error_flashes_without_swap(
    post_tracker, fake_vclient, sheet_cache, v5_character, endpoint, status_code
) -> None:
    """Verify server, rate-limit and other API errors flash a retry hint and drop the cached sheet."""
    suffix, route, data = endpoint
    fake_vclient.set_error(route, status_code=status_code)
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    response = post_tracker(
        v5_character, suffix, data, traits=[trait], health=HealthFactory.build(**HEALTH_V5)
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert "Could not save, try again." in body
    assert not SQUARE_TAG.findall(body)
    sheet_cache["update"].assert_not_called()
    sheet_cache["clear"].assert_called_once_with(v5_character.id)


def test_counter_squares_carry_label_and_pressed_state(show_sheet, v4_character) -> None:
    """Verify each editable counter square names its point and reports whether it is marked."""
    trait = _trait(CounterTrackerFactory.build(size=3, current=1), value=3, max_value=3)

    html = show_sheet(v4_character, traits=[trait])

    tags = SQUARE_TAG.findall(_slot(html, "tracker-ct-1"))
    assert [re.search(r'aria-label="([^"]+)"', tag).group(1) for tag in tags] == [
        "Willpower point 1",
        "Willpower point 2",
        "Willpower point 3",
    ]
    assert [re.search(r'aria-pressed="([^"]+)"', tag).group(1) for tag in tags] == [
        "true",
        "false",
        "false",
    ]


def test_disabled_marked_square_keeps_its_fill(show_sheet, v4_character) -> None:
    """Verify a square that is both disabled and marked still draws as filled."""
    # Given a counter whose current runs past its size
    trait = _trait(CounterTrackerFactory.build(size=2, current=3), value=2, max_value=3)

    html = show_sheet(v4_character, traits=[trait])

    last = SQUARE_TAG.findall(_slot(html, "tracker-ct-1"))[2]
    assert 'data-disabled="true"' in last
    assert 'data-marked="true"' in last
    assert "bg-base-content" in last


def _rows(html: str) -> list[str]:
    table = html[html.index("<table") : html.index("</table>")]
    return re.findall(r"<tr>(.*?)</tr>", table, re.DOTALL)


NOW = datetime(2026, 1, 1, tzinfo=UTC)
FIXED_CELL = '<span class="inline-flex track-cell justify-center">'


@pytest.mark.parametrize("in_subcategory", [False, True], ids=["category", "subcategory"])
def test_tracked_trait_gets_full_width_rows(show_sheet, v5_character, in_subcategory) -> None:
    """Verify a tracked trait's name spans the table and its circles stack over the squares."""
    # Given a tracked trait with a specialty, in a category or a subcategory
    trait = _trait(CounterTrackerFactory.build(size=3, current=1), value=3, max_value=5)
    trait = trait.model_copy(
        update={
            "specialties": [
                CharacterTraitSpecialty(id="sp-1", name="Grit", date_created=NOW, date_modified=NOW)
            ]
        }
    )
    if in_subcategory:
        subcategory = FullSheetTraitSubcategoryFactory.build(
            name="Nested", character_traits=[trait]
        )
        category = FullSheetTraitCategoryFactory.build(
            name="Skills", show_when_empty=True, character_traits=[], subcategories=[subcategory]
        )
        section = FullSheetTraitSectionFactory.build(name="Abilities", categories=[category])
        sheet = CharacterFullSheetFactory.build(sections=[section], character=v5_character)
        html = show_sheet(v5_character, sheet=sheet)
    else:
        html = show_sheet(v5_character, traits=[trait])

    # When reading the trait's two rows
    rows = [row for row in _rows(html) if "Willpower" in row or "tracker-ct-1" in row]
    name_row, tracker_row = rows

    # Then the name and specialties span both columns with no circles beside them
    assert re.search(r'<td class="text-lg align-top"\s+colspan="2">', name_row)
    assert "Grit" in name_row
    assert "fa-circle" not in name_row
    assert name_row.count("<td") == 1

    # Then the circles sit above the squares in one full-width cell, in square-width cells
    assert re.search(r'<td colspan="2"', tracker_row)
    assert tracker_row.index("fa-circle") < tracker_row.index('id="tracker-ct-1"')
    assert tracker_row.count(FIXED_CELL) == 5
    assert len(SQUARE_TAG.findall(tracker_row)) == 5


def test_trait_without_tracker_keeps_two_column_row(show_sheet, v5_character) -> None:
    """Verify an untracked trait keeps its name and plain circles side by side."""
    html = show_sheet(v5_character, traits=[_trait(None)])

    (row,) = [row for row in _rows(html) if "Willpower" in row]
    assert row.count("<td") == 2
    assert "colspan" not in row
    assert "fa-circle" in row
    assert FIXED_CELL not in html


@pytest.mark.parametrize(
    "endpoint",
    [
        ("/traits/ct-1/tracker", "update_trait_tracker", {"action": "set", "current": "2"}),
        ("/health", "update_health", {"action": "damage"}),
    ],
)
def test_connection_error_on_change_flashes_without_swap(
    post_tracker, sheet_cache, mocker, v5_character, endpoint
) -> None:
    """Verify a network failure on the change flashes a retry hint and drops the cached sheet."""
    suffix, service, data = endpoint
    mocker.patch(
        f"vweb.routes.character_view.views_trackers.{service}",
        side_effect=httpx2.ConnectError("unreachable"),
    )
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    response = post_tracker(v5_character, suffix, data, traits=[trait])

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["HX-Reswap"] == "none"
    assert "Could not save, try again." in body
    sheet_cache["update"].assert_not_called()
    sheet_cache["clear"].assert_called_once_with(v5_character.id)


def test_refetch_connection_error_falls_back_to_sheet_tracker(
    post_tracker, fake_vclient, sheet_cache, mocker, v4_character
) -> None:
    """Verify a network failure on the re-fetch after a rejected change draws the sheet state."""
    fake_vclient.set_error(Routes.CHARACTER_TRAITS_TRACKER_SET, status_code=400)
    mocker.patch(
        "vweb.routes.character_view.views_trackers.fetch_trait_tracker",
        side_effect=httpx2.ConnectError("unreachable"),
    )
    trait = _trait(CounterTrackerFactory.build(size=4, current=1), value=4)

    response = post_tracker(
        v4_character, "/traits/ct-1/tracker", {"action": "set", "current": "2"}, traits=[trait]
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert sum('data-marked="true"' in tag for tag in SQUARE_TAG.findall(body)) == 1
    _assert_no_cache_change(sheet_cache)
