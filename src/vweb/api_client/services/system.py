"""Service for interacting with the System API."""

from vweb.api_client.models.system import SystemHealth
from vweb.api_client.routes import Routes
from vweb.api_client.services.base import BaseService


class SystemService(BaseService):
    """Service for system-level operations in the Valentina API.

    Provides methods to check system health and status. This service is
    designed to grow with additional system endpoints over time.

    Example:
        with VClient(base_url=url, api_key=key) as client:
            health = client.system.health()
            print(health.database_status)
    """

    def health(self) -> SystemHealth:
        """Check the health status of the API and its dependencies.

        Verify that the API server, database, and cache are operational. This endpoint
        does not require authentication and is useful for monitoring and health checks.

        Returns:
            SystemHealth object containing the status of database and cache connections,
            as well as the current API version.

        Example:
            health = client.system.health()
            if health.database_status == "online":
                print("Database is healthy")
        """
        return self._call(Routes.HEALTH_GET)
