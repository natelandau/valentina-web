"""Build API response payloads and read back what the client sent."""

import json

import respx
from pydantic import BaseModel


def wire(model: BaseModel) -> dict:
    """Return the JSON payload the API would send for a model.

    Args:
        model: The model, usually built by a factory, to serialize.

    Returns:
        The model as a JSON-compatible dict.
    """
    return model.model_dump(mode="json")


def page(
    *models: BaseModel | dict,
    limit: int = 10,
    offset: int = 0,
    total: int | None = None,
) -> dict:
    """Return a paginated response payload holding the given models.

    Args:
        *models: The page's items, as models or payloads already in wire form.
        limit: The page size the response reports.
        offset: The offset the response reports.
        total: The total item count the response reports; defaults to the number of items.

    Returns:
        The paginated response as a JSON-compatible dict.
    """
    return {
        "items": [model if isinstance(model, dict) else wire(model) for model in models],
        "limit": limit,
        "offset": offset,
        "total": len(models) if total is None else total,
    }


def endpoint_url(base_url: str, endpoint: str, **ids: str) -> str:
    """Return the full URL for an endpoint with its path ids filled in.

    Args:
        base_url: The API base URL.
        endpoint: The endpoint pattern, such as ``Endpoints.USER``.
        **ids: Values for the pattern's path parameters; unused ones are ignored.

    Returns:
        The absolute URL a mocked route should match.
    """
    return f"{base_url}{endpoint.format(**ids)}"


def sent_json(route: respx.Route) -> dict | list:
    """Return the JSON body of the last request a mocked route received.

    Args:
        route: The respx route the client called.

    Returns:
        The decoded request body.
    """
    return json.loads(route.calls.last.request.content)


def sent_params(route: respx.Route) -> dict[str, str]:
    """Return the query parameters of the last request a mocked route received.

    Args:
        route: The respx route the client called.

    Returns:
        The query parameters, one value per name.
    """
    return dict(route.calls.last.request.url.params)
