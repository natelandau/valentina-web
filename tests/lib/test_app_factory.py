"""Tests for the vweb entry point's production launch command."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from vweb import app as app_module
from vweb.config import RedisSettings

if TYPE_CHECKING:
    from vweb.config import Settings


@pytest.fixture
def launch(mocker, test_settings: Settings):
    """Run main() in production with gunicorn stubbed, returning the command it would run."""

    def _launch(**overrides: object) -> list[str]:
        settings = test_settings.model_copy(
            update={
                "env": "production",
                "force_https": False,
                "redis": RedisSettings(url="redis://127.0.0.1:6380/0"),
                "workers": 3,
                **overrides,
            }
        )
        mocker.patch.object(app_module, "get_settings", return_value=settings)
        call = mocker.patch("subprocess.call", return_value=0)
        with pytest.raises(SystemExit):
            app_module.main()
        return call.call_args.args[0]

    return _launch


def test_production_runs_gunicorn_on_the_configured_bind(launch) -> None:
    """Verify production serves the app factory through gunicorn on the configured address."""
    cmd = launch(host="0.0.0.0", port=9000)  # noqa: S104

    assert cmd[0] == "gunicorn"
    assert cmd[cmd.index("--bind") + 1] == "0.0.0.0:9000"
    assert cmd[cmd.index("--workers") + 1] == "3"
    assert cmd[-1] == "vweb:create_app()"


@pytest.mark.parametrize(
    ("ip_header", "expected_atom"),
    [(None, None), ("CF-Connecting-IP", "%({CF-Connecting-IP}i)s")],
)
def test_access_log_reads_client_ip_from_configured_header(
    launch, ip_header: str | None, expected_atom: str | None
) -> None:
    """Verify the access log uses the proxy's client-IP header only when one is configured."""
    cmd = launch(access_log_ip_header=ip_header)

    if expected_atom is None:
        assert "--access-logformat" not in cmd
    else:
        assert cmd[cmd.index("--access-logformat") + 1].startswith(expected_atom)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only fork-safety workaround")
def test_macos_launch_disables_control_socket(launch) -> None:
    """Verify local production runs on macOS keep the gunicorn master fork-safe."""
    assert "--no-control-socket" in launch()
