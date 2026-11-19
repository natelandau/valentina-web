"""Tests for the shared_cards blueprint (/cards/*)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from vweb.api_client.testing import (
    AuditLogFactory,
    CampaignFactory,
    CharacterFactory,
    RollStatisticsFactory,
    Routes,
)
from vweb.lib.cache.dicerolls import DiceRollDisplay
from vweb.lib.catalog import catalog

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from flask.testing import FlaskClient
    from pytest_mock import MockerFixture

    from vweb.api_client.models import Campaign
    from vweb.api_client.models.audit_logs import AuditLog


def _audit_log(**overrides: object) -> AuditLog:
    """Build an audit log row that references no entities and has no changes by default."""
    return AuditLogFactory.build(
        **{
            "user_id": None,
            "campaign_id": None,
            "character_id": None,
            "book_id": None,
            "chapter_id": None,
            "changes": None,
            **overrides,
        }  # ty:ignore[invalid-argument-type]
    )


def _set_page(fake_vclient, items: list[AuditLog], *, offset: int = 0, has_more: bool) -> None:
    """Serve one audit log page at `offset`, reporting a further page when `has_more`."""
    fake_vclient.set_response(
        Routes.COMPANIES_AUDIT_LOGS_LIST,
        items=items,
        offset=offset,
        total=offset + len(items) + int(has_more),
    )


@pytest.fixture
def mock_statistics(mocker: MockerFixture) -> MagicMock:
    """Patch the statistics cache so tests can check which scope it is asked for."""
    return mocker.patch(
        "vweb.lib.cache.statistics.get", autospec=True, return_value=RollStatisticsFactory.build()
    )


@pytest.fixture
def mock_rolls(mocker: MockerFixture) -> MagicMock:
    """Patch the recent dice rolls cache so tests can check the filters it is asked for."""
    return mocker.patch("vweb.lib.cache.dicerolls.recent", autospec=True, return_value=[])


@pytest.mark.parametrize(
    "path",
    [
        "/cards/statistics",
        "/cards/statistics?campaign_id=c1&user_id=u1",
        "/cards/dice-rolls",
        "/cards/character-list",
    ],
    ids=[
        "statistics-no-scope",
        "statistics-two-scopes",
        "dice-rolls-no-scope",
        "characters-no-scope",
    ],
)
def test_card_without_valid_scope_returns_400(client: FlaskClient, path: str) -> None:
    """Verify each card refuses a request without the scope it needs."""
    assert client.get(path).status_code == 400


@pytest.mark.parametrize(
    ("query", "expected_scope"),
    [
        ("campaign_id=c-1", ("campaign", "c-1")),
        ("user_id=u-1", ("user", "u-1")),
        ("character_id=ch-1", ("character", "ch-1")),
    ],
)
def test_statistics_card_uses_requested_scope(
    client: FlaskClient, mock_statistics: MagicMock, query, expected_scope
) -> None:
    """Verify the statistics card fetches statistics for the one requested scope."""
    response = client.get(f"/cards/statistics?{query}")

    assert response.status_code == 200
    mock_statistics.assert_called_once_with(*expected_scope)


class TestDiceRollsCard:
    """Tests for GET /cards/dice-rolls."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("campaign_id=c1", {"campaign_id": "c1", "character_id": "", "user_id": ""}),
            ("character_id=ch1", {"campaign_id": "", "character_id": "ch1", "user_id": ""}),
            ("user_id=u1", {"campaign_id": "", "character_id": "", "user_id": "u1"}),
            (
                "campaign_id=c1&character_id=ch1&user_id=u1",
                {"campaign_id": "c1", "character_id": "ch1", "user_id": "u1"},
            ),
        ],
        ids=["campaign", "character", "user", "combined"],
    )
    def test_forwards_every_scope_filter(
        self, client: FlaskClient, mock_rolls: MagicMock, query, expected
    ) -> None:
        """Verify every supplied scope narrows the rolls fetched."""
        response = client.get(f"/cards/dice-rolls?{query}")

        assert response.status_code == 200
        kwargs = mock_rolls.call_args.kwargs
        assert {key: kwargs[key] for key in expected} == expected

    @pytest.mark.parametrize(
        ("modifier", "expected"), [(1, "5d10 +1"), (-2, "5d10 -2"), (0, "5d10")]
    )
    def test_notation_shows_signed_modifier(
        self, client: FlaskClient, mock_rolls: MagicMock, modifier: int, expected: str
    ) -> None:
        """Verify the signed modifier follows the dice notation only when non-zero."""
        mock_rolls.return_value = [
            DiceRollDisplay(
                id="r1",
                character_id="c1",
                character_name="Alice",
                num_dice=5,
                dice_size=10,
                trait_names=[],
                result_type="SUCCESS",
                result_humanized="3 successes",
                date_created=datetime.now(UTC),
                comment=None,
                dice_modifier=modifier,
            )
        ]

        body = client.get("/cards/dice-rolls?campaign_id=c1").get_data(as_text=True)

        assert re.search(rf">\s*{re.escape(expected)}\s*<", body)


@pytest.mark.parametrize(
    ("component", "props", "present", "absent"),
    [
        (
            "shared.cards.Statistics",
            {"campaign_id": "camp-abc", "col_span": 2},
            ["/cards/statistics", "campaign_id=camp-abc", "col_span=2"],
            ["user_id=", "character_id="],
        ),
        (
            "shared.cards.RecentDiceRolls",
            {"character_id": "ch-1", "page_size": 10},
            ["/cards/dice-rolls", "character_id=ch-1", "page_size=10"],
            ["user_id=", "campaign_id="],
        ),
        (
            "shared.cards.AuditLog",
            {"campaign_id": "c-1", "page_size": 15},
            ["/cards/audit-log", "campaign_id=c-1", "page_size=15"],
            ["user_id=", "character_id=", "book_id=", "show_filters="],
        ),
    ],
    ids=["statistics", "dice-rolls", "audit-log"],
)
def test_card_wrapper_lazy_loads_its_endpoint_with_only_set_props(
    app, component, props, present, absent
) -> None:
    """Verify each card wrapper loads its endpoint with the set props and no empty ones."""
    with app.test_request_context():
        html = catalog.render(component, **props)

    for text in present:
        assert text in html
    for text in absent:
        assert text not in html


class TestAuditLogCardAuthorization:
    """Tests for who may read the audit log card and with which scope."""

    @pytest.mark.parametrize(
        ("role", "query", "expected_status"),
        [
            ("PLAYER", "", 403),
            ("PLAYER", "?campaign_id=own-campaign", 403),
            ("STORYTELLER", "?user_id=someone", 403),
            ("STORYTELLER", "?campaign_id=foreign-campaign", 404),
            ("STORYTELLER", "?campaign_id=own-campaign", 200),
            ("ADMIN", "", 200),
        ],
        ids=[
            "player-unscoped",
            "player-own-campaign",
            "storyteller-unscoped",
            "storyteller-foreign-campaign",
            "storyteller-own-campaign",
            "admin-unscoped",
        ],
    )
    def test_access_by_role_and_scope(
        self, client: FlaskClient, use_context, fake_vclient, role, query, expected_status
    ) -> None:
        """Verify admins see the company, storytellers only their campaigns, and players nothing."""
        # Given a user whose context holds their own campaign
        use_context(user_role=role, campaign=CampaignFactory.build(id="own-campaign"))
        fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

        # When requesting the card
        response = client.get(f"/cards/audit-log{query}")

        # Then only permitted requests reach the audit log
        assert response.status_code == expected_status
        assert bool(fake_vclient.requests_for(Routes.COMPANIES_AUDIT_LOGS_LIST)) is (
            expected_status == 200
        )


@pytest.mark.usefixtures("admin_context")
class TestAuditLogCard:
    """Tests for GET /cards/audit-log."""

    def test_forwards_filters_and_paging_to_api(self, client: FlaskClient, fake_vclient) -> None:
        """Verify every filter query arg, the page size, and the offset reach the API."""
        fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

        response = client.get(
            "/cards/audit-log"
            "?acting_user_id=a1&user_id=u1&campaign_id=c1"
            "&book_id=b1&chapter_id=ch1&character_id=char1"
            "&entity_type=CAMPAIGN&operation=UPDATE"
            "&date_from=2025-01-01&date_to=2025-02-01"
            "&page_size=15&offset=30"
        )

        assert response.status_code == 200
        (request,) = fake_vclient.requests_for(Routes.COMPANIES_AUDIT_LOGS_LIST)
        assert request.query == {
            "limit": "15",
            "offset": "30",
            "acting_user_id": "a1",
            "user_id": "u1",
            "campaign_id": "c1",
            "book_id": "b1",
            "chapter_id": "ch1",
            "character_id": "char1",
            "entity_type": "CAMPAIGN",
            "operation": "UPDATE",
            "date_from": "2025-01-01T00:00:00",
            "date_to": "2025-02-01T00:00:00",
        }

    @pytest.mark.parametrize(("raw", "expected"), [("250000", "100000"), ("-5", "0")])
    def test_offset_bounded_to_api_range(
        self, client: FlaskClient, fake_vclient, raw: str, expected: str
    ) -> None:
        """Verify a hand-edited offset is bounded to what the API accepts."""
        fake_vclient.set_response(Routes.COMPANIES_AUDIT_LOGS_LIST, items=[])

        response = client.get(f"/cards/audit-log?offset={raw}")

        assert response.status_code == 200
        (request,) = fake_vclient.requests_for(Routes.COMPANIES_AUDIT_LOGS_LIST)
        assert request.query["offset"] == expected

    @pytest.mark.parametrize(("body_only", "has_card_shell"), [("false", True), ("true", False)])
    def test_rows_render_inside_card_or_alone(
        self, client: FlaskClient, fake_vclient, admin_context, body_only, has_card_shell
    ) -> None:
        """Verify the first load wraps the rows in the card, and paging returns rows alone."""
        user = admin_context.users[0]
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[_audit_log(acting_user_id=user.id).model_dump(mode="json")],
        )

        body = client.get(f"/cards/audit-log?body_only={body_only}").get_data(as_text=True)

        assert user.username in body
        assert ('id="auditlog"' in body) is has_card_shell

    @pytest.mark.parametrize(
        ("changes", "shown"),
        [
            ({"name": {"old": "Alice", "new": "Bob"}}, ["name", "Alice", "Bob"]),
            ({"deleted_by": "user-1"}, ["deleted_by", "user-1"]),
        ],
        ids=["old-new-change", "off-shape-entry"],
    )
    def test_row_shows_its_changes(self, client: FlaskClient, fake_vclient, changes, shown) -> None:
        """Verify a row shows field changes and entries that are not old/new pairs."""
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[_audit_log(changes=changes).model_dump(mode="json")],
        )

        body = client.get("/cards/audit-log").get_data(as_text=True)

        for text in shown:
            assert text in body

    @pytest.mark.parametrize(("scoped", "links_character"), [(False, True), (True, False)])
    def test_entity_link_hidden_when_card_is_scoped_to_it(
        self, client: FlaskClient, fake_vclient, admin_context, scoped, links_character
    ) -> None:
        """Verify a row links the character it affects, unless the card is scoped to it."""
        character = CharacterFactory.build(campaign_id=admin_context.campaigns[0].id)
        admin_context.characters = [character]
        fake_vclient.set_response(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            items=[_audit_log(character_id=character.id).model_dump(mode="json")],
        )
        query = f"?character_id={character.id}" if scoped else ""

        body = client.get(f"/cards/audit-log{query}").get_data(as_text=True)

        assert (f'href="/character/{character.id}"' in body) is links_character

    @pytest.mark.parametrize(
        ("offset", "has_more", "newer_enabled", "older_enabled"),
        [(0, False, False, False), (10, True, True, True)],
        ids=["first-and-last-page", "middle-page"],
    )
    def test_paging_buttons_enabled_only_when_there_is_a_page(
        self, client: FlaskClient, fake_vclient, offset, has_more, newer_enabled, older_enabled
    ) -> None:
        """Verify Newer is disabled on the first page and Older when no more entries exist."""
        _set_page(fake_vclient, [_audit_log()], offset=offset, has_more=has_more)

        body = client.get(f"/cards/audit-log?offset={offset}").get_data(as_text=True)

        fake_vclient.assert_called(
            Routes.COMPANIES_AUDIT_LOGS_LIST, query={"offset": str(offset)}, times=1
        )

        for label, enabled in (("Newer entries", newer_enabled), ("Older entries", older_enabled)):
            button = re.search(rf'<button[^>]*aria-label="{label}"[^>]*>', body)
            assert button, f"{label} button not found"
            assert ("disabled" not in button.group(0)) is enabled

    @pytest.mark.parametrize("body_only", ["false", "true"])
    def test_paging_urls_keep_filters_and_load_rows_only(
        self, client: FlaskClient, fake_vclient, body_only
    ) -> None:
        """Verify Newer/Older reload only the rows, with the active filters and next offset."""
        _set_page(fake_vclient, [_audit_log() for _ in range(3)], offset=3, has_more=True)

        body = client.get(
            "/cards/audit-log?campaign_id=c-1&entity_type=CAMPAIGN&operation=UPDATE"
            f"&page_size=3&offset=3&body_only={body_only}"
        ).get_data(as_text=True)

        fake_vclient.assert_called(
            Routes.COMPANIES_AUDIT_LOGS_LIST,
            query={
                "limit": "3",
                "offset": "3",
                "campaign_id": "c-1",
                "entity_type": "CAMPAIGN",
                "operation": "UPDATE",
            },
            times=1,
        )

        older = re.search(r'aria-label="Older entries"[^>]*hx-get="([^"]+)"', body)
        assert older, "Older entries button not found"
        url = older.group(1)
        for text in ("body_only=true", "campaign_id=c-1", "entity_type=CAMPAIGN", "offset=6"):
            assert text in url
        for empty_filter in ("acting_user_id=", "user_id=", "character_id="):
            assert empty_filter not in url

    @pytest.mark.parametrize("show_filters", [True, False])
    def test_filter_bar_only_when_requested(
        self, client: FlaskClient, fake_vclient, admin_context, show_filters
    ) -> None:
        """Verify show_filters adds the filter controls, with the company's users to pick from."""
        _set_page(fake_vclient, [], has_more=False)
        user = admin_context.users[0]

        body = client.get(f"/cards/audit-log?show_filters={str(show_filters).lower()}").get_data(
            as_text=True
        )

        assert ('name="entity_type"' in body) is show_filters
        assert ('name="acting_user_id"' in body) is show_filters
        assert (f'<option value="{user.id}">' in body) is show_filters

    def test_filter_values_are_xss_safe(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a quote-injection payload in a filter value cannot break out of x-data."""
        _set_page(fake_vclient, [], has_more=False)
        payload = "';alert(1)//"

        body = client.get(f"/cards/audit-log?show_filters=true&entity_type={payload}").get_data(
            as_text=True
        )

        # Inspect the x-data attribute only, so paging hx-get URLs don't interfere
        match = re.search(r"x-data='(\{.*?\})'", body, re.DOTALL)
        assert match, "x-data block not found in response"
        x_data_block = match.group(0)
        assert "';alert(1)//" not in x_data_block
        assert "&#39;;alert(1)//" not in x_data_block
        assert "\\u0027;alert(1)//" in x_data_block

    def test_card_id_is_sanitized(self, client: FlaskClient, fake_vclient) -> None:
        """Verify a malicious card_id is stripped to a DOM-id-safe slug, blocking injection."""
        _set_page(fake_vclient, [], has_more=False)

        body = client.get("/cards/audit-log?show_filters=true&card_id=x');alert(1)//").get_data(
            as_text=True
        )

        assert "');alert(1)//" not in body
        assert "&#39;);alert(1)//" not in body
        assert 'id="xalert1-filters"' in body


class TestCharacterListCard:
    """Tests for GET /cards/character-list."""

    @pytest.fixture
    def roster(self, use_context) -> Campaign:
        """Serve a campaign with the session user's PLAYER character and another owner's NPC."""
        campaign = CampaignFactory.build()
        mine = CharacterFactory.build(
            name="My Hero", type="PLAYER", user_player_id="test-user-id", campaign_id=campaign.id
        )
        theirs = CharacterFactory.build(
            name="Their Npc", type="NPC", user_player_id="other-user", campaign_id=campaign.id
        )
        use_context(user_role="PLAYER", campaign=campaign, characters=[mine, theirs])
        return campaign

    @pytest.mark.parametrize(
        ("query", "shown", "hidden"),
        [
            ("bucket=all", ["My Hero", "Their Npc"], []),
            ("bucket=mine", ["My Hero"], ["Their Npc"]),
            ("bucket=others", ["Their Npc"], ["My Hero"]),
            ("bucket=all&type=NPC&body_only=true", ["Their Npc"], ["My Hero"]),
        ],
        ids=["all", "mine", "others", "type-filter"],
    )
    def test_campaign_roster_split_by_bucket_and_filters(
        self, client: FlaskClient, roster, query, shown, hidden
    ) -> None:
        """Verify the campaign roster splits by owner bucket and narrows by filters."""
        body = client.get(f"/cards/character-list?campaign_id={roster.id}&{query}").get_data(
            as_text=True
        )

        for name in shown:
            assert name in body
        for name in hidden:
            assert name not in body

    @pytest.mark.parametrize(
        ("query", "shows_type_filter"),
        [
            ("bucket=all", True),
            ("bucket=mine", False),
            ("bucket=all&show_filters=false", False),
        ],
        ids=["several-types", "one-type", "filters-off"],
    )
    def test_type_filter_offered_only_when_it_can_narrow(
        self, client: FlaskClient, roster, query, shows_type_filter
    ) -> None:
        """Verify the type filter shows only for a roster with several types, unless turned off."""
        body = client.get(
            f"/cards/character-list?campaign_id={roster.id}&show_type=true&{query}"
        ).get_data(as_text=True)

        assert ('name="type"' in body) is shows_type_filter

    def test_user_scope_lists_every_character_the_user_owns(
        self, client: FlaskClient, use_context
    ) -> None:
        """Verify user scope lists the user's characters of any type, and no one else's.

        The API already scopes the roster by role, so the card applies no type filtering.
        """
        use_context(
            user_role="PLAYER",
            characters=[
                CharacterFactory.build(name="Owned Player", user_player_id="u-1"),
                CharacterFactory.build(
                    name="Owned Story", type="STORYTELLER", user_player_id="u-1"
                ),
                CharacterFactory.build(name="Not Owned", user_player_id="u-2"),
            ],
        )

        response = client.get("/cards/character-list?user_id=u-1")

        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Owned Player" in body
        assert "Owned Story" in body
        assert "Not Owned" not in body

    def test_profile_links_skip_ownerless_npc(self, client: FlaskClient, use_context) -> None:
        """Verify an NPC with no owner renders without a profile link instead of failing."""
        campaign = CampaignFactory.build()
        npc = CharacterFactory.build(
            name="Ownerless Npc", type="NPC", user_player_id=None, campaign_id=campaign.id
        )
        use_context(user_role="PLAYER", campaign=campaign, characters=[npc])

        response = client.get(
            f"/cards/character-list?campaign_id={campaign.id}&bucket=all&link_user_profile=true"
        )

        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Ownerless Npc" in body
        assert "/profile/None" not in body
