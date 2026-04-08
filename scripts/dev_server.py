# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Start the Flask dev server and Tailwind CSS watcher side by side.

Handles SIGINT, SIGTERM, and SIGHUP to ensure all child process trees
are cleaned up — no ghost processes after Ctrl-C or terminal close.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FLASK_CMD = ["uv", "run", "vweb"]
TAILWIND_CMD = [
    "npx",
    "@tailwindcss/cli",
    "-i",
    "src/vweb/static/css/input.css",
    "-o",
    "src/vweb/static/css/style.css",
    "--watch",
    "--optimize",
]

procs: list[subprocess.Popen[bytes]] = []


def kill_all() -> None:
    """Send SIGTERM to each subprocess process group, then SIGKILL stragglers."""
    for proc in procs:
        if proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def handle_signal(signum: int, _frame: object) -> None:
    """Clean up on SIGTERM / SIGHUP, then exit with the conventional code."""
    kill_all()
    sys.exit(128 + signum)


def main() -> None:
    """Launch both processes and wait."""
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGHUP, handle_signal)

    popen_kwargs: dict[str, object] = {
        "cwd": str(PROJECT_ROOT),
        "start_new_session": True,
    }

    try:
        procs.append(subprocess.Popen(FLASK_CMD, **popen_kwargs))  # noqa: S603
        procs.append(subprocess.Popen(TAILWIND_CMD, **popen_kwargs))  # noqa: S603
        print("✓ Started Flask server and Tailwind watcher")  # noqa: T201
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        kill_all()


if __name__ == "__main__":
    main()
