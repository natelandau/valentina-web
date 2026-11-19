"""Duty tasks for the project."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import dotenv_values
from duty import duty
from rich.console import Console

if TYPE_CHECKING:
    from duty.context import Context


console = Console()
PROJECT_ROOT = Path(__file__).parent.resolve()
# duty loads this file by path, so the project root is not importable until added
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.worktree import (  # noqa: E402
    CONTAINER_REDIS_PASSWORD,
    ENV_FILE,
    KEY_PORT,
    KEY_REDIS_URL,
    LocalRedis,
    dev_redis_error,
    redis_db,
    targets_api_redis,
)


def _main_checkout() -> Path:
    """Return the main checkout, which is PROJECT_ROOT unless this file runs from a worktree."""
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],  # noqa: S607
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()).parent.resolve() if result.returncode == 0 else PROJECT_ROOT


# Every worktree shares the main checkout's Redis container, so compose always runs against its file
MAIN_ROOT = _main_checkout()
IN_WORKTREE = PROJECT_ROOT != MAIN_ROOT
WORKTREE_SCRIPT = ["uv", "run", "python", "-m", "scripts.worktree"]
MAIN_WORKTREE_SCRIPT = [
    "uv",
    "run",
    "--project",
    str(MAIN_ROOT),
    "python",
    "-m",
    "scripts.worktree",
]

PY_SRC_PATHS = (Path(_) for _ in ("src/", "tests/", "duties.py", "scripts/") if Path(_).exists())
PY_SRC_LIST = tuple(str(_) for _ in PY_SRC_PATHS)
CI = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}
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


def gated(
    name: str, cmd: list[str], paths: tuple[str, ...] = (), junit: str | None = None
) -> list[str]:
    """Wrap a gate command in gate-cache so it skips on a tree where it already passed.

    Args:
        name (str): Marker name for the gate.
        cmd (list[str]): Command to run.
        paths (tuple[str, ...]): Git pathspecs the gate reads. A change outside them
            does not rerun the gate. Empty keys the gate on the whole tree.
        junit (str | None): JUnit XML report the command writes, recorded per test when
            gate-cache stats are on.

    Returns:
        list[str]: The command prefixed with the gate-cache invocation.
    """
    path_args = [arg for path in paths for arg in ("--path", path)]
    junit_args = ["--junit", junit] if junit else []
    return ["gate-cache", "--name", name, *path_args, *junit_args, "--", *cmd]


def compose(*args: str) -> list[str]:
    """Build a `docker compose` command for the main checkout's dev Redis container.

    Args:
        *args: Compose subcommand and its arguments.

    Returns:
        list[str]: The full command.
    """
    return [*LocalRedis(MAIN_ROOT).compose, *args]


def local_redis_url() -> str | None:
    """Return the `VWEB_REDIS__URL` the dev server will use, or None when unset.

    An exported variable wins over the env file, matching pydantic-settings. A blank value is
    returned as "", which the app reads as "no Redis".
    """
    if KEY_REDIS_URL in os.environ:
        return os.environ[KEY_REDIS_URL]
    return dotenv_values(PROJECT_ROOT / ENV_FILE).get(KEY_REDIS_URL)


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
        gated("ruff", ["ruff", "check", "--config", "pyproject.toml", "--no-fix", *PY_SRC_LIST]),
        title=pyprefix("code quality check"),
    )


@duty
def format(ctx: Context) -> None:  # noqa: A001
    """Format the code with ruff."""
    ctx.run(
        gated("format", ["ruff", "format", "--check", "--config", "pyproject.toml", *PY_SRC_LIST]),
        title=pyprefix("code formatting"),
    )


@duty
def ty(ctx: Context) -> None:
    """Type check the code with ty."""
    ctx.run(
        gated("ty", ["ty", "check", "src/"]),
        title="ty check",
    )


@duty
def typos(ctx: Context) -> None:
    """Check the code with typos."""
    ctx.run(
        gated("typos", ["typos", "--config", ".typos.toml"]),
        title=pyprefix("typos check"),
    )


@duty(skip_if=CI, skip_reason="skip prek in CI environments")
def precommit(ctx: Context) -> None:
    """Run prek hooks."""
    ctx.run(
        "PREK_SKIP=ruff,ruff-format,ty,typos,pytest gate-cache --name prek -- prek run --all-files",
        title=pyprefix("prek hooks"),
    )


@duty(pre=[ruff, format, ty, typos, precommit], capture=CI)
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


_SHARED_TEST_INPUTS = ("duties.py", "pyproject.toml", "uv.lock")
# scope: (pytest targets, gate-cache pathspecs). Web code calls the API client, so the
# web gate watches all of src/. The client tests also load the root test support files.
# The web and client targets match the test matrix in .github/workflows/reusable-tests.yml.
TEST_SCOPES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "all": (
        ("tests/",),
        ("src/", "scripts/", "tests/", *_SHARED_TEST_INPUTS),
    ),
    "web": (
        ("tests/", "--ignore=tests/api_client"),
        ("src/", "scripts/", "tests/", ":(exclude)tests/api_client", *_SHARED_TEST_INPUTS),
    ),
    "client": (
        ("tests/api_client/",),
        (
            "src/vweb/api_client/",
            "tests/api_client/",
            "tests/__init__.py",
            "tests/conftest.py",
            "tests/helpers.py",
            *_SHARED_TEST_INPUTS,
        ),
    ),
}


COVERAGE_FLOOR = 99


@duty()
def test(ctx: Context, *cli_args: str, scope: str = "all") -> None:  # noqa: PT028 (a duty, not a pytest test)
    """Run the tests for web code, API client code, or both, and report coverage.

    Each scope caches its pass against only the files its tests read, so editing
    web code does not rerun the API client tests.

    Usage: duty test [scope=all|web|client] [pytest args]

    Args:
        ctx (Context): The duty context.
        *cli_args (str): Extra pytest arguments. Any argument turns off the cache.
        scope (str): `web`, `client`, or `all` (default).

    Raises:
        ValueError: If `scope` is not a known scope.
    """
    if scope not in TEST_SCOPES:
        msg = f"Unknown test scope {scope!r}, expected one of: {', '.join(TEST_SCOPES)}"
        raise ValueError(msg)
    targets, paths = TEST_SCOPES[scope]
    junit = f".cache/junit-{scope}.xml"
    cmd = [
        "pytest",
        *targets,
        "-c",
        "pyproject.toml",
        "--color=yes",
        "--numprocesses=auto",
        "--cov",
        "--cov-config=pyproject.toml",
        "--cov-report=xml",
        "--cov-report=term",
        f"--junitxml={junit}",
        # Filtered runs and single scopes cover only part of src/, so only a full run is held to the floor
        *([f"--cov-fail-under={COVERAGE_FLOOR}"] if scope == "all" and not cli_args else []),
        *cli_args,
    ]
    # A marker covers the name, not the arguments, so a filtered pass must not skip the full suite
    ctx.run(
        cmd if cli_args else gated(f"test-{scope}", cmd, paths, junit=junit),
        title=pyprefix(f"Running {scope} tests"),
        capture=CI,
    )


@duty()
def validate_constants(ctx: Context, company_id: str = "") -> None:
    """Validate the API client constants against the live API.

    Usage: duty validate_constants company_id=<id>
    """
    cmd = ["uv", "run", "python", "scripts/validate_constants.py"]
    if company_id:
        cmd += ["--company-id", company_id]
    ctx.run(cmd, title="validate constants")


def _ensure_npm_deps(ctx: Context) -> None:
    """Install npm dependencies if node_modules is missing.

    `npx @tailwindcss/cli` only fetches the CLI package itself, not the
    project's own package.json deps (tailwindcss, daisyui) that input.css
    resolves against, so a fresh clone fails without this.
    """
    if not (PROJECT_ROOT / "node_modules").exists():
        ctx.run(["npm", "install"], title="npm install", capture=False)


@duty(pre=[dev_clean])
def dev_setup(ctx: Context) -> None:
    """Setup the development environment."""
    for directory in DEV_DIRECTORIES:
        if not directory.exists():
            directory.mkdir(parents=True)

    _ensure_npm_deps(ctx)

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
def redis_up(ctx: Context) -> None:
    """Start the dev Redis container if needed, and in a worktree, claim its Redis database."""
    if IN_WORKTREE:
        # Exported values beat .env.secret, so they would undo the worktree's own slot
        if overridden := [key for key in (KEY_REDIS_URL, KEY_PORT) if key in os.environ]:
            console.print(
                f"[red]Unset {', '.join(overridden)} in this shell: it overrides the worktree's "
                f"{ENV_FILE}.[/red]"
            )
            raise SystemExit(1)
        # provision starts the container itself
        ctx.run([*WORKTREE_SCRIPT, "provision"], title="provision worktree", capture=False)
        return
    ctx.run(compose("up", "-d", "--wait"), title="start dev Redis container")
    if targets_api_redis(url := local_redis_url()):
        console.print(f"[red]{dev_redis_error(url)}[/red]")
        raise SystemExit(1)
    if url and (message := dev_redis_error(url)):
        console.print(f"[yellow]Warning: {message}[/yellow]")


@duty()
def redis_down(ctx: Context) -> None:
    """Stop the dev Redis container that every worktree shares, keeping its data."""
    ctx.run(compose("stop"), title="stop dev Redis container")


@duty(pre=[redis_up])
def redis_cli(ctx: Context) -> None:
    """Open a redis-cli shell on this checkout's Redis database."""
    url = local_redis_url()
    # The shell opens on the dev container, so any other URL would show the wrong data
    if not IN_WORKTREE and (message := dev_redis_error(url)):
        console.print(f"[red]{message}[/red]")
        raise SystemExit(1)
    ctx.run(
        compose(
            "exec",
            "redis",
            "redis-cli",
            "-a",
            CONTAINER_REDIS_PASSWORD,
            "--no-auth-warning",
            "-n",
            str(redis_db(url) if url else 0),
        ),
        title="redis-cli",
        capture=False,
    )


@duty(pre=[redis_up])
def run(ctx: Context) -> None:
    """Run the Quart dev server and Tailwind CSS watcher."""
    for directory in DEV_DIRECTORIES:
        if not directory.exists():
            directory.mkdir(parents=True)

    _ensure_npm_deps(ctx)

    ctx.run(
        ["uv", "run", str(PROJECT_ROOT / "scripts" / "dev_server.py")],
        title="dev server",
        capture=False,
    )


@duty()
def css(ctx: Context) -> None:
    """Build the Tailwind CSS output (minified for production)."""
    _ensure_npm_deps(ctx)

    ctx.run(
        "npx @tailwindcss/cli -i src/vweb/static/css/input.css -o src/vweb/static/css/style.css --minify",
        title="build css",
        capture=False,
    )


@duty()
def worktree(ctx: Context, branch: str) -> None:
    """Create .worktrees/<branch> with its own Redis database and dev server port.

    Args:
        ctx: The duty context.
        branch: The new branch, which also names the worktree directory.
    """
    path = MAIN_ROOT / ".worktrees" / branch
    # This checkout's script, not the new worktree's: a branch cut from an older commit may lack it
    with ctx.cd(str(MAIN_ROOT)):
        ctx.run(
            [*MAIN_WORKTREE_SCRIPT, "create", branch],
            title=f"create worktree {branch}",
            capture=False,
        )
        ctx.run(
            [*MAIN_WORKTREE_SCRIPT, "provision", str(path)],
            title="provision worktree",
            capture=False,
        )
    with ctx.cd(str(path)):
        ctx.run(["uv", "sync"], title="install worktree Python dependencies")
        ctx.run(["npm", "install"], title="install worktree npm dependencies")
    worktree_prune(ctx)
    console.print(f"\n[green]✓[/green] Worktree ready. Start it with: cd {path} && duty run")


@duty()
def worktree_teardown(ctx: Context, branch: str = "") -> None:
    """Remove a worktree and flush its Redis database; the branch is kept.

    Args:
        ctx: The duty context.
        branch: The worktree's branch. Defaults to the worktree this runs in.
    """
    if branch:
        target = MAIN_ROOT / ".worktrees" / branch
    elif IN_WORKTREE:
        target = PROJECT_ROOT
    else:
        console.print(
            "[red]Name the worktree to remove: duty worktree-teardown branch=<branch>[/red]"
        )
        raise SystemExit(1)
    # The worktree directory disappears, so move to the main checkout for good rather than
    # with ctx.cd, which would change back into the deleted directory afterward
    os.chdir(MAIN_ROOT)
    ctx.run(
        [*MAIN_WORKTREE_SCRIPT, "teardown", str(target)],
        title=f"tear down worktree {target.name}",
    )


@duty()
def worktree_prune(ctx: Context) -> None:
    """Flush the Redis databases of worktrees that no longer exist."""
    with ctx.cd(str(MAIN_ROOT)):
        ctx.run([*MAIN_WORKTREE_SCRIPT, "prune"], title="prune Redis of removed worktrees")
