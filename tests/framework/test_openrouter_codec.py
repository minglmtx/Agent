"""Wire protocol normal/boundary/illegal cases; exact bytes and decimal charges."""

import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.openrouter_request import prepare_openrouter
from lab_generate_skill.adapters.models.openrouter_response import decode_openrouter
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.model_request import ResolvedModelRequest
from openrouter_fixtures import fixture, resolved, PARAMETERS, REPLY


def changed(
    request: ResolvedModelRequest,
    *,
    inputs: bytes | None = None,
    params: bytes | None = None,
) -> ResolvedModelRequest:
    input_bytes = inputs if inputs is not None else request.input_bytes
    parameters = params if params is not None else request.parameters_bytes
    return ResolvedModelRequest(
        request=request.request.model_copy(
            update={
                "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
                "parameters_sha256": hashlib.sha256(parameters).hexdigest(),
            }
        ),
        input_bytes=input_bytes,
        parameters_bytes=parameters,
        limits=request.limits,
    )


def test_wire_preserves_frozen_parameters_and_only_role_input(tmp_path: Path) -> None:
    request = resolved(fixture(tmp_path))
    payload = json_object(prepare_openrouter(request))
    assert payload == {
        **PARAMETERS,
        "model": request.request.model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
    }
    assert "request_id" not in payload and "owner" not in payload
    params = {
        **PARAMETERS,
        "reasoning": {"effort": "medium", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "skill",
                "strict": True,
                "schema": {"type": "object"},
            },
        },
    }
    assert (
        json_object(
            prepare_openrouter(changed(request, params=json.dumps(params).encode()))
        )["reasoning"]
        == params["reasoning"]
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"null",
        b"[]",
        b'{"messages":[]}',
        b'{"messages":[{"role":"alien","content":"x"}]}',
        b'{"messages":[{"role":"user","content":5}]}',
        b'{"messages":[{"role":"user","content":[]}]}',
        b'{"messages":[],"messages":[]}',
        b'{"messages":NaN}',
        b"\xff",
        b"{",
    ],
)
def test_bad_messages_rejected(tmp_path: Path, raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        prepare_openrouter(changed(resolved(fixture(tmp_path)), inputs=raw))


@pytest.mark.parametrize(
    "update",
    [
        {"stream": True},
        {"model": "other"},
        {"models": ["other"]},
        {"max_tokens": True},
        {"max_tokens": 0},
        {"seed": True},
        {"temperature": 3},
        {"top_p": 0},
        {"provider": {}},
        {"provider": {"allow_fallbacks": True, "require_parameters": True}},
        {"provider": {"allow_fallbacks": False}},
        {"reasoning": []},
        {"tools": {}},
        {"parallel_tool_calls": "yes"},
        {"max_retries": 1},
        {"stop": 2},
    ],
)
def test_parameters_reject_overrides_and_invalid_types(
    tmp_path: Path, update: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        prepare_openrouter(
            changed(
                resolved(fixture(tmp_path)),
                params=json.dumps({**PARAMETERS, **update}).encode(),
            )
        )


def test_multimodal_and_tool_messages_preserved(tmp_path: Path) -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,dW5pdA==",
                        "detail": "low",
                    },
                },
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call",
                    "type": "function",
                    "function": {"name": "click", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "done", "tool_call_id": "call"},
    ]
    wire = prepare_openrouter(
        changed(
            resolved(fixture(tmp_path)),
            inputs=json.dumps({"messages": messages}).encode(),
        )
    )
    assert json_object(wire)["messages"] == messages


@pytest.mark.parametrize(
    "number,units",
    [
        ("0", 0),
        ("0.000000001", 1),
        ("1.0000000000", 1_000_000_000),
        ("1e-9", 1),
        ("0.0000000001", None),
        ("null", None),
        ('"0.1"', None),
        ("true", None),
        ("-1", None),
        ("1e100000", None),
        ("1e-100000", None),
    ],
)
def test_exact_charge_never_rounds_or_guesses(
    tmp_path: Path, number: str, units: int | None
) -> None:
    raw = REPLY.replace(b"0.000000002", number.encode())
    reply = decode_openrouter(resolved(fixture(tmp_path)), raw)
    assert reply.raw_response == raw
    assert (None if reply.charge is None else reply.charge.units) == units


@pytest.mark.parametrize(
    "raw",
    [
        b'{"error":{"message":"unit"}}',
        b"{}",
        b'{"id":"x","choices":null}',
        REPLY.replace(b'"stop"', b"null"),
        REPLY.replace(b'"hello"', b"null"),
        REPLY.replace(b'"id":"unit-provider"', b'"id":"unit-provider","id":"another"'),
        REPLY.replace(b"0.000000002", b"NaN"),
    ],
)
def test_error_malformed_and_incomplete_responses_not_success(
    tmp_path: Path, raw: bytes
) -> None:
    with pytest.raises(ValueError):
        decode_openrouter(resolved(fixture(tmp_path)), raw)
