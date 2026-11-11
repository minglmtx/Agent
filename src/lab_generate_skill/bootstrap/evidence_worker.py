"""Installed fixed leaf worker for durably registered evidence I/O.

Parent admission must have approved scope/roots/release. The parent monitors its
original control; this child additionally enforces the transmitted fixed wall
and local monotonic deadline. No environment credentials or caller-selected code.
"""

import resource
import sys
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.storage.registered_protocol import (
    MAX_REGISTERED_PACKET,
)
from lab_generate_skill.adapters.storage.registered_service import (
    serve_registered_storage,
)


class _NoCancellationChannel:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError(
            "Private storage operation cannot select a cancellation provider"
        )


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_REGISTERED_PACKET + 1)
        reply = serve_registered_storage(
            raw, OperationGuards(SystemClock(), _NoCancellationChannel())
        )
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("REGISTERED_STORAGE_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
