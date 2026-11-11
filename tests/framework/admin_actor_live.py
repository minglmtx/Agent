"""First actual selected Admin engineering task; paid calls disabled."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.domain.actor_projection import (
    MapRailsAddressableProjection,
    FullAxProjection,
)
from lab_generate_skill.bootstrap.actor_context_policy import (
    accepted_actor_context_policy,
)
from lab_generate_skill.bootstrap.actor_deployment import (
    accepted_actor_defaults,
    ACTOR64_VALIDATION_PATH,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.actor_context_count import digest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from typing import Literal
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.processes.capture import retained_capture
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.releases.artifact_freeze import FileArtifactFreezer
from lab_generate_skill.domain.actor_step import ActorStepStarted, ActorStepClosed
from lab_generate_skill.domain.release import ReleaseArtifact
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


import pytest
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.actor.instructions import ACTIONS
from source_actor_callbacks import SourceActorCallbacks
from source_task_hooks import SourceTaskHooks
from reddit_source_selection import RedditSourceSelection
from gitlab_source_selection import GitlabSourceSelection
from map_navigation_source_selection import MapNavigationSourceSelection
from test_site_resource_installed import run_registered_site_case


def test_actual_admin_actor_business_chain(
    installed_sources: InstalledFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_actual_actor_business_chain(
        installed_sources, tmp_path, monkeypatch, site_id="shopping_admin"
    )


def run_actual_actor_business_chain(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    site_id: Literal["shopping_admin", "shopping", "gitlab", "reddit", "map"],
    reddit_selection: RedditSourceSelection | None = None,
    gitlab_selection: GitlabSourceSelection | None = None,
    map_selection: MapNavigationSourceSelection | None = None,
) -> None:
    if map_selection is not None and (
        site_id != "map" or not isinstance(map_selection, MapNavigationSourceSelection)
    ):
        raise ValueError("Selected Map navigation requires its original map entry")
    if reddit_selection is not None and (
        site_id != "reddit" or not isinstance(reddit_selection, RedditSourceSelection)
    ):
        raise ValueError("Explicit Reddit selection requires its original site entry")
    if gitlab_selection is not None and not isinstance(
        gitlab_selection, GitlabSourceSelection
    ):
        raise TypeError("Explicit validated GitLab selection required")
    if site_id == "gitlab":
        if gitlab_selection is None:
            raise ValueError(
                "GitLab Actor entry requires an explicit original selection"
            )
    elif gitlab_selection is not None:
        raise ValueError("Selected GitLab input requires its original site entry")
    receipt = Path(os.environ["LAB_ACTOR_SOFTWARE_RECEIPT"])
    source_root = Path(__file__).resolve().parents[2]
    verify_source(receipt, source_root=source_root)
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / {
            "shopping_admin": "admin-actor-native",
            "shopping": "shopping-actor-native",
            "gitlab": "gitlab-actor-native",
            "reddit": "reddit-actor-native",
            "map": "map-actor-native",
        }[site_id]
    )
    output.mkdir()
    c = resource_case(
        output / "resource",
        installed_sources.executable,
        installation=installed_sources,
    )
    # Choose the engineering operation budget before it is first bound. This
    # includes first-time immutable publication and local staging, not retries.
    c.op = c.op.model_copy(
        update={
            "deadline": datetime.now(timezone.utc)
            + timedelta(seconds=14400 if site_id == "map" else 3420)
        }
    )
    control = c.controls.bind(c.op)
    artifact, inventory_sha = pinned_causal_model(
        W, "models/Qwen2.5-7B-Instruct", "qwen25-original"
    )
    control.checkpoint()
    software = receipt.read_bytes()
    software_metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema="framework-check/3",
        visibility="private",
        producer="source-actor-software",
    )
    software_ref = evidence_reference(software, software_metadata)
    validation = (W / ACTOR64_VALIDATION_PATH).read_bytes()
    validation_metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema="actor-long-reconciled-acceptance/1",
        visibility="private",
        producer="source-actor-resource-qualification",
    )
    validation_ref = evidence_reference(validation, validation_metadata)
    config, params = accepted_actor_defaults(
        c.spec.engine_config,
        inventory_sha,
        validation_ref,
        validation,
        software_ref,
        software,
    )
    for raw, metadata, expected in [
        (software, software_metadata, software_ref),
        (validation, validation_metadata, validation_ref),
    ]:
        if c.evidence.put(raw, metadata, control=control) != expected:
            raise EvidenceIntegrityError(
                "Actor deployment evidence publication changed identity"
            )
    publication_root = W / "assets/frozen-actor-models-20261028-v1"
    publication_root.mkdir(exist_ok=True)
    artifact = FileArtifactFreezer(W, publication_root).freeze(
        artifact, "qwen25-7b-" + inventory_sha[:16], control
    )
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
        safe_to_remove = False
        callbacks = None
        facts = dict(
            engineering_only=True,
            site_id=site_id,
            formal_source_admission=False,
            paid_calls=0,
            software_receipt=str(receipt),
            model_inventory_sha256=inventory_sha,
            actor_resource_validation_ref=validation_ref.model_dump(mode="json"),
            actor_engine_config_sha256=digest(config),
            frozen_model=artifact.model_dump(mode="json"),
        )
        try:
            with registered_actor(c.spec, c.op, **c.dependencies()) as engine:
                # Validation loads the original model/tokenizer without inference.
                engine.validate(prepare_actor(saved_turn()), params, control)
                facts["warmup_generated_tokens"] = 0
                scope = ActorExecutionScope(
                    c.spec,
                    c.journal,
                    c.evidence,
                    engine,
                    c.op,
                    control,
                    cleanup_seconds=15,
                )
                facts["resource_binding"] = scope.binding.model_dump(mode="json")
                choice = (
                    MapRailsAddressableProjection()
                    if site_id == "map" and map_selection is None
                    else FullAxProjection()
                )
                context_policy = accepted_actor_context_policy(
                    software_ref, software, choice
                )
                facts["context_software_ref"] = software_ref.model_dump(mode="json")
                callbacks = SourceActorCallbacks(
                    c,
                    scope,
                    params,
                    output / "attempt",
                    context_policy=context_policy,
                    max_interactions=(
                        20
                        if gitlab_selection is not None and gitlab_selection.group
                        else 16
                    ),
                )
                if site_id == "map":
                    from map_actor_callbacks import MapActorCallbacks

                    callbacks = MapActorCallbacks(
                        c,
                        scope,
                        params,
                        output / "attempt",
                        context_policy=context_policy,
                        projection=choice,
                    )
                private_plan = None
                if site_id in ("gitlab", "reddit"):
                    from storage_installation_fixtures import storage_installation

                    sessions = output / "resource/site-private-sessions"
                    sessions.mkdir(mode=0o700)
                    storage = storage_installation(installed_sources)
                    if site_id == "reddit":
                        from reddit_site_native_plan import (
                            private_site_plan as reddit_private_plan,
                        )

                        private_plan = reddit_private_plan(
                            c.spec.token.owner,
                            storage,
                            evidence_root=output / "resource/evidence",
                            session_root=sessions,
                            journal_root=tmp_path / "journal",
                        )
                    else:
                        assert gitlab_selection is not None
                        from gitlab_site_native_plan import (
                            private_site_plan as gitlab_private_plan,
                        )

                        private_plan = gitlab_private_plan(
                            c.spec.token.owner,
                            storage,
                            evidence_root=output / "resource/evidence",
                            session_root=sessions,
                            journal_root=tmp_path / "journal",
                            selection=gitlab_selection,
                        )
                hooks = SourceTaskHooks(
                    c.spec.token.owner,
                    c.evidence,
                    tuple(ACTIONS),
                    callbacks.execute,
                    callbacks.evaluate,
                    private_site_plan=private_plan,
                    reddit_selection=reddit_selection,
                    gitlab_selection=gitlab_selection,
                    map_selection=map_selection,
                )
                if site_id == "map":
                    from map_source_live import run_source

                    facts["site_facts_path"] = str(tmp_path / "map-source-facts.json")
                    from map_source_inputs import engineering_scope

                    run_source(
                        installed_sources,
                        tmp_path,
                        monkeypatch,
                        hooks,
                        scope=engineering_scope(hooks.owner, hooks.map_selection),
                        evidence_root=output / "resource/evidence",
                    )
                else:
                    run_registered_site_case(
                        installed_sources,
                        tmp_path,
                        monkeypatch,
                        "actor_source",
                        task_hooks=hooks,
                        site_id=site_id,
                    )
                facts["actor"] = callbacks.facts
            cleanup = c.op.cleanup(
                "actor-native-inspect", now=datetime.now(timezone.utc), seconds=30
            )
            record = c.journal.read(c.spec.token, cleanup)
            facts["resource_record"] = record.model_dump(mode="json")
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
            facts["step_started"], facts["step_closed"] = started.model_dump(
                mode="json"
            ), closed.model_dump(mode="json")
            safe_to_remove = True
            assert callbacks is not None
            if callbacks.errors:
                raise BaseExceptionGroup(
                    "Task errors retained through confirmed recovery/closure",
                    callbacks.errors,
                )
            assert callbacks.facts["judgment"]["evaluation"]["status"] in (
                "success",
                "failure",
            )
            assert callbacks.facts["verified_model_returns"] > 0
        except BaseException as error:
            if callbacks is not None:
                facts["actor"] = callbacks.facts
            capture = engine.capture if engine is not None else retained_capture(error)
            if capture is not None:
                raise record_failure(output, "operation", error, capture)
            raise
        finally:
            (output / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")
    assert not staged.parent.exists()
    verify_source(receipt, source_root=source_root)
    facts["local_staging_removed_after_step_closure"] = True
    (output / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")
