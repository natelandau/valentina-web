"""Tests for FakeVClient's response sequencing and body-subset assertions."""

import pytest

from vweb.api_client.exceptions import APIConnectionError, APIError, NotFoundError
from vweb.api_client.registry import campaigns_service
from vweb.api_client.testing import (
    CampaignFactory,
    FakeConnectionError,
    FakeError,
    FakeResponse,
    FakeVClient,
    Routes,
)

_BODY = {"name": "Ada", "settings": {"xp": 3, "mode": "fast"}}


@pytest.mark.parametrize(
    ("body", "json_subset", "matches"),
    [
        pytest.param(_BODY, {"name": "Ada"}, True, id="top-level-key"),
        pytest.param(_BODY, {"settings": {"xp": 3}}, True, id="nested-subset"),
        pytest.param(_BODY, {"settings": {"xp": 4}}, False, id="nested-value-differs"),
        pytest.param(_BODY, {"missing": 1}, False, id="key-absent"),
        pytest.param(_BODY, {"name": "Bob"}, False, id="value-differs"),
        pytest.param(None, {"name": "Ada"}, False, id="no-json-body"),
    ],
)
def test_json_subset_matches_nested_keys(
    body: dict | None,
    json_subset: dict,
    matches: bool,  # noqa: FBT001
) -> None:
    """Verify json_subset passes only when every key, nested ones too, carries the given value."""
    with FakeVClient() as client:
        path = Routes.CAMPAIGNS_UPDATE.pattern.format(company_id="co1", campaign_id="c1")
        client._http.patch(path, json=body)

        if matches:
            client.assert_called(Routes.CAMPAIGNS_UPDATE, json_subset=json_subset)
        else:
            with pytest.raises(AssertionError, match="found 0"):
                client.assert_called(Routes.CAMPAIGNS_UPDATE, json_subset=json_subset)


@pytest.mark.parametrize(
    ("failure", "expected_exception"),
    [
        pytest.param(FakeError(status_code=404), NotFoundError, id="error"),
        pytest.param(FakeConnectionError(), APIConnectionError, id="connection-error"),
    ],
)
def test_no_content_route_can_succeed_after_a_failure(
    failure: FakeError | FakeConnectionError, expected_exception: type[APIError]
) -> None:
    """Verify a delete route can fail first and then succeed, as a retry flow expects."""
    with FakeVClient() as client:
        client.set_responses(Routes.CAMPAIGNS_DELETE, [failure, FakeResponse()])
        service = campaigns_service("acting-user")

        with pytest.raises(expected_exception):
            service.delete("c1")
        service.delete("c1")

        client.assert_called(Routes.CAMPAIGNS_DELETE, times=2)


def test_connection_error_is_raised_and_recorded() -> None:
    """Verify set_connection_error makes the client raise and still records the request."""
    with FakeVClient() as client:
        client.set_connection_error(Routes.CAMPAIGNS_GET)

        with pytest.raises(APIConnectionError):
            campaigns_service("acting-user").get("c1")

        client.assert_called(Routes.CAMPAIGNS_GET, params={"campaign_id": "c1"}, times=1)


@pytest.mark.parametrize(
    ("total", "offset", "expected_total", "has_more"),
    [
        pytest.param(None, 0, 2, False, id="defaults-to-last-page"),
        pytest.param(5, 2, 5, True, id="more-pages-remain"),
    ],
)
def test_paginated_response_reports_total_and_offset(
    total: int | None,
    offset: int,
    expected_total: int,
    has_more: bool,  # noqa: FBT001
) -> None:
    """Verify set_response's total and offset reach the page the service returns."""
    with FakeVClient() as client:
        client.set_response(
            Routes.CAMPAIGNS_LIST, items=CampaignFactory.batch(2), total=total, offset=offset
        )

        result = campaigns_service("acting-user").get_page()

        assert result.total == expected_total
        assert result.offset == offset
        assert result.has_more is has_more
