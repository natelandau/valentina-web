"""Dev-only: give each git worktree its own Redis logical database and dev server port.

Dev servers in separate worktrees run at the same time, and sharing one Redis database lets a
branch's cached data or sessions leak into another's. Each worktree instead claims a slot: its
own Redis logical database on this repo's dev Redis container (`compose-db.yml`) and the main
checkout's port plus the slot, both recorded in its `.env.secret`. The container listens on
port 6380 so no checkout ever touches the API's Redis on 6379.

Run as a module from the checkout it acts on:

    uv run python -m scripts.worktree create BRANCH    # from the main checkout
    uv run python -m scripts.worktree provision        # from inside a worktree
    uv run python -m scripts.worktree prune
    uv run python -m scripts.worktree teardown [PATH]
"""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import click
from dotenv import dotenv_values
from rich.console import Console

console = Console()

ENV_FILE = ".env.secret"
# Local files a worktree needs that git does not carry: they are ignored in every checkout
COPIED_FILES = (ENV_FILE, "CLAUDE.local.md")
COMPOSE_FILE = "compose-db.yml"
# Each slot needs its own OAuth callback URL registered with every provider
MAX_WORKTREES = 5
DEV_REDIS_PORT = 6380
# Port of the Redis that valentina-noir runs, and the default of vweb.config.RedisSettings.url
API_REDIS_PORT = 6379
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})  # noqa: S104

# Must match vweb.config.Settings, which cannot be built without a complete .env.secret
DEFAULT_PORT = 8089

# Credentials compose-db.yml gives the container
CONTAINER_REDIS_PASSWORD = "redispassword"  # noqa: S105
DEV_REDIS_URL = f"redis://:{CONTAINER_REDIS_PASSWORD}@127.0.0.1:{DEV_REDIS_PORT}/0"

KEY_REDIS_URL = "VWEB_REDIS__URL"
KEY_PORT = "VWEB_PORT"


@dataclass(frozen=True)
class MainSettings:
    """The main checkout's Redis URL and port that every worktree derives its own from."""

    redis_url: str | None
    port: int

    @classmethod
    def load(cls, main: Path) -> "MainSettings":
        """Read the main checkout's `.env.secret`, falling back to the application defaults.

        Args:
            main (Path): The main checkout.

        Returns:
            MainSettings: The main checkout's settings.
        """
        env = read_env(main / ENV_FILE)
        return cls(redis_url=env.get(KEY_REDIS_URL), port=int(env.get(KEY_PORT, DEFAULT_PORT)))

    @property
    def redis_db(self) -> int:
        """The Redis logical database the main checkout uses."""
        return redis_db(self.redis_url) if self.redis_url else 0

    def port_for(self, slot: int) -> int:
        """Return the dev server port for a worktree holding this slot."""
        return self.port + slot


def read_env(env_file: Path) -> dict[str, str]:
    """Read an env file without building Settings, which may refuse a half-configured file."""
    if not env_file.exists():
        return {}
    # A blank value means unset, matching how the app falls back to its default
    return {key: value for key, value in dotenv_values(env_file).items() if value}


def rewrite_env(env_file: Path, values: dict[str, str]) -> None:
    """Set each key in an env file in place, keeping every other line and comment.

    Args:
        env_file (Path): The env file to edit.
        values (dict[str, str]): Keys to set, appended when the file lacks them.
    """
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        # dotenv honors an `export ` prefix, so an exported duplicate is live too
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        # Rewrite every occurrence: dotenv keeps the last one, so a stale duplicate would win
        if key in values:
            lines[index] = f"{key}={values[key]}"
            seen.add(key)
    lines.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def redis_db(url: str) -> int:
    """Return the logical database a Redis URL selects, which is 0 when the URL names none."""
    path = urlsplit(url).path.strip("/")
    if not path:
        return 0
    if not path.isdigit():
        sys.exit(f"{KEY_REDIS_URL} must end in a numeric database such as /0, not /{path}")
    return int(path)


def with_redis_db(url: str, database: int) -> str:
    """Return the same Redis URL pointed at another logical database."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def dev_redis_error(url: str | None) -> str | None:
    """Explain why a Redis URL is not this repo's dev container, so no tool acts on another Redis.

    Args:
        url (str | None): The main checkout's `VWEB_REDIS__URL`, or None when unset.

    Returns:
        str | None: None when the URL targets the dev container, else a message with the fix.
    """
    if url:
        parts = urlsplit(url)
        try:
            port = parts.port
        except ValueError:
            port = None
        if parts.hostname in LOCAL_HOSTS and port == DEV_REDIS_PORT:
            return None
    # Never echo the URL itself: it may carry a password
    if url is None:
        found = f"unset, so the app falls back to port {API_REDIS_PORT}"
    else:
        found = "set to another Redis" if url else "blank, so the app uses no Redis"
    return (
        f"the main checkout's {KEY_REDIS_URL} is {found}, not the dev Redis container on "
        f"port {DEV_REDIS_PORT}. Add this line to the main checkout's {ENV_FILE}:\n"
        f"{KEY_REDIS_URL}={DEV_REDIS_URL}"
    )


def targets_api_redis(url: str | None) -> bool:
    """Return whether a dev server with this URL would use the API's Redis on local port 6379.

    An unset URL counts, because the app falls back to `redis://127.0.0.1:6379/0`. A blank URL
    does not: the app then uses an in-memory cache and no Redis at all.
    """
    if url is None:
        return True
    if not url:
        return False
    parts = urlsplit(url)
    try:
        port = parts.port or API_REDIS_PORT
    except ValueError:
        return False
    return parts.hostname in LOCAL_HOSTS and port == API_REDIS_PORT


def slot_of(env: dict[str, str], main: MainSettings) -> int | None:
    """Return the slot a worktree's env already claims, or None when it still mirrors main's.

    A worktree's slot is its Redis logical database; its port is main's port plus the slot.
    """
    if KEY_REDIS_URL not in env:
        return None
    database = redis_db(env[KEY_REDIS_URL])
    return None if database in {0, main.redis_db} else database


def free_slots(taken: set[int], main: MainSettings) -> list[int]:
    """List the slots no live worktree holds, lowest first, never main's Redis database."""
    return [
        slot for slot in range(1, MAX_WORKTREES + 1) if slot not in taken and slot != main.redis_db
    ]


def choose_slot(current: int | None, taken: set[int], main: MainSettings) -> int:
    """Keep a worktree's slot when it is still free and in range, else take the lowest free one.

    Args:
        current (int | None): The slot the worktree's env already claims.
        taken (set[int]): Slots other live worktrees hold.
        main (MainSettings): The main checkout's settings, whose Redis database is never a slot.

    Returns:
        int: The worktree's slot.
    """
    free = free_slots(taken, main)
    if current in free:
        return current
    if not free:
        sys.exit(
            f"no worktree slot is free (slots in use: {sorted(taken)}); "
            "tear one down first with `duty worktree-teardown branch=<branch>`"
        )
    return free[0]


@dataclass(frozen=True)
class Checkouts:
    """The main checkout and every linked worktree, as git records them."""

    main: Path
    worktrees: list[Path]

    @classmethod
    def discover(cls, cwd: Path) -> "Checkouts":
        """Read the checkouts of the repository that holds cwd from `git worktree list`.

        Args:
            cwd (Path): Any directory inside the repository.

        Returns:
            Checkouts: The main checkout and every linked worktree.
        """
        listing = _git(cwd, "worktree", "list", "--porcelain")
        paths = [
            Path(line.removeprefix("worktree "))
            for line in listing.splitlines()
            if line.startswith("worktree ")
        ]
        return cls(main=paths[0], worktrees=paths[1:])

    @property
    def live_worktrees(self) -> list[Path]:
        """Worktrees whose directory still exists; git lists deleted ones until pruned."""
        return [path for path in self.worktrees if path.exists()]


def _git(cwd: Path, *args: str) -> str:
    """Run git in cwd and return its output, exiting with git's message when it fails."""
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def toplevel(cwd: Path) -> Path:
    """Return the root of the checkout that holds cwd."""
    return Path(_git(cwd, "rev-parse", "--show-toplevel").strip())


class LocalRedis:
    """The dev Redis container, reached with `docker compose exec` against the main checkout."""

    def __init__(self, main: Path) -> None:
        # The container bind-mounts its data relative to the compose file, so a worktree's
        # copy would start a second container over empty data
        self.compose = ["docker", "compose", "-f", str(main / COMPOSE_FILE)]

    def up(self) -> None:
        """Start the container if it is not already running, quietly unless it fails."""
        result = subprocess.run(  # noqa: S603
            [*self.compose, "up", "-d", "--wait"], capture_output=True, text=True, check=False
        )
        if result.returncode:
            sys.exit(f"starting the dev Redis container failed: {result.stderr.strip()}")

    def _redis(self, database: int, *args: str) -> str:
        result = subprocess.run(  # noqa: S603
            [
                *self.compose,
                "exec",
                "-T",
                "redis",
                "redis-cli",
                "-a",
                CONTAINER_REDIS_PASSWORD,
                "--no-auth-warning",
                "-n",
                str(database),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            sys.exit(f"redis-cli {args[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def databases_with_keys(self) -> set[int]:
        """List the Redis logical databases that hold at least one key, in one round trip."""
        keyspace = self._redis(0, "INFO", "keyspace")
        return {int(match) for match in re.findall(r"^db(\d+):keys=[1-9]", keyspace, re.MULTILINE)}

    def flush(self, database: int) -> None:
        """Delete every key in a worktree's Redis logical database."""
        if database == 0:
            sys.exit("refusing to flush Redis database 0, which belongs to the main checkout")
        self._redis(database, "FLUSHDB")


def claimed_slots(
    checkouts: Checkouts, main: MainSettings, *, exclude: Path | None = None
) -> set[int]:
    """Return the slots live worktrees hold, leaving out `exclude`.

    Args:
        checkouts (Checkouts): The repository's checkouts.
        main (MainSettings): The main checkout's settings.
        exclude (Path | None): A worktree whose own slot does not count as taken.

    Returns:
        set[int]: The claimed slots.
    """
    return {
        slot
        for path in checkouts.live_worktrees
        if path != exclude and (slot := slot_of(read_env(path / ENV_FILE), main)) is not None
    }


def require_dev_redis(main: MainSettings) -> None:
    """Exit unless the main checkout points at the dev Redis container, never the API's."""
    if message := dev_redis_error(main.redis_url):
        sys.exit(message)


def copy_local_files(main: Path, worktree: Path) -> None:
    """Copy the main checkout's env and local instruction files into a worktree, replacing any there.

    Args:
        main (Path): The main checkout.
        worktree (Path): The worktree to copy into.
    """
    for name in COPIED_FILES:
        source = main / name
        if not source.exists():
            continue
        # A branch cut before a file was ignored would otherwise commit it
        ignored = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", name],  # noqa: S607
            cwd=worktree,
            check=False,
        )
        if ignored.returncode:
            console.print(f"[yellow]skipped {name}: this branch does not ignore it[/yellow]")
            continue
        # copy2 keeps the mode, so a private env file stays private
        shutil.copy2(source, worktree / name)
        console.print(f"copied {name}")


def create(cwd: Path, branch: str) -> Path:
    """Create `.worktrees/<branch>` on a new branch and copy in the main checkout's local files.

    Refuses before touching git when the dev Redis is not configured or every slot is taken,
    so a refused worktree leaves nothing behind.

    Args:
        cwd (Path): Any directory inside the repository.
        branch (str): The new branch, which also names the worktree directory.

    Returns:
        Path: The new worktree.
    """
    checkouts = Checkouts.discover(cwd)
    main = MainSettings.load(checkouts.main)
    require_dev_redis(main)
    choose_slot(None, claimed_slots(checkouts, main), main)
    path = checkouts.main / ".worktrees" / branch
    _git(checkouts.main, "worktree", "add", str(path), "-b", branch)
    console.print(f"created worktree {path} on branch {branch}")
    copy_local_files(checkouts.main, path)
    return path


def provision(cwd: Path) -> None:
    """Give the worktree that holds cwd its own Redis database and dev server port.

    Running it again keeps the slot already there and only re-points `.env.secret` at it.

    Args:
        cwd (Path): Any directory inside the worktree.
    """
    checkouts = Checkouts.discover(cwd)
    here = toplevel(cwd)
    if here == checkouts.main:
        sys.exit("this is the main checkout, which keeps Redis database 0; run this in a worktree")
    env_file = here / ENV_FILE
    if not env_file.exists():
        sys.exit(f"{env_file} is missing; create the worktree with `duty worktree`")

    main = MainSettings.load(checkouts.main)
    require_dev_redis(main)
    redis = LocalRedis(checkouts.main)
    redis.up()

    current = slot_of(read_env(env_file), main)
    slot = choose_slot(current, claimed_slots(checkouts, main, exclude=here), main)
    if slot != current:
        # A slot freed by a removed worktree may still hold its keys
        redis.flush(slot)

    port = main.port_for(slot)
    # require_dev_redis has exited unless main.redis_url is set
    rewrite_env(
        env_file,
        {KEY_REDIS_URL: with_redis_db(str(main.redis_url), slot), KEY_PORT: str(port)},
    )
    console.print(f"[green]✓[/green] {ENV_FILE} uses Redis database {slot} and port {port}")


def prune(cwd: Path) -> None:
    """Flush the Redis databases of worktrees that no longer exist.

    Args:
        cwd (Path): Any directory inside the repository.
    """
    checkouts = Checkouts.discover(cwd)
    main = MainSettings.load(checkouts.main)
    require_dev_redis(main)
    redis = LocalRedis(checkouts.main)
    redis.up()

    used = {0, main.redis_db} | claimed_slots(checkouts, main)
    for slot in sorted(redis.databases_with_keys() - used):
        redis.flush(slot)
        console.print(f"flushed Redis database {slot}")


def teardown(cwd: Path, target: Path | None) -> None:
    """Remove a worktree, then flush its Redis database.

    git refuses to remove a worktree with uncommitted changes or untracked files, and nothing
    is flushed then.

    Args:
        cwd (Path): Any directory inside the repository.
        target (Path | None): The worktree to remove, or the one that holds cwd.
    """
    checkouts = Checkouts.discover(cwd)
    worktree = target.resolve() if target else toplevel(cwd)
    if worktree == checkouts.main:
        sys.exit("this is the main checkout; name a worktree to tear down")
    if worktree not in checkouts.worktrees:
        sys.exit(f"{worktree} is not a worktree of this repository")

    main = MainSettings.load(checkouts.main)
    require_dev_redis(main)
    slot = slot_of(read_env(worktree / ENV_FILE), main)

    _git(checkouts.main, "worktree", "remove", str(worktree))
    console.print(f"removed worktree {worktree}")
    # A branch with a slash nests its worktree, and git leaves the emptied parents behind
    container = checkouts.main / ".worktrees"
    for parent in worktree.parents:
        if parent == container or not parent.is_relative_to(container) or any(parent.iterdir()):
            break
        parent.rmdir()

    # Another worktree may still claim this slot until its next provision moves it
    if slot is None or slot in claimed_slots(checkouts, main, exclude=worktree):
        return
    redis = LocalRedis(checkouts.main)
    redis.up()
    redis.flush(slot)
    console.print(f"flushed Redis database {slot}")


@click.group()
def cli() -> None:
    """Manage per-worktree Redis databases and ports for local development."""


@cli.command(name="create")
@click.argument("branch")
def create_command(branch: str) -> None:
    """Create .worktrees/BRANCH on a new branch with the main checkout's local files."""
    create(Path.cwd(), branch)


@cli.command(name="provision")
@click.argument("path", required=False, type=click.Path(exists=True, path_type=Path))
def provision_command(path: Path | None) -> None:
    """Give a worktree (default: this one) its own Redis database and port."""
    provision(path or Path.cwd())


@cli.command(name="prune")
def prune_command() -> None:
    """Flush the Redis databases of worktrees that no longer exist."""
    prune(Path.cwd())


@cli.command(name="teardown")
@click.argument("path", required=False, type=click.Path(path_type=Path))
def teardown_command(path: Path | None) -> None:
    """Remove a worktree (default: this one) and flush its Redis database."""
    teardown(Path.cwd(), path)


if __name__ == "__main__":
    cli()
