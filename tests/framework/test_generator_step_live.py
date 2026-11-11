"""Actual fixed installed Generator worker in a named step, without model loading.

The engineering intent below is not the production resource journal/authority.
This verifies the fixed argv, wire installation, controller and kernel seams.
"""

import base64
from dataclasses import asdict
import json
import os
from pathlib import Path

from lab_generate_skill.adapters.models.generator_release import (
    verify_generator_release,
)
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    MAX_WORKER_PACKET,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.capture import CommandCapture
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.slurm.cgroup_quiescence import observe_user_quiescence
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.step_launch import (
    fixed_generator_step_argv,
    generator_step_name,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.generator_installation import GeneratorInstallation
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from generator_resource_fixtures import resource_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_linux_cgroups import actual_slurm_execution
from test_step_kernel_live import capture_json


def command_json(capture: CommandCapture) -> dict[str, object]:
    return {
        "argv": capture.argv,
        "returncode": capture.returncode,
        "complete": capture.complete,
        "stdout_base64": base64.b64encode(capture.stdout).decode(),
        "stderr_base64": base64.b64encode(capture.stderr).decode(),
        "termination": (
            asdict(capture.termination) if capture.termination is not None else None
        ),
    }


def test_actual_fixed_installed_generator_step(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    execution, accounting = actual_slurm_execution()
    c = resource_case(
        tmp_path, installed_sources.executable, installation=installed_sources
    )
    control = DeadlineControl(90, "fixed-generator-step-engineering")
    release = verify_generator_release(c.spec, c.evidence, c.workspace_root, control)
    parent_readings = KernelReadings(control)
    parent = read_process_identity(parent_readings, os.getpid(), execution.uid)
    token = c.spec.token.model_copy(
        update={
            "owner": c.spec.token.owner.model_copy(update={"job_id": execution.job_id})
        }
    )
    argv = fixed_generator_step_argv(
        token,
        execution,
        parent.node_id,
        python_executable=c.spec.python_executable,
        srun_executable="/usr/bin/srun",
    )
    intent = c.evidence.put(
        json.dumps(
            {
                "schema": "engineering-step-intent/1",
                "argv": argv,
                "original_execution": execution.model_dump(mode="json"),
                "parent": parent.model_dump(mode="json"),
                "production_authority": False,
            },
            sort_keys=True,
        ).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="engineering-step-intent/1",
            visibility="private",
            producer="engineering-test",
        ),
    )
    channel = FramedProcessSession(
        argv, max_frame_bytes=MAX_WORKER_PACKET, cuda_visible_devices="0"
    )
    engine = SupervisedGeneratorEngine(
        channel,
        token.expected_resource_id,
        c.spec.artifact,
        c.spec.engine_config,
        GeneratorInstallation(
            manifest_ref=c.spec.release_ref,
            manifest=release.manifest,
            workspace_root=str(c.workspace_root),
            python_executable=c.spec.python_executable,
        ),
    )
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "generator-step-observation.json"
    )
    payload: dict[str, object] = {
        "schema": "actual-fixed-generator-step-check/1",
        "intent": intent.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json"),
        "raw_accounting_base64": base64.b64encode(accounting).decode(),
        "argv": argv,
        "production_authority": False,
        "model_or_api_calls": 0,
    }
    primary: BaseException | None = None
    try:
        channel.start(control)
        assert channel.process_id is not None
        launcher_readings = KernelReadings(control)
        launcher = read_process_identity(
            launcher_readings, channel.process_id, execution.uid
        )
        worker = engine.configure(control)
        assert worker.process_id != launcher.process_id
        assert engine.installed_sources is not None
        live = observe_process_cgroup(execution, worker, control)
        launcher_live = observe_process_cgroup(execution, launcher, control)
        assert launcher_live.membership.step_id == "batch"
        target = SlurmStepTarget(
            resources="single_gpu",
            execution=execution,
            step_name=generator_step_name(token),
            launcher=launcher,
            worker=live.membership,
        )
        observer = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path("/usr/bin/scontrol")
        )
        observed = observer.observe(target, control)
        assert observed.controller is not None
        assert (
            engine.configure(control) == worker
        )  # No second wire configure or new step.
        assert (
            observe_process_cgroup(execution, worker, control).membership
            == live.membership
        )
        payload.update(
            launcher=launcher.model_dump(mode="json"),
            worker=worker.model_dump(mode="json"),
            installed_sources=engine.installed_sources.model_dump(mode="json"),
            controller=observed.controller.model_dump(mode="json"),
            live_commands=[command_json(x) for x in observed.commands],
            live_kernel=capture_json(live.capture),
            launcher_kernel=capture_json(launcher_live.capture),
        )
        engine.close(DeadlineControl(15, "fixed-step-close"))
        ending = engine.capture.termination
        assert (
            ending is not None
            and ending.state == "reaped"
            and ending.process_id == launcher.process_id
            and ending.returncode == 0
            and not ending.cleanup_errors
        )
        closed = observe_user_quiescence(
            live.membership, DeadlineControl(15, "original-user-observation")
        )
        absent = observer.observe(
            target, DeadlineControl(15, "controller-absence"), require_absent=True
        )
        assert absent.controller is None
        payload.update(
            termination=asdict(ending),
            quiescence=closed.facts.model_dump(mode="json"),
            closure_kernel=capture_json(closed.capture),
            absent_commands=[command_json(x) for x in absent.commands],
            passed=True,
        )
    except BaseException as error:
        primary = error
        payload.update(
            passed=False,
            error_type=type(error).__name__,
            stage=getattr(error, "slurm_step_stage", None),
            failed_commands=[
                command_json(x) for x in getattr(error, "slurm_step_commands", ())
            ],
        )
        raise
    finally:
        cleanup_error: BaseException | None = None
        try:
            engine.close(DeadlineControl(15, "fixed-step-final-close"))
        except BaseException as error:
            cleanup_error = error
            payload["cleanup_error_type"] = type(error).__name__
        payload["final_capture"] = command_json(engine.capture)
        with output.open("x") as stream:
            os.chmod(output, 0o600)
            json.dump(payload, stream, indent=2)
        if cleanup_error is not None:
            raise BaseExceptionGroup(
                "Engineering step and close failed",
                ([primary] if primary is not None else []) + [cleanup_error],
            )
