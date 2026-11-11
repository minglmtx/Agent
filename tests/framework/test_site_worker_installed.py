"""Fixed installed Admin worker in its original CPU step; engineering authority."""

from datetime import datetime, timezone
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request
from typing import Any
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.adapters.sites.worker_client import SupervisedSiteInstance
from lab_generate_skill.adapters.sites.worker_protocol import MAX_PACKET
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.step_launch import (
    fixed_site_step_argv,
    site_step_name,
)
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.slurm.cgroup_pin import pin_user_tree, PinnedUserTree
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from site_worker_fixtures import configuration, operation, Authority
from test_admin_database_native import IMAGE, IMAGE_SHA
from test_linux_cgroups import actual_slurm_execution
from test_generator_step_live import command_json
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
import pytest


def test_installed_admin_in_original_cpu_step(
    installed_sources: InstalledFixture,
) -> None:
    execution, accounting = actual_slurm_execution()
    parent_root = Path(tempfile.mkdtemp(prefix="lab-site-worker-", dir="/tmp"))
    config = configuration(
        storage_installation(installed_sources), job_id=execution.job_id
    )
    files = SiteFilesPlan(
        instance_id=config.token.expected_resource_id,
        workspace_root="/anvme/workspace/r102bf10-lab-generate-skill",
        source_path=str(IMAGE),
        node_root=str(parent_root / "instance"),
        image=ReleaseFile(
            path=IMAGE.name, sha256=IMAGE_SHA, size_bytes=1356492800, executable=False
        ),
    )
    config = SiteWorkerConfiguration.model_validate(
        {**config.model_dump(), "files": files}
    )
    parent = current_process_identity()
    control = DeadlineControl(240, "site-installed-start")
    argv = fixed_site_step_argv(
        config.token,
        execution,
        parent.node_id,
        python_executable=config.installation.python_executable,
        srun_executable="/usr/bin/srun",
    )
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    # Engineering intent only; production ResourceJournal assembly remains pending.
    (output / "site-engineering-intent.json").write_text(
        json.dumps(
            dict(
                configuration=config.model_dump(mode="json"),
                argv=argv,
                resource_journal_integrated=False,
            ),
            indent=2,
        )
        + "\n"
    )
    channel = FramedProcessSession(argv, max_frame_bytes=MAX_PACKET)
    client = SupervisedSiteInstance(channel, "installed-site", config, Authority())
    op = operation(config)
    pin: PinnedUserTree | None = None
    primary: BaseException | None = None
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        resource_journal_integrated=False,
        formal_site_authority=False,
        accounting=accounting.decode(),
    )
    safe = False
    try:
        channel.start(control)
        assert channel.process_id is not None
        launcher = read_process_identity(
            KernelReadings(control), channel.process_id, execution.uid
        )
        ready = client.configure(op, control=control)
        ownership = ready.owner_guard
        assert ownership.controller == parent and ownership.supervisor != launcher
        assert not Path(files.node_root).exists()
        live = observe_process_cgroup(execution, ownership.worker, control)
        supervisor = observe_process_cgroup(execution, ownership.supervisor, control)
        assert supervisor.membership.step_id == live.membership.step_id
        assert supervisor.membership.user_inode == live.membership.user_inode
        target = SlurmStepTarget(
            execution=execution,
            step_name=site_step_name(config.token),
            resources="cpu_only",
            launcher=launcher,
            worker=live.membership,
        )
        pin = pin_user_tree(target.worker, control)
        observer = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path("/usr/bin/scontrol")
        )
        observed = observer.observe(target, control)
        assert observed.controller is not None and observed.controller.gpu_type is None
        started = client.start(op, control=control)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(started.endpoint, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
            assert (
                response.status == 200
                and len(body) <= 1024 * 1024
                and b"login" in body.lower()
            )
        facts.update(
            started=started.model_dump(mode="json"),
            owner_guard=ownership.model_dump(mode="json"),
            installed_sources=ready.installed_sources.model_dump(mode="json"),
            identity_pinned_before_site_effects=True,
            target=target.model_dump(mode="json"),
            controller=observed.controller.model_dump(mode="json"),
            login_bytes=len(body),
        )
        exits = client.close(
            op.cleanup("site-close", now=datetime.now(timezone.utc), seconds=30),
            control=DeadlineControl(25, "site-close"),
        )
        assert exits and len(exits) == 5 and all(f.state == "reaped" for f in exits)
        ending = channel.capture.termination
        assert (
            ending is not None
            and ending.state == "reaped"
            and ending.returncode == 0
            and not ending.cleanup_errors
        )
        absent = observer.wait_absent(
            observed.controller, DeadlineControl(15, "site-step-absence")
        )
        closed = pin.observe(DeadlineControl(15, "site-original-domain"))
        assert absent.controller is None and closed.facts.original == target.worker
        safe = True
        facts.update(
            passed=True,
            exits=[f.model_dump(mode="json") for f in exits],
            termination=asdict(ending),
            quiescence=closed.facts.model_dump(mode="json"),
        )
    except BaseException as error:
        primary = error
        facts.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        errors: list[BaseException] = []
        try:
            client.close(
                op.cleanup("final-close", now=datetime.now(timezone.utc), seconds=30),
                control=DeadlineControl(25, "final-close"),
            )
        except BaseException as error:
            errors.append(error)
        if pin is not None:
            try:
                pin.close()
            except BaseException as error:
                errors.append(error)
        facts["final_capture"] = command_json(channel.capture)
        facts["last_reply"] = (
            client.last_reply.model_dump(mode="json")
            if client.last_reply is not None
            else None
        )
        facts["private_root_visible_from_parent"] = Path(files.node_root).exists()
        for folder in (Path(files.log_root), Path(files.state_root)):
            for log in folder.glob("*.log"):
                try:
                    if not log.is_symlink() and log.is_file():
                        with log.open("rb") as stream:
                            stream.seek(max(0, log.stat().st_size - 20000))
                            (
                                output / ("site-native-" + folder.name + "-" + log.name)
                            ).write_bytes(stream.read(20000))
                except BaseException as error:
                    errors.append(error)
        facts["private_root_removed"] = safe and not errors
        if safe and not errors:
            shutil.rmtree(parent_root)
        facts["cleanup_errors"] = [type(e).__name__ + ": " + str(e) for e in errors]
        (output / "site-worker-native.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
        if errors:
            raise BaseExceptionGroup(
                "Site engineering check and cleanup failed",
                ([primary] if primary else []) + errors,
            ) from None


def test_installed_site_rejects_missing_asset_before_native_effects(
    installed_sources: InstalledFixture,
) -> None:
    execution, _ = actual_slurm_execution()
    config = configuration(
        storage_installation(installed_sources), job_id=execution.job_id
    )
    # Deliberately missing workspace: the real installer/guard/transport run, but
    # NodeSiteFiles must reject before creating a root, port or service.
    parent = current_process_identity()
    argv = fixed_site_step_argv(
        config.token,
        execution,
        parent.node_id,
        python_executable=config.installation.python_executable,
        srun_executable="/usr/bin/srun",
    )
    channel = FramedProcessSession(argv, max_frame_bytes=MAX_PACKET)
    client = SupervisedSiteInstance(
        channel, "installed-site-reject", config, Authority()
    )
    op = operation(config)
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    facts: dict[str, Any] = dict(
        passed=False, engineering_only=True, native_site_started=False
    )
    original: BaseException | None = None
    try:
        control = DeadlineControl(60, "site-pre-effect-probe")
        channel.start(control)
        ready = client.configure(op, control=control)
        assert client.state == "configured" and client.last_reply is not None
        assert client.last_reply.started is None
        facts["prepared"] = ready.model_dump(mode="json")
        with pytest.raises(SiteWorkerFailure) as caught:
            client.start(op, control=control)
        reply = caught.value.reply
        assert client.prepared == ready and reply.owner_guard is None
        assert reply.error is not None and reply.error.type_name == "FileNotFoundError"
        assert reply.started is None and reply.exits == ()
        facts.update(passed=True, reply=reply.model_dump(mode="json"))
    except BaseException as error:
        original = error
        facts.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        cleanup: BaseException | None = None
        try:
            client.close(
                op.cleanup("probe-close", now=datetime.now(timezone.utc), seconds=20),
                control=DeadlineControl(15, "probe-close"),
            )
        except BaseException as error:
            cleanup = error
            facts.update(passed=False, cleanup_error=type(error).__name__)
        facts["final_capture"] = command_json(channel.capture)
        facts["last_reply"] = (
            client.last_reply.model_dump(mode="json") if client.last_reply else None
        )
        (output / "site-worker-pre-effect-probe.json").write_text(
            json.dumps(facts, indent=2) + "\n"
        )
        if cleanup:
            raise BaseExceptionGroup(
                "Site probe and cleanup failed",
                ([original] if original else []) + [cleanup],
            ) from None
