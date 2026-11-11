"""Original producer→Actor inputs→RunPlan→claimed source; no resource/model effects."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_actor_configuration import (
    category_observation_projection,
    declare_category_actor_inputs,
    publish_category_actor_inputs,
    category_actor_metadata,
)
from lab_generate_skill.bootstrap.shopping_category_run_configuration import (
    freeze_category_execution_run,
)
from lab_generate_skill.bootstrap.shopping_category_execution_admission import (
    admit_shopping_category_execution_source,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.domain.evidence_identity import evidence_reference
from shopping_category_run_fixtures import run_input_case
from shopping_category_owned_reads import CategoryUnitRead
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals


def actor_inputs(c: Any) -> Any:
    return publish_category_actor_inputs(
        c.actor,
        c.binding,
        c.parameters,
        c.software_ref,
        c.software,
        c.store,
        c.operation,
        c.controls.bind(c.operation),
    )


def arguments(c: Any, inputs: Any) -> dict[str, Any]:
    return dict(
        source=c.published,
        scope=c.scope,
        actor=c.actor,
        parameters=c.parameters,
        actor_inputs=inputs,
        operation=c.operation,
        owner=c.source.owner,
        evidence=c.store,
        controls=c.controls,
        task_seconds=1200,
        cleanup_seconds=60,
    )


def test_actual_actor_run_freeze_and_claim_consume_same_complete_original_bindings(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    c = run_input_case(tmp_path, node_path, monkeypatch, originals[0])
    frozen = actor_inputs(c)
    assert len(frozen.context.profiles) == 20
    assert frozen.context.policy.schema_version == "context-projection-policy/2"
    assert (
        frozen.context.policy.actor_projection
        == frozen.policy.actor_projection
        == category_observation_projection()
    )
    assert frozen.context.policy.candidate_order == ("compact_full_ax", "local_ax")
    assert category_observation_projection().supports_local(c.scope.task)

    assert all(
        (p.context_window, p.output_reserve, p.input_limit) == (65536, 4096, 61440)
        for p in frozen.context.profiles
    )
    assert frozen.policy.max_generations == 20 and frozen.policy.max_interactions == 16
    args = arguments(c, frozen)
    planned = freeze_category_execution_run(**args)
    assert planned == freeze_category_execution_run(**args)
    assert (
        planned.run.purpose == "engineering"
        and planned.run.split == "train"
        and planned.run.budget is None
    )
    assert isinstance(planned.run.workload, ExecutionWorkload)
    assert planned.run.tasks == (c.published.inputs.baseline_inputs.binding,)
    assert planned.inputs.source_context_receipt_ref == c.published.material.context_ref
    assert planned.inputs.attempt_id != c.published.receipt.scope.attempt_id
    claim_root = tmp_path / "actual-claims"
    claim_root.mkdir()
    admitted = admit_shopping_category_execution_source(
        planned.run,
        planned.binding,
        c.published.material,
        c.source.owner.execution,
        c.source.owner.controller,
        c.operation,
        claim_root=claim_root,
        claim_scope="unit-category-real-run",
        evidence=c.store,
        controls=c.controls,
        source_reads=CategoryUnitRead(
            c.source, tmp_path / "source/evidence", c.operation
        ),
    )
    assert admitted.published.source.task == planned.task
    assert admitted.published.source.intent.binding.attempt_id == c.scope.attempt_id
    assert c.source.owner._sealed


@pytest.mark.parametrize("fault", ["output", "window", "route", "software"])
def test_actor_input_mismatches_refuse_before_publication(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = run_input_case(tmp_path, node_path, monkeypatch, originals[0])
    actor, parameters, software = c.actor, c.parameters, c.software
    if fault == "output":
        parameters = parameters.model_copy(update={"max_new_tokens": 1024})
    elif fault == "window":
        actor = actor.model_copy(
            update={
                "engine_config": actor.engine_config.model_copy(
                    update={"context_window": 32768}
                )
            }
        )
    elif fault == "route":
        actor = actor.model_copy(
            update={
                "model_binding_ref": actor.model_binding_ref.model_copy(
                    update={"sha256": "0" * 64}
                )
            }
        )
    else:
        software = b"{}"

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid Actor data reached CAS")

    monkeypatch.setattr(c.store, "put", forbidden)
    expected: type[Exception] = (
        ValueError if fault in ["output", "window"] else OwnershipConflict
    )
    if fault == "software":
        from lab_generate_skill.domain.errors import EvidenceIntegrityError

        expected = EvidenceIntegrityError
    with pytest.raises(expected):
        publish_category_actor_inputs(
            actor,
            c.binding,
            parameters,
            c.software_ref,
            software,
            c.store,
            c.operation,
            c.controls.bind(c.operation),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "source-attempt",
        "release",
        "binding-release",
        "profile",
        "limits",
        "store",
    ],
)
def test_run_mismatches_refuse_before_any_cas_write(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = run_input_case(tmp_path, node_path, monkeypatch, originals[0])
    frozen = actor_inputs(c)
    args = arguments(c, frozen)
    if fault == "owner":
        args["scope"] = c.scope.model_copy(
            update={"owner": c.scope.owner.model_copy(update={"worker_id": "foreign"})}
        )
    elif fault == "source-attempt":
        args["scope"] = c.source.owner.scope
    elif fault == "release":
        args["actor"] = c.actor.model_copy(
            update={
                "release_ref": c.actor.release_ref.model_copy(
                    update={"sha256": "0" * 64}
                )
            }
        )
    elif fault == "binding-release":
        binding = c.binding.model_copy(
            update={
                "release_ref": c.binding.release_ref.model_copy(
                    update={"sha256": "0" * 64}
                )
            }
        )
        routing = evidence_reference(
            binding.model_dump_json().encode(),
            category_actor_metadata("model-binding/1"),
        )
        args["actor"] = c.actor.model_copy(update={"model_binding_ref": routing})
        args["actor_inputs"] = declare_category_actor_inputs(
            c.actor.artifact,
            c.actor.engine_config,
            binding,
            routing,
            c.parameters,
            c.software_ref,
            c.software,
        )
    elif fault == "profile":
        args["actor_inputs"] = replace(
            frozen,
            context=frozen.context.model_copy(
                update={"profiles": frozen.context.profiles[:1]}
            ),
        )
    elif fault == "limits":
        args["task_seconds"] = True
    elif fault == "store":
        args["evidence"] = object()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid run reached CAS")

    monkeypatch.setattr(c.store, "put", forbidden)
    with pytest.raises(ValueError if fault == "limits" else OwnershipConflict):
        freeze_category_execution_run(**args)


@pytest.mark.parametrize("phase", ["actor", "run"])
def test_partial_actor_or_run_publication_retains_first_error_and_exact_candidates(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    phase: str,
) -> None:
    c = run_input_case(tmp_path, node_path, monkeypatch, originals[0])
    frozen = declare_category_actor_inputs(
        c.actor.artifact,
        c.actor.engine_config,
        c.binding,
        c.actor.model_binding_ref,
        c.parameters,
        c.software_ref,
        c.software,
    )
    if phase == "run":
        actor_inputs(c)
    put = c.store.put
    calls: list[Any] = []

    def lost(*args: Any, **kwargs: Any) -> Any:
        value = put(*args, **kwargs)
        calls.append(value)
        if len(calls) == 2:
            raise OSError("Category input acknowledgement lost")
        return value

    monkeypatch.setattr(c.store, "put", lost)
    with pytest.raises(OSError, match="acknowledgement lost") as caught:
        if phase == "actor":
            actor_inputs(c)
        else:
            freeze_category_execution_run(**arguments(c, frozen))
    key = "category_actor_input" if phase == "actor" else "category_run"
    assert tuple(calls[:1]) == getattr(caught.value, key + "_known_references")
    assert calls[1] in getattr(caught.value, key + "_candidates")
    assert len(calls) == 2


@pytest.mark.parametrize("changed", ["root", "files"])
def test_node_staging_changes_only_location_and_never_model_file_pins(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    changed: str,
) -> None:
    c = run_input_case(tmp_path, node_path, monkeypatch, originals[0])
    artifact = c.actor.artifact.model_copy(
        update={"root": str(node_path / "staged-model")}
    )
    if changed == "files":
        first = artifact.files[0].model_copy(update={"sha256": "0" * 64})
        artifact = artifact.model_copy(update={"files": (first, *artifact.files[1:])})
    c.actor = c.actor.model_copy(update={"artifact": artifact})
    args = arguments(c, actor_inputs(c))
    if changed == "root":
        planned = freeze_category_execution_run(**args)
        assert (
            planned.run.resources.configuration_ref.content_schema
            == "actor-resource-spec/1"
        )
    else:
        with pytest.raises(OwnershipConflict):
            freeze_category_execution_run(**args)
