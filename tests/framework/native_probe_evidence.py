"""Bounded command capture plus full Python traceback for native engineering probes."""

from pathlib import Path
import traceback
from dataclasses import asdict
from typing import Any
from lab_generate_skill.adapters.processes.capture import retained_capture


def preserve_failure(output: Path, error: BaseException) -> dict[str, Any]:
    (output / "native-failure-traceback.txt").write_text(
        "".join(traceback.format_exception(error))
    )
    facts: dict[str, Any] = {"traceback": "native-failure-traceback.txt"}
    capture = retained_capture(error)
    if capture is not None:
        for name, content in (("stdout", capture.stdout), ("stderr", capture.stderr)):
            path = output / ("native-failure-" + name + ".bin")
            path.write_bytes(content)
            facts[name] = path.name
        facts.update(
            returncode=capture.returncode,
            complete=capture.complete,
            termination=(
                None if capture.termination is None else asdict(capture.termination)
            ),
        )
    return facts
