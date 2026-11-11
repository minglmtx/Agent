"""Installed fixed readonly publication leaf; bounded stdin and no credentials."""

import resource
import sys
from lab_generate_skill.domain.lifecycle import CancellationRef
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.storage.publication_protocol import MAX_REQUEST
from lab_generate_skill.adapters.storage.publication_service import (
    serve_publication_read,
)


class _NoCancellationChannel:
    def is_cancelled(self, reference: CancellationRef) -> bool:
        raise ValueError("Private publication operation has no cancellation provider")


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        reply = serve_publication_read(
            raw, OperationGuards(SystemClock(), _NoCancellationChannel())
        )
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("PUBLICATION_READ_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
