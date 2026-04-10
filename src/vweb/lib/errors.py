"""Centralized error handlers for the application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_wtf.csrf import CSRFError
from loguru import logger

if TYPE_CHECKING:
    from flask import Flask
    from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask) -> None:
    """Register custom error handlers on the Flask application.

    Args:
        app: The Flask application instance.
    """
    from vweb.app import catalog

    @app.errorhandler(CSRFError)
    def csrf_error(error: CSRFError) -> tuple[str, int]:
        """Return 400 for CSRF validation failures rather than letting them bubble to 500."""
        return catalog.render(
            "errors.ErrorPage",
            code=400,
            title="Bad Request",
            message=str(error.description),
        ), 400

    @app.errorhandler(404)
    def not_found(error: HTTPException) -> tuple[str, int]:  # noqa: ARG001
        return catalog.render(
            "errors.ErrorPage",
            code=404,
            title="Page Not Found",
            message="The page you're looking for doesn't exist or has been moved.",
        ), 404

    @app.errorhandler(400)
    def bad_request(error: HTTPException) -> tuple[str, int]:  # noqa: ARG001
        return catalog.render(
            "errors.ErrorPage",
            code=400,
            title="Bad Request",
            message="The server could not understand the request.",
        ), 400

    @app.errorhandler(403)
    def forbidden(error: HTTPException) -> tuple[str, int]:  # noqa: ARG001
        return catalog.render(
            "errors.ErrorPage",
            code=403,
            title="Forbidden",
            message="You don't have permission to access this resource.",
        ), 403

    @app.errorhandler(500)
    def server_error(error: HTTPException) -> tuple[str, int]:  # noqa: ARG001
        return catalog.render(
            "errors.ErrorPage",
            code=500,
            title="Server Error",
            message="Something went wrong on our end. Please try again later.",
        ), 500

    @app.errorhandler(Exception)
    def unhandled_exception(error: Exception) -> tuple[str, int]:
        logger.exception("Unhandled exception: {error}", error=error)
        return catalog.render(
            "errors.ErrorPage",
            code=500,
            title="Server Error",
            message="Something went wrong on our end. Please try again later.",
        ), 500
