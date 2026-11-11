"""Stable diagnostics are exact; only full standard AST addresses may differ."""

import json
import subprocess
import sys

import pytest
from actor_parse_diagnostics import same_parse_failure

ORIGINAL = "malformed node or string on line 1: <ast.Name object at 0x123abc>"
OTHER = "malformed node or string on line 1: <ast.Name object at 0x456def>"


@pytest.mark.parametrize(
    "recorded,error,expected",
    [
        (ORIGINAL, ValueError(ORIGINAL), True),
        (ORIGINAL, ValueError(OTHER), True),
        (
            "malformed node or string: <ast.Call object at 0x1>",
            ValueError("malformed node or string: <ast.Call object at 0x2>"),
            True,
        ),
        (
            "No valid JSON object in Actor response",
            ValueError("No valid JSON object in Actor response"),
            True,
        ),
        ("syntax", SyntaxError("syntax"), True),
        (ORIGINAL, TypeError(OTHER), False),
        (ORIGINAL, ValueError(OTHER.replace("line 1", "line 2")), False),
        (ORIGINAL, ValueError(OTHER.replace("ast.Name", "ast.Call")), False),
        (ORIGINAL, ValueError(OTHER.replace(" on line 1", "")), False),
        (ORIGINAL, ValueError("prefix " + OTHER), False),
        (ORIGINAL, ValueError(OTHER + "\n"), False),
        (ORIGINAL, ValueError(OTHER + " suffix"), False),
        (
            ORIGINAL.replace("Name", "NoSuchNode"),
            ValueError(OTHER.replace("Name", "NoSuchNode")),
            False,
        ),
        (
            ORIGINAL.replace("Name", "literal_eval"),
            ValueError(OTHER.replace("Name", "literal_eval")),
            False,
        ),
        (
            ORIGINAL.replace("ast.Name", "other.Name"),
            ValueError(OTHER.replace("ast.Name", "other.Name")),
            False,
        ),
        ("pointer 0x123abc", ValueError("pointer 0x456def"), False),
        ("", ValueError(OTHER), False),
        (ORIGINAL, ValueError(""), False),
        (ORIGINAL * 1000, ValueError(OTHER * 1000), False),
    ],
)
def test_diagnostic_comparison(
    recorded: str, error: BaseException, expected: bool
) -> None:
    assert same_parse_failure(type(error).__name__, recorded, error) is expected
    assert same_parse_failure("WrongException", recorded, error) is False


@pytest.mark.parametrize("bad", [None, 0, True, [], {}])
def test_wrong_types_are_not_coerced(bad: object) -> None:
    # Exercise the runtime boundary without changing the typed production API.
    from typing import cast

    assert not same_parse_failure(cast(str, bad), ORIGINAL, ValueError(OTHER))
    assert not same_parse_failure("ValueError", cast(str, bad), ValueError(OTHER))


def test_real_ast_diagnostic_across_processes() -> None:
    program = (
        "import ast,json\n"
        "try: ast.literal_eval(\"{'estimated_delivery_date': null}\")\n"
        "except ValueError as e: print(json.dumps(str(e)))\n"
    )
    messages = [
        json.loads(subprocess.check_output([sys.executable, "-I", "-B", "-c", program]))
        for _ in range(2)
    ]
    assert all("<ast.Name object at 0x" in message for message in messages)
    assert same_parse_failure("ValueError", messages[0], ValueError(messages[1]))
