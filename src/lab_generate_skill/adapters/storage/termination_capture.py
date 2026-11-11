"""Produce ending facts only from the original fixed runner's confirmed capture.

Called by the transport that sent the exact request. No absence, timeout or
foreign typed ending is upgraded to a reap; unknown captures return None.
"""

import hashlib
import json
from datetime import datetime, timezone
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.adapters.processes.capture import CommandCapture


def captured_storage_end(
    controller: ProcessIdentity,
    request: bytes,
    argv: tuple[str, ...],
    capture: CommandCapture | None,
) -> StorageProcessEnd | None:
    if capture is None:
        return None
    end = capture.termination
    if (
        capture.argv != argv
        or end is None
        or end.state != "reaped"
        or end.cleanup_errors
        or type(end.process_id) is not int
        or end.process_id == controller.process_id
        or type(capture.returncode) is not int
        or end.returncode != capture.returncode
        or type(capture.stdout) is not bytes
        or type(capture.stderr) is not bytes
        or type(capture.complete) is not bool
    ):
        return None
    fingerprint = json.dumps(
        {
            "argv": argv,
            "returncode": capture.returncode,
            "complete": capture.complete,
            "pid": end.process_id,
            "kill_requested": end.kill_requested,
            "stdout_sha256": hashlib.sha256(capture.stdout).hexdigest(),
            "stdout_bytes": len(capture.stdout),
            "stderr_sha256": hashlib.sha256(capture.stderr).hexdigest(),
            "stderr_bytes": len(capture.stderr),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return StorageProcessEnd(
        controller=controller,
        request_sha256=hashlib.sha256(request).hexdigest(),
        process_id=end.process_id,
        returncode=capture.returncode,
        observed_at=datetime.now(timezone.utc),
        capture_sha256=hashlib.sha256(fingerprint).hexdigest(),
        kill_requested=end.kill_requested,
    )
