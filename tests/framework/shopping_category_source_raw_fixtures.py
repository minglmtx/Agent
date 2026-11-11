"""Synthetic observations through the actual role-bound producer encoder.

Only software fixtures use these fabricated kernel/controller readings. They
are not an independent physical observation, source qualification or live grant.
"""

from typing import Any
import pytest
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.slurm.kernel_capture import KernelCapture
from lab_generate_skill.adapters.slurm.kernel_files import KernelRead
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step


def complete_unit_closed_raw(patch: pytest.MonkeyPatch) -> None:
    def wrap(module: Any, role: Any) -> None:
        original = module.observe_closed

        def closed(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            if result is None:
                return None
            target, store = result.target, args[3]
            control = kwargs.get("metadata_control", args[4])
            termination = args[2]
            assert termination is not None and termination.state == "reaped"
            kernel = KernelCapture(
                (
                    KernelRead(
                        target.worker.user_path + "/cgroup.events",
                        b"populated 0\n",
                        True,
                    ),
                ),
                (),
            )
            command = CommandCapture(
                (
                    args[0].slurm.scontrol_executable,
                    "show",
                    "step",
                    target.execution.job_id + "." + target.worker.step_id,
                    "--json",
                ),
                0,
                b'{"steps":[]}',
                b"",
                True,
                termination,
            )
            reference = WorkerStepEvidence(role).save(
                store, target, "closed", [kernel], [command], control
            )
            return result.model_copy(update={"evidence": reference})

        patch.setattr(module, "observe_closed", closed)

    wrap(site_step, "site")
    wrap(browser_step, "browser")
