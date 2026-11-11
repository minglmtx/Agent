"""Canonical raw kernel/controller encoding shared by fixed step providers."""

import base64
from dataclasses import asdict
import json
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from .kernel_capture import KernelCapture


def encode_step_raw(
    schema: str,
    target: SlurmStepTarget | None,
    phase: str,
    kernels: list[KernelCapture],
    commands: list[CommandCapture],
    error: BaseException | None,
) -> bytes:
    payload = {
        "schema_version": schema,
        "target": None if target is None else target.model_dump(mode="json"),
        "phase": phase,
        "error": (
            None if error is None else describe_error(error).model_dump(mode="json")
        ),
        "kernel": [
            {
                "reads": [
                    {
                        "path": r.path,
                        "complete": r.complete,
                        "content_base64": base64.b64encode(r.content).decode(),
                    }
                    for r in k.reads
                ],
                "controls": [asdict(c) for c in k.controls],
                "failed_control_path": k.failed_control_path,
                "pinned_controls": [asdict(c) for c in k.pinned_controls],
            }
            for k in kernels
        ],
        "commands": [
            {
                "argv": c.argv,
                "returncode": c.returncode,
                "complete": c.complete,
                "stdout_base64": base64.b64encode(c.stdout).decode(),
                "stderr_base64": base64.b64encode(c.stderr).decode(),
                "termination": None if c.termination is None else asdict(c.termination),
            }
            for c in commands
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
