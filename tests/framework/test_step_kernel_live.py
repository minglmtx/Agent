"""Real dedicated Slurm step: batch observes worker, then the original empty tree.

Engineering child only, no project worker, model, API, production authority or
resource ledger. This tests kernel APIs; the production step assembly is separate.
"""

import base64
from dataclasses import asdict
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest

from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.worker_identity import parse_process_start
from lab_generate_skill.adapters.slurm.cgroup_quiescence import observe_user_quiescence
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.process_identity import ProcessIdentity
from test_linux_cgroups import actual_slurm_execution

CHILD = """
import json, os, socket, sys
from pathlib import Path
print(json.dumps({'pid':os.getpid(), 'node':socket.gethostname(),
    'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'stat':Path('/proc/self/stat').read_text()}), flush=True)
assert sys.stdin.readline() == 'exit\\n'
"""


def capture_json(capture: KernelCapture) -> dict[str, object]:
    return {
        "reads": [
            {
                "path": r.path,
                "complete": r.complete,
                "content_base64": base64.b64encode(r.content).decode(),
            }
            for r in capture.reads
        ],
        "controls": [asdict(c) for c in capture.controls],
        "failed_control_path": capture.failed_control_path,
    }


def test_actual_step_worker_and_original_quiescence() -> None:
    execution, accounting = actual_slurm_execution()
    argv = [
        "/usr/bin/srun",
        "--jobid=" + execution.job_id,
        "--job-name=lab-kernel-step-check-" + execution.job_id,
        "--exact",
        "--exclusive",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=1",
        "--gres=gpu:1",
        "--mpi=none",
        "--kill-on-bad-exit=1",
        "--immediate=5",
        "--export=ALL",
        sys.executable,
        "-I",
        "-B",
        "-c",
        CHILD,
    ]
    child = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        start_new_session=True,
        close_fds=True,
        bufsize=0,
    )
    try:
        assert child.stdout is not None and child.stdin is not None
        control = DeadlineControl(35, "step-kernel-engineering-live")
        raw = bytearray()
        while not raw.endswith(b"\n"):
            ready, _, _ = select.select(
                [child.stdout], [], [], min(2, control.checkpoint())
            )
            if ready:
                chunk = os.read(child.stdout.fileno(), 1)
                assert chunk, "Step exited before its identity handshake"
                raw.extend(chunk)
                assert len(raw) <= 32768
        handshake = json.loads(raw)
        worker = ProcessIdentity(
            node_id=handshake["node"],
            boot_id=handshake["boot"],
            process_id=handshake["pid"],
            start_ticks=parse_process_start(
                handshake["stat"].encode(), handshake["pid"]
            ),
        )
        assert child.pid != worker.process_id and os.getpid() != worker.process_id
        try:
            live = observe_process_cgroup(execution, worker, control)
        except BaseException as error:
            capture = getattr(error, "slurm_kernel_capture", None)
            if isinstance(capture, KernelCapture):
                failed_output = (
                    Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
                    / "step-kernel-failure.json"
                )
                with failed_output.open("x") as stream:
                    os.chmod(failed_output, 0o600)
                    json.dump(
                        {
                            "worker": worker.model_dump(mode="json"),
                            "launcher_pid": child.pid,
                            "execution": execution.model_dump(mode="json"),
                            "error_type": type(error).__name__,
                            "capture": capture_json(capture),
                        },
                        stream,
                        indent=2,
                    )
            raise
        again = observe_process_cgroup(execution, worker, control)
        assert (
            live.membership == again.membership and live.membership.step_id != "batch"
        )
        with pytest.raises(ValueError, match="still exists"):
            observe_user_quiescence(live.membership, control)
        stdout, stderr = child.communicate(b"exit\n", timeout=20)
        assert child.returncode == 0, stderr.decode(errors="replace")
        assert stdout == b"" and stderr == b""
        cleanup = DeadlineControl(15, "step-kernel-engineering-closure")
        closed = observe_user_quiescence(live.membership, cleanup)
        repeated = observe_user_quiescence(live.membership, cleanup)
        assert closed.facts == repeated.facts
        assert closed.facts.writer_status == "missing"
        output = (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
            / "step-kernel-observation.json"
        )
        payload = {
            "schema": "actual-step-kernel-check/1",
            "execution": execution.model_dump(mode="json"),
            "raw_accounting_base64": base64.b64encode(accounting).decode(),
            "argv": argv,
            "launcher_pid": child.pid,
            "launcher_exit": child.returncode,
            "worker": worker.model_dump(mode="json"),
            "membership": live.membership.model_dump(mode="json"),
            "quiescence": closed.facts.model_dump(mode="json"),
            "live_capture": capture_json(live.capture),
            "closure_capture": capture_json(closed.capture),
            "repeat_live_and_closure": True,
            "production_authority": False,
            "model_or_api_calls": 0,
        }
        with output.open("x") as stream:
            os.chmod(output, 0o600)
            json.dump(payload, stream, indent=2)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.communicate(timeout=5)
        for pipe in (child.stdin, child.stdout, child.stderr):
            if pipe is not None:
                pipe.close()
