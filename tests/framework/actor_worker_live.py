"""Actual installed supervised Actor GPU child; engineering invocation only."""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.actor_worker_protocol import MAX_WORKER_PACKET
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.processes.owner_pidfd import pinned_owner, ended
from lab_generate_skill.adapters.releases.artifact_copy import (
    copy_pinned_file,
    sync_directory,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.runtime.lifecycle import OperationGuards
from actor_engine_fixtures import config
from actor_engine_live import saved_turn
from actor_installation_fixtures import installed_declaration
from generator_engine_live import staging, verify_source, W
from generator_model_assets import pinned_causal_model
from generator_worker_diagnostics import record_failure
from test_slurm_commands import Cancel
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_actual_installed_actor_gpu(installed_sources: InstalledFixture) -> None:
    receipt = Path(os.environ["LAB_ACTOR_SOFTWARE_RECEIPT"])
    verify_source(receipt)
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "actor-worker-native"
    output.mkdir(exist_ok=False)

    def save(name: str, raw: bytes) -> None:
        with (output / name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(output)

    controls = OperationGuards(SystemClock(), Cancel())
    operation = OperationContext(
        operation_id="actor-worker-leaf",
        run_id="run",
        owner_id="owner",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=510),
    )
    control = controls.bind(operation)
    original, inventory_sha = pinned_causal_model(
        W, "models/Qwen2.5-7B-Instruct", "qwen25-original"
    )
    request = prepare_actor(saved_turn())
    params = LocalActorParameters(
        max_input_tokens=28672,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
        enable_thinking=False,
    )
    cleanup_allowed = True
    facts: dict[str, Any] = {
        "job_id": os.environ["SLURM_JOB_ID"],
        "model_inventory_sha256": inventory_sha,
        "software_receipt": str(receipt),
        "production_authority": False,
        "production_launch_ledger": False,
        "actual_browser_actions": 0,
        "paid_calls": 0,
    }
    with staging(preserve_if=lambda: not cleanup_allowed) as local:
        began = time.monotonic()
        for member in original.files:
            (local / member.path).parent.mkdir(parents=True, exist_ok=True)
            copy_pinned_file(Path(original.root), local, member, control)
        local.chmod(0o555)
        facts["copy_seconds"] = time.monotonic() - began
        artifact = ReleaseArtifact(
            artifact_id="actor-worker-model", root=str(local), files=original.files
        )
        cfg = config().model_copy(update={"context_window": 32768})
        worker = FramedProcessSession(
            (
                str(installed_sources.executable),
                "-I",
                "-B",
                "-m",
                "lab_generate_skill.bootstrap.actor_worker",
            ),
            max_frame_bytes=MAX_WORKER_PACKET,
            cuda_visible_devices=os.environ["CUDA_VISIBLE_DEVICES"],
        )
        engine = SupervisedActorEngine(
            worker,
            "actor-engineering",
            artifact,
            cfg,
            installed_declaration(installed_sources),
        )
        save(
            "launch-intent.json",
            json.dumps(
                {
                    "artifact": artifact.model_dump(mode="json"),
                    "config": cfg.model_dump(mode="json"),
                    "production_launch_ledger": False,
                }
            ).encode(),
        )
        cleanup_allowed = False
        primary: BaseException | None = None
        try:
            worker.start(control)
            engine.configure(control)
            owner = engine.owner_guard
            assert owner is not None and engine.installed_sources is not None
            save("owner-guard.json", owner.model_dump_json().encode())
            save(
                "installed-sources.json",
                engine.installed_sources.model_dump_json().encode(),
            )
            with (
                pinned_owner(owner.supervisor, control) as supervisor_fd,
                pinned_owner(owner.worker, control) as worker_fd,
            ):
                invocation_error: BaseException | None = None
                try:
                    began = time.monotonic()
                    engine.validate(request, params, control)
                    facts["load_validate_seconds"] = time.monotonic() - began
                    save(
                        "generation-intent.json",
                        json.dumps(
                            {
                                "request": request.model_dump(mode="json"),
                                "parameters": params.model_dump(mode="json"),
                                "engineering_only": True,
                            }
                        ).encode(),
                    )
                    exchange = engine.generate_exchange(request, params, control)
                    save("generation-command.json", exchange.command)
                    save("generation-reply.json", exchange.reply)
                    reply = exchange.decoded_reply
                    assert reply.output is not None
                    facts.update(
                        actual_inferences=1, output=reply.output.model_dump(mode="json")
                    )
                except BaseException as error:
                    invocation_error = error
                    raise
                finally:
                    cleanup = operation.cleanup(
                        "actor-worker-close", now=datetime.now(timezone.utc), seconds=30
                    )
                    try:
                        engine.close(controls.bind(cleanup))
                    except BaseException as error:
                        if invocation_error is not None:
                            raise BaseExceptionGroup(
                                "Actor invocation and close failed",
                                [invocation_error, error],
                            ) from None
                        raise
                    facts["original_supervisor_exited"] = ended(supervisor_fd)
                    facts["original_worker_exited"] = ended(worker_fd)
                    cleanup_allowed = (
                        facts["original_supervisor_exited"]
                        and facts["original_worker_exited"]
                    )
            assert cleanup_allowed and worker.capture.complete
            assert (
                worker.capture.termination is not None
                and worker.capture.termination.returncode == 0
            )
            facts["graceful_zero_exit"] = True
        except BaseException as error:
            primary = record_failure(output, "operation", error, worker.capture)
            raise primary
        finally:
            if not cleanup_allowed:
                try:
                    worker.abort(
                        controls.bind(
                            operation.cleanup(
                                "actor-worker-abort",
                                now=datetime.now(timezone.utc),
                                seconds=10,
                            )
                        )
                    )
                except BaseException as error:
                    if primary is not None:
                        raise BaseExceptionGroup(
                            "Actor worker and abort failed", [primary, error]
                        ) from None
                    raise
            save("facts.json", json.dumps(facts, ensure_ascii=False, indent=2).encode())
    verify_source(receipt)
    save(
        "staging-closed.json",
        json.dumps({"removed": not local.parent.exists()}).encode(),
    )
