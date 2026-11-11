"""Supplied public Ed25519 key/title; no private key or credential material."""

import base64
import json
import struct
from pydantic import field_validator
from lab_generate_skill.domain.validation import Contract, NonEmptyText


def canonical_public_key(value: str) -> str:
    """Preserve the original complete Ed25519 wire rule, optional comment aside."""
    if type(value) is not str or "\n" in value or "\r" in value:
        raise ValueError("One supplied public Ed25519 key required")
    parts = value.split()
    if len(parts) not in (2, 3) or parts[0] != "ssh-ed25519":
        raise ValueError("Only complete public Ed25519 key material is supported")
    try:
        wire = base64.b64decode(parts[1], validate=True)
        length = struct.unpack(">I", wire[:4])[0]
        kind = wire[4 : 4 + length]
        offset = 4 + length
        key_length = struct.unpack(">I", wire[offset : offset + 4])[0]
        key = wire[offset + 4 :]
    except (ValueError, struct.error):
        raise ValueError("Malformed public key wire") from None
    if kind != b"ssh-ed25519" or key_length != 32 or len(key) != 32:
        raise ValueError("Complete native public Ed25519 wire required")
    return "ssh-ed25519 " + base64.b64encode(wire).decode("ascii")


class SshKeyParameters(Contract):
    public_key: NonEmptyText
    title: NonEmptyText

    @field_validator("public_key")
    @classmethod
    def public_wire(cls, value: str) -> str:
        canonical_public_key(value)
        return value

    @field_validator("title")
    @classmethod
    def single_title(cls, value: str) -> str:
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("One nonempty supplied native key title required")
        return value


def render_public_goal(goal: str, parameters: SshKeyParameters) -> str:
    """Exact old public_task_input.render layout, without importing old runners."""
    parameters = SshKeyParameters.model_validate(parameters)
    if type(goal) is not str or not goal.strip():
        raise ValueError("Explicit original public goal required")
    return (
        goal
        + "\n\nTask-supplied parameters:\n"
        + json.dumps(
            parameters.model_dump(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )
