"""Fail when pyproject.toml or uv.lock resolves a dependency from a path outside the repository.

Developing against an unreleased sibling checkout, such as `../valentina-python-client`, adds a
`[tool.uv.sources]` path override and an editable uv.lock entry. Neither resolves in CI, in the
Docker build, or on another machine. Paths inside the repository (the project itself, workspace
members) are allowed.

Standard library only: CI runs this before uv installs anything, since `uv sync` itself fails on
a leaked path.

    python3 scripts/check_local_sources.py staged   # pre-commit: the index
    python3 scripts/check_local_sources.py push     # pre-push: each pushed commit touching either file
    python3 scripts/check_local_sources.py tree     # CI: the working tree
"""

import argparse
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = "pyproject.toml"
LOCKFILE = "uv.lock"
NULL_SHA = "0" * 40
LOCK_PATH_KEYS = ("editable", "path", "directory", "virtual")
FILE_URL_MARKER = "@ file:"


def is_external(path: str) -> bool:
    """Return True when a dependency path points outside the repository.

    Args:
        path (str): Path as written in pyproject.toml or uv.lock, relative to the project root.

    Returns:
        bool: True for absolute paths and paths that climb above the project root.
    """
    return not (PROJECT_ROOT / path).resolve().is_relative_to(PROJECT_ROOT)


def file_url_path(requirement: str) -> str | None:
    """Return the local path of a `name @ file://...` requirement, or None for any other form.

    Args:
        requirement (str): A PEP 508 requirement string.

    Returns:
        str | None: The path the file URL names, with uv's `${PROJECT_ROOT}` expanded.
    """
    if FILE_URL_MARKER not in requirement:
        return None
    url = requirement.split(" @ ", 1)[1].split(";", 1)[0].strip()
    url = url.replace("${PROJECT_ROOT}", PROJECT_ROOT.as_posix())
    return unquote(urlparse(url).path)


def requirements(document: dict) -> Iterator[str]:
    """Yield every requirement string pyproject.toml declares.

    Args:
        document (dict): Parsed pyproject.toml.

    Yields:
        str: A PEP 508 requirement string.
    """
    project = document.get("project", {})
    yield from project.get("dependencies", [])
    for group in project.get("optional-dependencies", {}).values():
        yield from group
    for group in document.get("dependency-groups", {}).values():
        yield from (item for item in group if isinstance(item, str))


def pyproject_findings(text: str) -> Iterator[str]:
    """Yield each source or file URL requirement that points outside the repository.

    Args:
        text (str): Contents of pyproject.toml.

    Yields:
        str: A description of the offending source.
    """
    document = tomllib.loads(text)
    sources = document.get("tool", {}).get("uv", {}).get("sources", {})
    for name, spec in sources.items():
        for entry in spec if isinstance(spec, list) else [spec]:
            if (path := entry.get("path")) and is_external(path):
                yield f"{PYPROJECT}: [tool.uv.sources] {name} = {path}"
    for requirement in requirements(document):
        if (path := file_url_path(requirement)) and is_external(path):
            yield f"{PYPROJECT}: {requirement}"


def lockfile_findings(text: str) -> Iterator[str]:
    """Yield each locked package whose source points outside the repository.

    Args:
        text (str): Contents of uv.lock.

    Yields:
        str: A description of the offending package.
    """
    for package in tomllib.loads(text).get("package", []):
        source = package.get("source", {})
        for key in LOCK_PATH_KEYS:
            if (path := source.get(key)) and is_external(path):
                yield f"{LOCKFILE}: {package.get('name')} from {key} {path}"


CHECKS: dict[str, Callable[[str], Iterator[str]]] = {
    PYPROJECT: pyproject_findings,
    LOCKFILE: lockfile_findings,
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command and capture its output.

    Returns:
        subprocess.CompletedProcess[str]: The finished process.
    """
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def git_show(revision: str, filename: str) -> str | None:
    """Return a file's contents at a revision, or None when it does not exist there.

    Args:
        revision (str): A commit, or "" for the index.
        filename (str): Path from the repository root.

    Returns:
        str | None: The file contents.
    """
    result = git("show", f"{revision}:{filename}")
    return result.stdout if result.returncode == 0 else None


def read_working_tree(filename: str) -> str | None:
    """Return a file's contents from the working tree, or None when it does not exist.

    Args:
        filename (str): Path from the repository root.

    Returns:
        str | None: The file contents.
    """
    path = PROJECT_ROOT / filename
    return path.read_text() if path.exists() else None


def check(read: Callable[[str], str | None], label: str = "") -> list[str]:
    """Run every check against files supplied by a reader.

    Args:
        read (Callable[[str], str | None]): Returns a file's contents, or None when it is absent.
        label (str): Prefix for each finding, such as a commit hash.

    Returns:
        list[str]: Every finding.
    """
    findings = []
    for filename, find in CHECKS.items():
        if (text := read(filename)) is None:
            continue
        try:
            findings.extend(f"{label}{finding}" for finding in find(text))
        except tomllib.TOMLDecodeError as error:
            findings.append(f"{label}{filename}: not valid TOML ({error})")
    return findings


def pushed_commits() -> list[str]:
    """Return the pushed commits that change pyproject.toml or uv.lock.

    Reads the range prek and pre-commit export for pre-push hooks. A new branch has no remote
    base, so its range is everything not already on a remote.

    Returns:
        list[str]: Commit hashes, newest first.
    """
    to_ref = os.environ.get("PRE_COMMIT_TO_REF", "")
    from_ref = os.environ.get("PRE_COMMIT_FROM_REF", "")
    if not to_ref:
        sys.exit("PRE_COMMIT_TO_REF is not set; run this mode from a pre-push hook.")
    if to_ref == NULL_SHA:  # Deleting a remote branch pushes no content
        return []
    revisions = [f"{from_ref}..{to_ref}"] if from_ref and from_ref != NULL_SHA else []
    revisions = revisions or [to_ref, "--not", "--remotes"]
    result = git("rev-list", *revisions, "--", *CHECKS)
    if result.returncode != 0:
        sys.exit(result.stderr.strip())
    return result.stdout.split()


def main() -> int:
    """Check the selected files and report any local path dependency.

    Returns:
        int: The exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=("staged", "push", "tree"))
    mode = parser.parse_args().mode

    if mode == "staged":
        findings = check(read=lambda filename: git_show(revision="", filename=filename))
    elif mode == "tree":
        findings = check(read=read_working_tree)
    else:
        findings = [
            finding
            for sha in pushed_commits()
            for finding in check(
                read=lambda filename, sha=sha: git_show(revision=sha, filename=filename),
                label=f"{sha[:8]} ",
            )
        ]

    if not findings:
        return 0

    report = [
        "Dependencies resolve from a local path outside this repository:",
        *(f"  {finding}" for finding in findings),
        "",
        "Leave pyproject.toml and uv.lock unstaged while they point at a local checkout, or run",
        "`duty vclient-release` to switch back to the published package.",
    ]
    if mode == "push":
        report.append("These files are already committed; rewrite those commits before pushing.")
    sys.stderr.write("\n".join(report) + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
