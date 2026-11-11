"""Installed browser in CPU-only step, original kernel domain and bounded close.

Engineering loopback only. This verifies the actual fixed worker and observed
resource domain, not production permission or ResourceJournal integration.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from collections.abc import Iterator
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading

from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.worker_protocol import MAX_PACKET
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.slurm.cgroup_pin import pin_user_tree, PinnedUserTree
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.kernel_capture import KernelReadings
from lab_generate_skill.adapters.slurm.kernel_identity import read_process_identity
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.slurm.step import SlurmStepObserver
from lab_generate_skill.adapters.slurm.step_launch import (
    fixed_browser_step_argv,
    browser_step_name,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from browser_worker_fixtures import configuration
from browsergym_fixtures import operation, LoopbackAuthority
from evidence_control_fixtures import EvidenceFixtureStore
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_linux_cgroups import actual_slurm_execution
from test_slurm_cpu_step import browser_token
from test_generator_step_live import command_json
from test_step_kernel_live import capture_json


@pytest.fixture
def cpu_page() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><title>CPU browser</title><label for='description'>Description</label><input id='description'></html>"
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_actual_browser_cpu_step_and_original_tree_close(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    cpu_page: str,
) -> None:
    execution, accounting = actual_slurm_execution()
    base = configuration(storage_installation(installed_sources), cpu_page)
    scope = base.spec.scope.model_copy(
        update={
            "owner": base.spec.scope.owner.model_copy(
                update={"job_id": execution.job_id}
            )
        }
    )
    config = BrowserWorkerConfiguration.model_validate(
        base.model_copy(update={"spec": base.spec.model_copy(update={"scope": scope})})
    )
    token = browser_token().model_copy(
        update={"owner": scope.owner, "attempt_id": scope.attempt_id}
    )
    control = DeadlineControl(90, "browser-cpu-step-engineering")
    parent = read_process_identity(KernelReadings(control), os.getpid(), execution.uid)
    argv = fixed_browser_step_argv(
        token,
        execution,
        parent.node_id,
        python_executable=config.installation.python_executable,
        srun_executable="/usr/bin/srun",
    )
    store = EvidenceFixtureStore(tmp_path)
    intent = store.put(
        json.dumps(
            {
                "schema_version": "browser-cpu-step-engineering-intent/1",
                "argv": argv,
                "token": token.model_dump(mode="json"),
                "execution": execution.model_dump(mode="json"),
                "configuration": config.model_dump(mode="json"),
                "production_authority": False,
            }
        ).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="browser-cpu-step-engineering-intent/1",
            visibility="private",
            producer="engineering-test",
        ),
    )
    channel = FramedProcessSession(argv, max_frame_bytes=MAX_PACKET)
    client = SupervisedBrowserSession(
        channel, token.expected_resource_id, config, LoopbackAuthority()
    )
    session = EvidenceBrowserSession(client, store)
    op = operation(config.spec, "initial")
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "browser-cpu-step.json"
    payload: dict[str, object] = {
        "schema_version": "browser-cpu-step-check/1",
        "passed": False,
        "intent": intent.model_dump(mode="json"),
        "argv": argv,
        "production_authority": False,
        "resource_journal_integrated": False,
        "formal_experiment": False,
        "model_or_api_calls": 0,
        "accounting": accounting.decode(),
    }
    pinned: PinnedUserTree | None = None
    primary: BaseException | None = None
    try:
        channel.start(control)
        assert channel.process_id is not None
        launcher = read_process_identity(
            KernelReadings(control), channel.process_id, execution.uid
        )
        initial = session.start(op, control=control)
        assert (
            client.last_reply is not None and client.last_reply.owner_guard is not None
        )
        guard = client.last_reply.owner_guard
        assert guard.controller == parent and guard.supervisor != launcher
        live = observe_process_cgroup(execution, guard.worker, control)
        supervisor = observe_process_cgroup(execution, guard.supervisor, control)
        launcher_live = observe_process_cgroup(execution, launcher, control)
        assert launcher_live.membership.step_id == "batch"
        assert live.membership.user_inode == supervisor.membership.user_inode
        target = SlurmStepTarget(
            execution=execution,
            step_name=browser_step_name(token),
            resources="cpu_only",
            launcher=launcher,
            worker=live.membership,
        )
        pinned = pin_user_tree(target.worker, control)
        observer = SlurmStepObserver(
            SlurmCommandRunner(), scontrol=Path("/usr/bin/scontrol")
        )
        observed = observer.observe(target, control)
        assert observed.controller is not None and observed.controller.gpu_type is None
        assert (
            observe_process_cgroup(execution, guard.worker, control).membership
            == live.membership
        )
        assert client.last_readout is not None
        text = client.last_readout.observation.text or ""
        match = re.search(r"\[([^\]]+)\] textbox ['\"]Description['\"]", text)
        assert match is not None, text
        result = session.step(
            BrowserAction(
                action_id="cpu-fill",
                protocol_id="browsergym-highlevel-v1",
                name="fill",
                payload=f"fill({match.group(1)!r}, 'CPU only')",
            ),
            operation(config.spec, "fill"),
            control=control,
        )
        assert client.last_readout is not None and "CPU only" in (
            client.last_readout.observation.text or ""
        )
        payload.update(
            target=target.model_dump(mode="json"),
            guard=guard.model_dump(mode="json"),
            controller=observed.controller.model_dump(mode="json"),
            initial_ref=initial.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
            live_commands=[command_json(c) for c in observed.commands],
            live_kernel=capture_json(live.capture),
            supervisor_kernel=capture_json(supervisor.capture),
            pinned_kernel=capture_json(pinned.opened),
        )
        close_op = op.cleanup("close", now=datetime.now(timezone.utc), seconds=30)
        client.close(close_op, control=DeadlineControl(15, "browser-cpu-close"))
        ending = channel.capture.termination
        assert (
            ending is not None and ending.state == "reaped" and ending.returncode == 0
        )
        assert ending.process_id == launcher.process_id and not ending.cleanup_errors
        closed = pinned.observe(DeadlineControl(15, "browser-original-tree"))
        absent = observer.wait_absent(
            observed.controller, DeadlineControl(15, "browser-step-absence")
        )
        assert absent.controller is None and closed.facts.original == target.worker
        payload.update(
            termination=asdict(ending),
            closed=closed.facts.model_dump(mode="json"),
            closure_kernel=capture_json(closed.capture),
            absent_commands=[command_json(c) for c in absent.commands],
            passed=True,
        )
    except BaseException as error:
        primary = error
        payload["error_type"] = type(error).__name__
        payload["failed_commands"] = [
            command_json(c) for c in getattr(error, "slurm_step_commands", ())
        ]
        raise
    finally:
        errors: list[BaseException] = []
        try:
            client.close(
                op.cleanup("final-close", now=datetime.now(timezone.utc), seconds=30),
                control=DeadlineControl(15, "browser-final-close"),
            )
        except BaseException as error:
            errors.append(error)
            try:
                channel.abort(DeadlineControl(5, "browser-final-abort"))
            except BaseException as abort:
                errors.append(abort)
        if pinned is not None:
            try:
                pinned.close()
            except BaseException as error:
                errors.append(error)
        payload["cleanup_errors"] = [type(e).__name__ for e in errors]
        payload["final_capture"] = command_json(channel.capture)
        if errors:
            payload["passed"] = False
        with output.open("x") as stream:
            os.chmod(output, 0o600)
            json.dump(payload, stream, indent=2)
        if errors:
            raise BaseExceptionGroup(
                "Browser CPU step and cleanup failed",
                ([primary] if primary is not None else []) + errors,
            )
