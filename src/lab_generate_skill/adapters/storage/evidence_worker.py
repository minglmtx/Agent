"""Fixed one-exchange evidence worker, launched as an installed package module.

All storage initialization/reading/writing happens here, after full validation.
No retries, arbitrary function imports, child processes or credential access.
Parent must supervise the process and durably isolate unconfirmed termination.
Successful reply only reports this exchange; it is not a resource-clean receipt.
"""

import resource
import sys
from pathlib import Path

from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .filesystem import FileEvidenceStore
from .worker_protocol import (
    MAX_PACKET_BYTES,
    EvidenceReply,
    decode_command,
    encode_reply,
)


def exchange(raw: bytes) -> bytes:
    # Invalid framing/metadata/expected digest must fail before even root init.
    command, payload = decode_command(raw)
    result = b""
    error = None
    try:
        store = FileEvidenceStore(
            Path(command.root),
            max_object_bytes=command.max_object_bytes,
            initialize=command.operation == "put",
        )
        if command.operation == "put":
            assert command.metadata is not None
            reference = store.put(
                payload, command.metadata, exchange_id=command.exchange_id
            )
            if reference != command.reference:
                raise ValueError("Storage returned a different evidence identity")
        else:
            result = store.read(command.reference)
    except BaseException as caught:
        error = describe_error(caught)
        result = b""
    reply = EvidenceReply(
        exchange_id=command.exchange_id,
        operation=command.operation,
        reference=command.reference,
        error=error,
    )
    return encode_reply(command, reply, result)


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_PACKET_BYTES + 1)
        result = exchange(raw)
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    except BaseException:
        # Do not print exception arguments, malformed raw input or evidence.
        # No valid exchange identity exists or the output channel has failed.
        sys.stderr.write("EVIDENCE_WORKER_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
