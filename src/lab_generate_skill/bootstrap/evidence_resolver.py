"""Fixed installed cleanup leaf; no original I/O or alternate runtime selection."""

import resource
import sys
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.storage.registered_protocol import (
    MAX_REGISTERED_PACKET,
)
from lab_generate_skill.adapters.storage.resolver_service import (
    serve_storage_resolution,
)
from .evidence_worker import _NoCancellationChannel


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(MAX_REGISTERED_PACKET + 1)
        result = serve_storage_resolution(
            raw, OperationGuards(SystemClock(), _NoCancellationChannel())
        )
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("STORAGE_RESOLVER_PROTOCOL_OR_OUTPUT_FAILED\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
