"""Tests for the local path dependency guard."""

import pytest
from scripts.check_local_sources import (
    check,
    is_external,
    lockfile_findings,
    pyproject_findings,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("../valentina-python-client", True),
        ("../../../../valentina-python-client", True),
        ("/Users/someone/valentina-python-client", True),
        ("packages/../../outside", True),
        (".", False),
        ("packages/member", False),
        ("packages/../member", False),
    ],
)
def test_is_external(path: str, *, expected: bool) -> None:
    """Verify only paths that leave the repository count as external."""
    assert is_external(path) is expected


def test_pyproject_findings_flags_external_path() -> None:
    """Verify a sibling checkout source is reported and in-repo sources are not."""
    text = """
[tool.uv.sources]
    valentina-python-client = { path = "../valentina-python-client", editable = true }
    member = { path = "packages/member" }
    vendored = [{ path = "vendor/a", marker = "sys_platform == 'linux'" }, { path = "/abs/b" }]
    other = { git = "https://example.com/other.git" }
"""
    assert list(pyproject_findings(text)) == [
        "pyproject.toml: [tool.uv.sources] valentina-python-client = ../valentina-python-client",
        "pyproject.toml: [tool.uv.sources] vendored = /abs/b",
    ]


def test_pyproject_findings_without_sources() -> None:
    """Verify a pyproject.toml with no uv sources is clean."""
    assert list(pyproject_findings('[project]\nname = "vweb"\n')) == []


def test_lockfile_findings_flags_external_editable() -> None:
    """Verify an editable sibling checkout is reported while the project itself is not."""
    text = """
[[package]]
name = "vweb"
source = { editable = "." }

[[package]]
name = "valentina-python-client"
source = { editable = "../valentina-python-client" }

[[package]]
name = "flask"
source = { registry = "https://pypi.org/simple" }
"""
    assert list(lockfile_findings(text)) == [
        "uv.lock: valentina-python-client from editable ../valentina-python-client",
    ]


def test_lockfile_findings_flags_external_virtual() -> None:
    """Verify a virtual package outside the repository is reported."""
    text = '[[package]]\nname = "sibling"\nsource = { virtual = "../sibling" }\n'
    assert list(lockfile_findings(text)) == ["uv.lock: sibling from virtual ../sibling"]


def test_pyproject_findings_flags_external_file_url() -> None:
    """Verify a file URL requirement outside the repository is reported."""
    text = """
[project]
dependencies = [
    "flask>=3",
    "inside @ file:///${PROJECT_ROOT}/vendor/inside",
    "valentina-python-client @ file:///Users/someone/valentina-python-client",
]
[dependency-groups]
dev = ["tool @ file:///opt/tool ; python_version >= '3.13'", { include-group = "x" }]
"""
    assert list(pyproject_findings(text)) == [
        "pyproject.toml: valentina-python-client @ file:///Users/someone/valentina-python-client",
        "pyproject.toml: tool @ file:///opt/tool ; python_version >= '3.13'",
    ]


def test_check_reports_invalid_toml() -> None:
    """Verify unparsable files fail the check instead of raising."""
    findings = check(read=lambda filename: "not = [valid" if filename == "uv.lock" else None)
    assert len(findings) == 1
    assert findings[0].startswith("uv.lock: not valid TOML")
