"""Real CPU-step byte conservation using the fixed launch flags, no site effects."""

import json
import os
from pathlib import Path
import sys
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.slurm.step_launch import fixed_site_step_argv
from site_worker_fixtures import configuration
from test_linux_cgroups import actual_slurm_execution
from test_generator_step_live import command_json

# Explicit binary flushing: production workers also flush each complete frame.
ECHO = """
import sys
for _ in range(4):
    header = sys.stdin.buffer.read(4)
    if not header:
        break
    assert len(header) == 4
    payload = sys.stdin.buffer.read(int.from_bytes(header, 'big'))
    sys.stdout.buffer.write(header + payload)
    sys.stdout.buffer.flush()
"""


def test_real_cpu_step_preserves_binary_frames() -> None:
    compile(ECHO, "binary-echo", "exec")
    execution, _ = actual_slurm_execution()
    config = configuration(job_id=execution.job_id)
    argv = fixed_site_step_argv(
        config.token,
        execution,
        os.environ["SLURMD_NODENAME"],
        python_executable=sys.executable,
        srun_executable="/usr/bin/srun",
    )
    # Replace only the fixed module with a bounded diagnostic child. This tests
    # transport flags, not installed worker authority or site initialization.
    channel = FramedProcessSession(argv[:-2] + ("-c", ECHO), max_frame_bytes=4096)
    control = DeadlineControl(30, "binary-step-probe")
    facts: dict[str, object] = {"passed": False, "matched_lengths": []}
    matched: list[int] = []
    try:
        channel.start(control)
        for payload in (b"a" * 10, b"a" * 13, bytes(range(256)) * 2, b"z" * 266):
            actual = channel.exchange(payload, control=control)
            assert actual == payload
            matched.append(len(payload))
        channel.finish(control=control)
        facts["passed"] = True
    finally:
        channel.abort(DeadlineControl(5, "binary-step-close"))
        facts["matched_lengths"] = matched
        facts["capture"] = command_json(channel.capture)
        (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "binary-step-probe.json"
        ).write_text(json.dumps(facts, indent=2) + "\n")
