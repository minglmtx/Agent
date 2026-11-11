"""Strict bounded worker packet decoding and retained process-failure capture."""

import base64
from lab_generate_skill.adapters.processes.commands import CommandFailure
from lab_generate_skill.adapters.processes.wire_json import json_object


def parse_packet(
    raw: bytes, limit: int
) -> tuple[int | None, bytes, bool, tuple[str, ...]]:
    packet = json_object(raw)
    if set(packet) != {"status", "body_base64", "complete", "errors"}:
        raise ValueError("Unexpected worker packet")
    status = packet["status"]
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        raise ValueError("Invalid worker status")
    if (
        type(packet["body_base64"]) is not str
        or type(packet["complete"]) is not bool
        or not isinstance(packet["errors"], list)
        or any(not isinstance(x, str) or not x.isidentifier() for x in packet["errors"])
    ):
        raise ValueError("Invalid worker capture fields")
    body = base64.b64decode(packet["body_base64"], validate=True)
    if len(body) > limit:
        raise ValueError("Worker exceeded response limit")
    return status, body, packet["complete"], tuple(packet["errors"])


def retained_command_failure(error: BaseException) -> CommandFailure | None:
    if isinstance(error, CommandFailure):
        return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            found = retained_command_failure(child)
            if found is not None:
                return found
    return None
