"""Tests for character trait-edit route permission enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock

from vclient.testing import CharacterFactory

from tests.conftest import get_csrf
from tests.helpers import build_global_context


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
        mocker.patch("vweb.lib.hooks.load_global_context", return_value=ctx)

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
