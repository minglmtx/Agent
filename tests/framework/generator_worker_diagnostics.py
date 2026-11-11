"""Persist engineering child diagnostics without replacing the original error.

All three bounded records are attempted even if one write fails. Return the
original exception on success, otherwise a group containing it first and every
recording failure. The caller raises the returned error; this grants no retry.
"""

import json
from dataclasses import asdict
from pathlib import Path
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.processes.remote_errors import describe_error


def record_failure(
    output: Path, phase: str, error: BaseException, capture: CommandCapture
) -> BaseException:
    failures: list[BaseException] = []
    records = (
        ("stdout.bin", capture.stdout),
        ("stderr.log", capture.stderr),
        (
            "error.json",
            (
                json.dumps(
                    {
                        "error": describe_error(error).model_dump(mode="json"),
                        "termination": (
                            None
                            if capture.termination is None
                            else asdict(capture.termination)
                        ),
                    },
                    indent=2,
                )
                + "\n"
            ).encode(),
        ),
    )
    for suffix, content in records:
        try:
            (output / (phase + "-" + suffix)).write_bytes(content)
        except BaseException as failure:
            failures.append(failure)
    if failures:
        return BaseExceptionGroup(
            "Worker failure and diagnostic recording failures", [error, *failures]
        )
    return error
