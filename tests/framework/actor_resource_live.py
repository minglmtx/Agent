"""Actual registered Actor GPU -> original trace -> retained return -> closure.

Engineering authority and archived public observation only. No current website,
formal source admission, browser action, Teacher request or training data.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.processes.capture import retained_capture
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.application.actor_generation import execute_actor_generation
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.actor_step import ActorStepStarted, ActorStepClosed
from lab_generate_skill.domain.release import ReleaseArtifact
from actor_registered_fixtures import registered_call
from actor_resource_fixtures import resource_case
from actor_release_fixtures import freeze_model_release
from actor_engine_live import saved_turn
from generator_engine_live import staging, verify_source, W
from generator_model_assets import pinned_causal_model
from generator_worker_diagnostics import record_failure
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_actual_registered_actor_recorded_generation(
    installed_sources: InstalledFixture,
) -> None:
    receipt = Path(os.environ["LAB_ACTOR_SOFTWARE_RECEIPT"])
    verify_source(receipt)
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "actor-resource-native"
    output.mkdir()
    c = resource_case(
        output / "resource",
        installed_sources.executable,
        installation=installed_sources,
    )
    # Choose the engineering operation budget before it is first bound. This
    # includes first-time immutable publication and local staging, not retries.
    c.op = c.op.model_copy(
        update={"deadline": datetime.now(timezone.utc) + timedelta(seconds=510)}
    )
    control = c.controls.bind(c.op)
    artifact, inventory_sha = pinned_causal_model(
        W, "models/Qwen2.5-7B-Instruct", "qwen25-original"
    )
    publication_root = W / "assets/frozen-actor-models-20261028-v1"
    publication_root.mkdir(exist_ok=True)
    artifact = FileArtifactFreezer(W, publication_root).freeze(
        artifact, "qwen25-7b-" + inventory_sha[:16], control
    )
    config = c.spec.engine_config.model_copy(update={"context_window": 32768})
    release_ref, model_ref = freeze_model_release(
        output / "actual-model-release",
        c.evidence,
        artifact,
        config,
        model_name="Qwen/Qwen2.5-7B-Instruct",
        installation=installed_sources.manifest,
    )
    c.workspace_root = W
    safe_to_remove = True
    engine: SupervisedActorEngine | None = None
    with staging(preserve_if=lambda: not safe_to_remove) as staged:
        for member in artifact.files:
            (staged / member.path).parent.mkdir(parents=True, exist_ok=True)
            copy_pinned_file(Path(artifact.root), staged, member, control)
        staged.chmod(0o555)
        c.spec = c.spec.model_copy(
            update={
                "artifact": ReleaseArtifact(
                    artifact_id=artifact.artifact_id,
                    root=str(staged),
                    files=artifact.files,
                ),
                "engine_config": config,
                "release_ref": release_ref,
                "model_binding_ref": model_ref,
            }
        )
        params = LocalActorParameters(
            max_input_tokens=28672,
            max_new_tokens=4096,
            seed=42,
            temperature=0.7,
            top_p=0.95,
            enable_thinking=False,
        )
        safe_to_remove = False
        try:
            with registered_actor(c.spec, c.op, **c.dependencies()) as engine:
                scope = ActorExecutionScope(
                    c.spec,
                    c.journal,
                    c.evidence,
                    engine,
                    c.op,
                    control,
                    cleanup_seconds=15,
                )
                local = registered_call(c, scope, output / "call", saved_turn(), params)
                result = execute_actor_generation(
                    local.dispatch, local.journal, local.model, c.controls
                )
                assert result.project().generation is not None
                assert len(local.business.completed) == 1
                execution = local.business.completed[0]
                for name, ref in (
                    ("command", execution.command_ref),
                    ("reply", execution.reply_ref),
                    ("response", execution.response_ref),
                ):
                    (output / (name + ".json")).write_bytes(
                        c.evidence.read(ref, control=control)
                    )
                (output / "trace.json").write_text(result.model_dump_json())
                (output / "execution.json").write_text(execution.model_dump_json())
            cleanup = c.op.cleanup(
                "actor-native-inspect", now=datetime.now(timezone.utc), seconds=30
            )
            record = c.journal.read(c.spec.token, cleanup)
            assert [e.state for e in record.events] == [
                "registered",
                "acquiring",
                "acquired",
                "closing",
                "closed",
            ]
            acquired = json.loads(
                c.evidence.read(
                    record.events[2].evidence[0], control=c.controls.bind(cleanup)
                )
            )
            ending = json.loads(
                c.evidence.read(
                    record.events[-1].evidence[0], control=c.controls.bind(cleanup)
                )
            )
            started = ActorStepStarted.model_validate_json(json.dumps(acquired["step"]))
            closed = ActorStepClosed.model_validate_json(
                json.dumps(ending["step_closed"])
            )
            assert closed.target == started.controller.target
            assert not ending["cleanup_errors"] and ending["primary"] is None
            assert ending["termination"]["state"] == "reaped"
            # Original history can still validate after closure, without loading
            # another model or reissuing a generate command.
            local.authority.verify_return(execution, c.controls.bind(cleanup))
            safe_to_remove = True
            facts = {
                "job_id": os.environ["SLURM_JOB_ID"],
                "software_receipt": str(receipt),
                "model_inventory_sha256": inventory_sha,
                "resource_binding": scope.binding.model_dump(mode="json"),
                "resource_record": record.model_dump(mode="json"),
                "output": execution.output.model_dump(mode="json"),
                "step_started": started.model_dump(mode="json"),
                "step_closed": closed.model_dump(mode="json"),
                "actual_inferences": 1,
                "actual_browser_actions": 0,
                "paid_calls": 0,
                "historical_return_verified_after_close": True,
                "source_observation_job": "4772787",
                "formal_source_admission": False,
                "engineering_authority": True,
                "frozen_model": artifact.model_dump(mode="json"),
            }
        except BaseException as error:
            capture = engine.capture if engine is not None else retained_capture(error)
            if capture is not None:
                raise record_failure(output, "operation", error, capture)
            raise
    assert not staged.parent.exists()
    verify_source(receipt)
    facts["local_staging_removed_after_step_closure"] = True
    (output / "facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n"
    )
