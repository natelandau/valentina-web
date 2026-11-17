"""Build API response payloads from model instances."""

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
