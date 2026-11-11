"""Bounded native stderr on the private supervised worker diagnostic stream.

No argv, environment, stdin, task input or stdout is copied. The outer resource
stores this stream as private evidence; it must never become model input. This
is best effort and cannot replace the primary error or prevent physical cleanup.
"""

import base64
import json
import sys
from lab_generate_skill.adapters.processes.capture import retained_capture


def native_failure(error: BaseException) -> None:
    capture = retained_capture(error)
    if capture is None:
        return
    try:
        event = dict(
            schema_version="site-native-failure/1",
            returncode=capture.returncode,
            complete=capture.complete,
            stderr_base64=base64.b64encode(capture.stderr[:8192]).decode("ascii"),
            stderr_truncated=len(capture.stderr) > 8192,
        )
        sys.stderr.write("SITE_NATIVE_FAILURE " + json.dumps(event) + "\n")
        sys.stderr.flush()
    except (OSError, ValueError) as diagnostic:
        setattr(error, "site_diagnostic_error", diagnostic)
