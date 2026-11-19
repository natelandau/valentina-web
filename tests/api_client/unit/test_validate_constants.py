"""Tests for vweb.api_client.validate_constants."""

import typing

import pytest

from vweb.api_client import constants
from vweb.api_client.validate_constants import (
    CONSTANT_MAP,
    ConstantMismatch,
    ValidationResult,
    print_report,
    validate,
)

# Client-only Literal types that have no API /options counterpart
CLIENT_ONLY_LITERALS = {
    "AuditLogInclude",
    "BookInclude",
    "ChapterInclude",
    "CharacterInclude",
    "UserInclude",
}


def _matching_options() -> dict[str, dict]:
    """Return an options payload that agrees with every mapped local constant."""
    options: dict[str, dict] = {}
    for name, mapping in CONSTANT_MAP.items():
        values = list(typing.get_args(getattr(constants, name)))
        options.setdefault(mapping.api_category, {})[mapping.api_option] = values
    return options


def test_every_literal_constant_is_mapped() -> None:
    """Verify every API-backed Literal in constants.py is checked against the API."""
    literal_names = {
        name
        for name in dir(constants)
        if not name.startswith("_")
        and typing.get_origin(getattr(constants, name)) is typing.Literal
    }

    assert literal_names - CLIENT_ONLY_LITERALS - set(CONSTANT_MAP) == set()


def test_every_mapping_names_an_existing_constant() -> None:
    """Verify the map has no entry for a constant that no longer exists."""
    assert [name for name in CONSTANT_MAP if not hasattr(constants, name)] == []


def test_matching_options_are_valid() -> None:
    """Verify options that agree with every constant validate cleanly."""
    result = validate(_matching_options())

    assert result.is_valid is True
    assert result.mismatches == []
    assert result.unmapped_api_options == {}


@pytest.mark.parametrize(
    ("api_values", "missing", "extra"),
    [
        pytest.param(["ALIVE", "DEAD", "UNDEAD"], {"UNDEAD"}, set(), id="new-api-value"),
        pytest.param(["ALIVE"], set(), {"DEAD"}, id="value-dropped-by-api"),
        pytest.param(None, set(), {"ALIVE", "DEAD"}, id="option-absent-from-api"),
    ],
)
def test_value_drift_is_reported(
    api_values: list[str] | None, missing: set[str | int], extra: set[str | int]
) -> None:
    """Verify each side's extra values are reported against the drifted constant."""
    options = _matching_options()
    if api_values is None:
        del options["characters"]["CharacterStatus"]
    else:
        options["characters"]["CharacterStatus"] = api_values

    result = validate(options)

    assert result.is_valid is False
    assert result.mismatches == [
        ConstantMismatch(
            constant_name="CharacterStatus",
            api_category="characters",
            api_option="CharacterStatus",
            missing_from_client=missing,
            extra_in_client=extra,
        )
    ]


@pytest.mark.parametrize(
    ("category", "option", "value"),
    [
        pytest.param("characters", "_related", ["x"], id="underscore-metadata-key"),
        pytest.param("characters", "TrackerRules", {"V5": {}}, id="non-list-value"),
        pytest.param(
            "character_autogeneration",
            "CharacterClassPercentileChance",
            ["MORTAL: 0-50"],
            id="ignored-informational-option",
        ),
    ],
)
def test_non_enum_options_are_not_reported_unmapped(
    category: str, option: str, value: object
) -> None:
    """Verify metadata, nested tables, and ignored options are not treated as missing enums."""
    options = _matching_options()
    options.setdefault(category, {})[option] = value

    assert validate(options).is_valid is True


def test_non_dict_category_is_skipped() -> None:
    """Verify a top-level value that is not a category of options is skipped."""
    options: dict = _matching_options() | {"_version": "1.2.3"}

    assert validate(options).is_valid is True


def test_new_api_option_is_reported_unmapped() -> None:
    """Verify an API enum with no local constant is reported by category."""
    options = _matching_options()
    options["characters"]["NewOptionType"] = ["FOO"]

    result = validate(options)

    assert result.is_valid is False
    assert result.unmapped_api_options == {"characters": ["NewOptionType"]}


@pytest.mark.parametrize(
    ("result", "expected_lines"),
    [
        pytest.param(
            ValidationResult(is_valid=True),
            [f"{len(CONSTANT_MAP)}/{len(CONSTANT_MAP)} constants in sync"],
            id="in-sync",
        ),
        pytest.param(
            ValidationResult(
                is_valid=False,
                mismatches=[
                    ConstantMismatch(
                        constant_name="CharacterStatus",
                        api_category="characters",
                        api_option="CharacterStatus",
                        missing_from_client={"UNDEAD"},
                    ),
                    ConstantMismatch(
                        constant_name="GameVersion",
                        api_category="characters",
                        api_option="GameVersion",
                        extra_in_client={"V4"},
                    ),
                ],
            ),
            [
                "characters.CharacterStatus",
                "['UNDEAD']",
                "characters.GameVersion",
                "['V4']",
                "2 mismatch(es)",
            ],
            id="mismatch",
        ),
        pytest.param(
            ValidationResult(is_valid=False, unmapped_api_options={"characters": ["NewOption"]}),
            ["characters.NewOption", "1 unmapped API option(s)"],
            id="unmapped",
        ),
    ],
)
def test_print_report_lists_each_problem(
    capsys: pytest.CaptureFixture[str], result: ValidationResult, expected_lines: list[str]
) -> None:
    """Verify the report names each drifted constant, its values, and each unmapped option."""
    print_report(result)

    out = capsys.readouterr().out
    for line in expected_lines:
        assert line in out
