"""Duty tasks for the project."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from duty import duty, tools
from rich.console import Console

if TYPE_CHECKING:
    from duty.context import Context


console = Console()

PY_SRC_PATHS = (Path(_) for _ in ("src/", "tests/", "duties.py", "scripts/") if Path(_).exists())
PY_SRC_LIST = tuple(str(_) for _ in PY_SRC_PATHS)
CI = os.environ.get("CI", "0") in {"1", "true", "yes", ""}
PROJECT_ROOT = Path(__file__).parent
DEV_DIR = PROJECT_ROOT / ".dev"
DEV_DIRECTORIES = []


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from a string.

    Args:
        text (str): String to remove ANSI escape sequences from.

    Returns:
        str: String without ANSI escape sequences.
    """
    ansi_chars = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")

    # Replace [ with \[ so rich doesn't interpret output as style tags
    return ansi_chars.sub("", text).replace("[", r"\[")


def pyprefix(title: str) -> str:
    """Add a prefix to the title if CI is true.

    Returns:
        str: Title with prefix if CI is true.
    """
    if CI:
        prefix = f"(python{sys.version_info.major}.{sys.version_info.minor})"
        return f"{prefix:14}{title}"
    return title


@duty()
def dev_clean(ctx: Context) -> None:  # noqa: ARG001
    """Clean the development environment."""
    for directory in DEV_DIRECTORIES:
        if directory.exists():
            shutil.rmtree(directory)
            console.print(f"✓ Cleaned dev env in '{directory.name}/'")


@duty(silent=True, post=[dev_clean])
def clean(ctx: Context) -> None:
    """Clean the project."""
    ctx.run("rm -rf .coverage*")
    ctx.run("rm -rf .cache")
    ctx.run("rm -rf build")
    ctx.run("rm -rf dist")
    ctx.run("rm -rf pip-wheel-metadata")
    ctx.run("rm *.log")
    ctx.run("rm *.rdb")
    ctx.run("find . -type d -name __pycache__ | xargs rm -rf")
    ctx.run("find . -name '.DS_Store' -delete")


@duty
def ruff(ctx: Context) -> None:
    """Check the code quality with ruff."""
    ctx.run(
        tools.ruff.check(*PY_SRC_LIST, fix=False, config="pyproject.toml"),
        title=pyprefix("code quality check"),
        command=f"ruff check --config pyproject.toml --no-fix {' '.join(PY_SRC_LIST)}",
    )


@duty
def format(ctx: Context) -> None:  # noqa: A001
    """Format the code with ruff."""
    ctx.run(
        tools.ruff.format(*PY_SRC_LIST, check=True, config="pyproject.toml"),
        title=pyprefix("code formatting"),
        command="ruff format --check --config pyproject.toml src/",
    )


@duty
def ty(ctx: Context) -> None:
    """Type check the code with ty."""
    ctx.run(
        ["ty", "check", "src/"],
        title="ty check",
        command="ty check src/",
    )


@duty
def typos(ctx: Context) -> None:
    """Check the code with typos."""
    ctx.run(
        ["typos", "--config", ".typos.toml"],
        title=pyprefix("typos check"),
        command="typos --config .typos.toml",
    )


@duty(skip_if=CI, skip_reason="skip prek in CI environments")
def precommit(ctx: Context) -> None:
    """Run prek hooks."""
    ctx.run(
        "PREK_SKIP=ty,pytest,ruff prek run --all-files",
        title=pyprefix("prek hooks"),
    )


@duty(pre=[ruff, ty, typos, precommit], capture=CI)
def lint(ctx: Context) -> None:
    """Run all linting duties."""


@duty(capture=CI)
def update(ctx: Context) -> None:
    """Update the project."""
    ctx.run(["uv", "lock", "--upgrade"], title="update uv lock")
    ctx.run(["uv", "sync"], title="update uv sync")
    ctx.run(["prek", "autoupdate"], title="prek autoupdate")
    ctx.run(["uvx", "uv-upx", "upgrade", "run"], title="uv-upx upgrade")
    ctx.run(["npm", "update", "--save"], title="update npm packages")


@duty()
def test(ctx: Context, *cli_args: str) -> None:
    """Test package and generate coverage reports."""
    ctx.run(
        tools.pytest(
            "tests/",
            config_file="pyproject.toml",
            color="yes",
        ).add_args(
            "--cov",
            "--cov-config=pyproject.toml",
            "--cov-report=xml",
            "--cov-report=term",
            *cli_args,
        ),
        title=pyprefix("Running tests"),
        capture=CI,
    )


@duty(pre=[dev_clean])
def dev_setup(ctx: Context) -> None:  # noqa: ARG001
    """Setup the development environment."""
    for directory in DEV_DIRECTORIES:
        if not directory.exists():
            directory.mkdir(parents=True)

    console.print(
        """
✓ Development environment setup complete.
  Start the development environment with one of the following commands:

  Run locally:
    [green]duty run[/green]

  Run everything from docker:
    [green]docker compose up --build[/green]
"""
    )


@duty()
def run(ctx: Context) -> None:
    """Run the Quart dev server and Tailwind CSS watcher."""
    for directory in DEV_DIRECTORIES:
        if not directory.exists():
            directory.mkdir(parents=True)

    ctx.run(
        ["uv", "run", str(PROJECT_ROOT / "scripts" / "dev_server.py")],
        title="dev server",
        capture=False,
    )


@duty()
def css(ctx: Context) -> None:
    """Build the Tailwind CSS output (minified for production)."""
    ctx.run(
        "npx @tailwindcss/cli -i src/vweb/static/css/input.css -o src/vweb/static/css/style.css --minify",
        title="build css",
        capture=False,
    )
