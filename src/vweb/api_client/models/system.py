"""Pydantic models for System API responses."""

from pydantic import BaseModel


class SystemHealth(BaseModel):
    """Response model for system health check.

    Represents the health status of the API and its dependencies including
    database and cache connectivity, latency metrics, and uptime information.
    """

    database_status: str
    cache_status: str
    database_latency_ms: float | None
    cache_latency_ms: float | None
    uptime: str
    version: str
