"""Unit tests for the per-worktree Redis and port helpers."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.worktree import (
    ENV_FILE,
    KEY_PORT,
    KEY_REDIS_URL,
    Checkouts,
    MainSettings,
    choose_slot,
    copy_local_files,
    create,
    dev_redis_error,
    free_slots,
    read_env,
    redis_db,
    rewrite_env,
    slot_of,
    targets_api_redis,
    teardown,
    with_redis_db,
)

from scripts import worktree

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

MAIN = MainSettings(redis_url="redis://:redispassword@127.0.0.1:6380/0", port=8089)
FIX_LINE = "VWEB_REDIS__URL=redis://:redispassword@127.0.0.1:6380/0"


def _write_env(directory: Path, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ENV_FILE).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, mocker: MockerFixture) -> tuple[Path, list[Path], MagicMock, MagicMock]:
    """Build a main checkout on the dev Redis with five provisioned worktrees, git and Redis mocked.

    Returns:
        tuple: The main checkout, the worktrees, the mocked `_git`, and the mocked `LocalRedis`.
    """
    main = tmp_path / "main"
    _write_env(main, f"{KEY_REDIS_URL}=redis://:redispassword@127.0.0.1:6380/0\n")
    worktrees = [main / ".worktrees" / f"wt{slot}" for slot in range(1, 6)]
    for slot, path in enumerate(worktrees, start=1):
        _write_env(path, f"{KEY_REDIS_URL}=redis://:redispassword@127.0.0.1:6380/{slot}\n")
    mocker.patch.object(
        Checkouts, "discover", return_value=Checkouts(main=main, worktrees=worktrees)
    )
    git = mocker.patch.object(worktree, "_git", autospec=True, return_value="")
    redis = mocker.patch.object(worktree, "LocalRedis", autospec=True)
    return main, worktrees, git, redis


def test_create_refuses_a_sixth_worktree_before_git_runs(
    repo: tuple[Path, list[Path], MagicMock, MagicMock],
) -> None:
    """Verify a sixth worktree is refused before `git worktree add`, so nothing is left behind."""
    # Given five worktrees holding every slot
    main, _, git, _ = repo

    # When creating another
    with pytest.raises(SystemExit):
        create(main, "wt6")

    # Then git was never asked to add it
    git.assert_not_called()


def test_create_refuses_when_main_is_not_on_dev_redis(
    repo: tuple[Path, list[Path], MagicMock, MagicMock],
) -> None:
    """Verify an unconfigured main checkout stops create before git runs."""
    # Given main pointing at the API's Redis
    main, _, git, _ = repo
    _write_env(main, f"{KEY_REDIS_URL}=redis://127.0.0.1:6379/0\n")

    # When / Then
    with pytest.raises(SystemExit):
        create(main, "wt6")
    git.assert_not_called()


def test_teardown_flushes_nothing_when_git_refuses(
    repo: tuple[Path, list[Path], MagicMock, MagicMock],
) -> None:
    """Verify a worktree git will not remove, such as one with uncommitted changes, keeps its data."""
    # Given git refusing to remove the worktree
    main, worktrees, git, redis = repo
    git.side_effect = SystemExit("worktree has modifications")

    # When tearing it down
    with pytest.raises(SystemExit):
        teardown(main, worktrees[0])

    # Then no Redis database is flushed
    redis.return_value.flush.assert_not_called()


def test_teardown_checks_the_guard_before_removing(
    repo: tuple[Path, list[Path], MagicMock, MagicMock],
) -> None:
    """Verify teardown refuses before removing anything when main is not on the dev Redis."""
    # Given main pointing at the API's Redis
    main, worktrees, git, _ = repo
    _write_env(main, f"{KEY_REDIS_URL}=redis://127.0.0.1:6379/0\n")

    # When / Then
    with pytest.raises(SystemExit):
        teardown(main, worktrees[0])
    git.assert_not_called()


def test_teardown_flushes_the_removed_worktrees_slot(
    repo: tuple[Path, list[Path], MagicMock, MagicMock],
) -> None:
    """Verify a removed worktree's Redis database is flushed."""
    # Given git removing the worktree directory
    main, worktrees, git, redis = repo
    git.side_effect = lambda *_args: worktrees[1].joinpath(ENV_FILE).unlink() or ""

    # When tearing down the slot 2 worktree
    teardown(main, worktrees[1])

    # Then slot 2 is flushed
    redis.return_value.flush.assert_called_once_with(2)


def test_copy_local_files_keeps_file_permissions(tmp_path: Path) -> None:
    """Verify the copied env file keeps main's restrictive mode."""
    # Given a main env file readable only by its owner, and a worktree that ignores it
    main = tmp_path / "main"
    _write_env(main, "VWEB_PORT=8089\n")
    (main / ENV_FILE).chmod(0o600)
    target = tmp_path / "wt"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)  # noqa: S603, S607
    (target / ".gitignore").write_text(f"{ENV_FILE}\n", encoding="utf-8")

    # When copying
    copy_local_files(main, target)

    # Then the copy keeps the mode
    assert (target / ENV_FILE).stat().st_mode & 0o777 == 0o600


def test_rewrite_env_rewrites_exported_keys(tmp_path: Path) -> None:
    """Verify an `export`-prefixed duplicate is rewritten too, since dotenv honors it."""
    # Given an env file with a plain and an exported port
    env_file = tmp_path / ENV_FILE
    env_file.write_text("VWEB_PORT=1\nexport VWEB_PORT=2\n", encoding="utf-8")

    # When rewriting the port
    rewrite_env(env_file, {KEY_PORT: "8091"})

    # Then the file resolves to the new value
    assert read_env(env_file)[KEY_PORT] == "8091"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (None, True),
        ("", False),
        ("redis://127.0.0.1:6379/0", True),
        ("redis://:pw@localhost/0", True),
        ("redis://[::1]:6379/0", True),
        ("redis://0.0.0.0:6379/0", True),
        ("redis://:redispassword@127.0.0.1:6380/0", False),
        ("redis://:pw@redis.example.com:6379/0", False),
    ],
)
def test_targets_api_redis_matches_local_port_6379(url: str | None, *, expected: bool) -> None:
    """Verify only an unset URL or a local URL on port 6379 counts as the API's Redis."""
    # Given / When / Then
    assert targets_api_redis(url) is expected


def test_redis_db_exits_on_a_non_numeric_database() -> None:
    """Verify a malformed URL exits with a message instead of a traceback."""
    # Given / When / Then
    with pytest.raises(SystemExit):
        redis_db("redis://127.0.0.1:6380/abc")


def test_dev_redis_error_rejects_a_non_numeric_port() -> None:
    """Verify a malformed port is refused rather than crashing the guard."""
    # Given / When / Then
    assert dev_redis_error("redis://127.0.0.1:port/0") is not None


def test_rewrite_env_replaces_and_appends_keys(tmp_path: Path) -> None:
    """Verify existing keys change in place, other lines survive, and missing keys are appended."""
    # Given an env file with a comment, a key to change, and an unrelated key
    env_file = tmp_path / ENV_FILE
    env_file.write_text(
        "# comment\nVWEB_APP_NAME=test\nVWEB_REDIS__URL=redis://127.0.0.1:6380/0\n",
        encoding="utf-8",
    )

    # When rewriting one existing and one missing key
    rewrite_env(env_file, {KEY_REDIS_URL: "redis://127.0.0.1:6380/2", KEY_PORT: "8091"})

    # Then the file keeps its other lines and holds both values
    assert env_file.read_text(encoding="utf-8").splitlines() == [
        "# comment",
        "VWEB_APP_NAME=test",
        "VWEB_REDIS__URL=redis://127.0.0.1:6380/2",
        "VWEB_PORT=8091",
    ]


def test_rewrite_env_keeps_comments(tmp_path: Path) -> None:
    """Verify a commented-out copy of a key is left alone."""
    # Given an env file with a commented and a live port
    env_file = tmp_path / ENV_FILE
    env_file.write_text("# VWEB_PORT=1\nVWEB_PORT=8089\n", encoding="utf-8")

    # When rewriting the port
    rewrite_env(env_file, {KEY_PORT: "8091"})

    # Then only the live line changes
    assert env_file.read_text(encoding="utf-8") == "# VWEB_PORT=1\nVWEB_PORT=8091\n"


def test_rewrite_env_replaces_every_duplicate_key(tmp_path: Path) -> None:
    """Verify a key set twice is rewritten everywhere so the last occurrence cannot win."""
    # Given an env file that sets the port twice
    env_file = tmp_path / ENV_FILE
    env_file.write_text("VWEB_PORT=1\nVWEB_PORT=2\n", encoding="utf-8")

    # When rewriting the port
    rewrite_env(env_file, {KEY_PORT: "8091"})

    # Then the file resolves to the new value
    assert read_env(env_file)[KEY_PORT] == "8091"


def test_read_env_treats_blank_values_as_unset(tmp_path: Path) -> None:
    """Verify a blank value falls back like a missing key."""
    # Given an env file with a blank port
    env_file = tmp_path / ENV_FILE
    env_file.write_text("VWEB_PORT=\n", encoding="utf-8")

    # When / Then the blank key is absent
    assert KEY_PORT not in read_env(env_file)


def test_main_settings_load_defaults_when_env_is_missing(tmp_path: Path) -> None:
    """Verify a checkout without an env file has no Redis URL and the default port."""
    # Given / When / Then
    assert MainSettings.load(tmp_path) == MainSettings(redis_url=None, port=8089)


def test_main_settings_load_reads_the_env_file(tmp_path: Path) -> None:
    """Verify main's Redis URL and port come from its env file."""
    # Given a main checkout with both keys set
    (tmp_path / ENV_FILE).write_text(
        "VWEB_REDIS__URL=redis://127.0.0.1:6380/0\nVWEB_PORT=9000\n", encoding="utf-8"
    )

    # When / Then
    assert MainSettings.load(tmp_path) == MainSettings(
        redis_url="redis://127.0.0.1:6380/0", port=9000
    )


def test_port_for_adds_the_slot_to_mains_port() -> None:
    """Verify a worktree's port is main's port plus its slot."""
    # Given / When / Then
    assert MAIN.port_for(3) == 8092


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("redis://127.0.0.1:6380", 0),
        ("redis://127.0.0.1:6380/", 0),
        ("redis://:pw@127.0.0.1:6380/3", 3),
    ],
)
def test_redis_db_reads_the_logical_database(url: str, expected: int) -> None:
    """Verify the logical database comes from the URL path and defaults to 0."""
    # Given / When / Then
    assert redis_db(url) == expected


def test_with_redis_db_keeps_credentials() -> None:
    """Verify switching the logical database keeps the host and password."""
    # Given / When / Then
    assert with_redis_db("redis://:pw@127.0.0.1:6380/0", 4) == "redis://:pw@127.0.0.1:6380/4"


@pytest.mark.parametrize(
    "url",
    ["redis://:redispassword@127.0.0.1:6380/0", "redis://:pw@localhost:6380/2"],
)
def test_dev_redis_error_accepts_the_dev_container(url: str) -> None:
    """Verify a URL on the local dev container passes the guard."""
    # Given / When / Then
    assert dev_redis_error(url) is None


@pytest.mark.parametrize(
    "url",
    [
        None,
        "redis://127.0.0.1:6379/0",
        "redis://:pw@redis.example.com:6380/0",
        "redis://127.0.0.1/0",
    ],
)
def test_dev_redis_error_rejects_anything_else(url: str | None) -> None:
    """Verify a missing URL, the API's Redis, or a remote host is refused with the fix."""
    # Given / When
    message = dev_redis_error(url)

    # Then the message names the line to add
    assert message is not None
    assert FIX_LINE in message


def test_dev_redis_error_never_echoes_the_url() -> None:
    """Verify the message leaves out the configured URL, which may carry a password."""
    # Given / When
    message = dev_redis_error("redis://:hunter2@redis.example.com:6379/0")

    # Then
    assert message is not None
    assert "hunter2" not in message


def test_slot_of_ignores_an_env_that_mirrors_main() -> None:
    """Verify a freshly copied env file has no slot yet."""
    # Given / When / Then
    assert slot_of({KEY_REDIS_URL: str(MAIN.redis_url)}, MAIN) is None
    assert slot_of({}, MAIN) is None


def test_slot_of_reads_an_assigned_slot() -> None:
    """Verify a provisioned env file claims its Redis database as its slot."""
    # Given / When / Then
    assert slot_of({KEY_REDIS_URL: "redis://:pw@127.0.0.1:6380/5"}, MAIN) == 5


def test_free_slots_stops_at_max_worktrees() -> None:
    """Verify only slots 1 to 5 are offered."""
    # Given / When / Then
    assert free_slots({1, 2}, MAIN) == [3, 4, 5]


def test_free_slots_is_empty_when_all_five_are_taken() -> None:
    """Verify a sixth worktree finds no slot."""
    # Given / When / Then
    assert free_slots({1, 2, 3, 4, 5}, MAIN) == []


def test_free_slots_skips_mains_database() -> None:
    """Verify main's own Redis database is never handed to a worktree."""
    # Given main on database 2
    main = MainSettings(redis_url="redis://:pw@127.0.0.1:6380/2", port=8089)

    # When / Then
    assert free_slots(set(), main) == [1, 3, 4, 5]


def test_choose_slot_keeps_a_free_current_slot() -> None:
    """Verify re-provisioning keeps the slot a worktree already holds."""
    # Given / When / Then
    assert choose_slot(current=4, taken={1, 2}, main=MAIN) == 4


def test_choose_slot_takes_the_lowest_free_slot() -> None:
    """Verify a new or conflicting worktree gets the lowest slot nobody holds."""
    # Given / When / Then
    assert choose_slot(current=None, taken={1, 2}, main=MAIN) == 3
    assert choose_slot(current=2, taken={1, 2}, main=MAIN) == 3


def test_choose_slot_replaces_a_slot_above_the_cap() -> None:
    """Verify a slot outside 1 to 5 is not kept."""
    # Given / When / Then
    assert choose_slot(current=9, taken=set(), main=MAIN) == 1


def test_choose_slot_exits_when_every_slot_is_taken() -> None:
    """Verify running out of slots exits instead of sharing one."""
    # Given / When / Then
    with pytest.raises(SystemExit):
        choose_slot(current=None, taken={1, 2, 3, 4, 5}, main=MAIN)
