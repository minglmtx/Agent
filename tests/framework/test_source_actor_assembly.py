"""Real CAS with synthetic source/resource gates; no native effects or admission."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json
import pytest
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from source_actor_plan import plan_source_actor
from source_actor_authority import SourceActorAuthority
from state_storage_fixtures import fixture
from state_contract_fixtures import allocation
from test_run_journal import command


class UnitSpec(Contract):
    schema_version: str = "engineering-unit-spec/1"
    token: AllocationToken
    release_ref: EvidenceRef
    model_binding_ref: EvidenceRef


def setup(root: Path) -> tuple[Any, Any, Any, Any, Any, Any]:
    state = fixture(root)

    def raw(data: bytes, schema: str) -> EvidenceRef:
        return state.store.put(
            data,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="engineering-unit",
            ),
        )

    def put(model: Contract) -> EvidenceRef:
        return raw(
            model.model_dump_json().encode(), str(model.model_dump()["schema_version"])
        )

    native: Any = SimpleNamespace(
        public=state.baseline_inputs.public_task,
        binding=state.baseline_inputs.binding,
        binding_ref=state.baseline_inputs.prepared.task_binding_ref,
        request=SimpleNamespace(operation=state.baseline_inputs.preparation.operation),
        put=put,
        raw=raw,
        native_contract_ref=raw(b"{}", "engineering-native/1"),
    )
    saved = dict(
        baseline=state.baseline,
        baseline_inputs=state.baseline_inputs,
        baseline_ref=put(state.baseline),
    )
    journal: Any = SimpleNamespace(state="acquired")
    journal.read = lambda *args: SimpleNamespace(state=journal.state)
    actor_token = allocation("actor", attempt=False).model_copy(
        update={"provider_id": "fixed-actor-worker"}
    )
    spec = UnitSpec(
        token=actor_token,
        release_ref=raw(b"{}", "release-manifest/1"),
        model_binding_ref=raw(b"{}", "model-binding/1"),
    )
    actor: Any = SimpleNamespace(
        spec=spec,
        op=command("unit-actor-start"),
        evidence=state.store,
        controls=state.adapter.controls,
    )
    browser: Any = SimpleNamespace(
        spec=SimpleNamespace(token=allocation("browser")),
        op=command("unit-browser-start", attempt="attempt"),
        journal=journal,
    )
    site: Any = SimpleNamespace(
        spec=SimpleNamespace(token=allocation("site", attempt=False)),
        op=command("unit-site-start"),
        journal=journal,
        evidence=state.store,
    )
    source: Any = SimpleNamespace(native=native, saved=saved, c=site)
    params = LocalActorParameters(
        max_input_tokens=28672,
        max_new_tokens=4096,
        seed=42,
        temperature=0.7,
        top_p=0.95,
    )
    return source, browser, actor, params, state, journal


@pytest.mark.parametrize("change", ["none", "owner", "observation", "baseline"])
def test_original_plan_freezes_caps_only_actor_and_original_inputs(
    tmp_path: Path, change: str
) -> None:
    source, browser, actor, params, state, _ = setup(tmp_path)
    initial = state.baseline_inputs.observation_ref
    if change == "owner":
        actor.spec = actor.spec.model_copy(
            update={
                "token": actor.spec.token.model_copy(
                    update={
                        "owner": actor.spec.token.owner.model_copy(
                            update={"owner_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif change == "observation":
        initial = initial.model_copy(update={"sha256": "f" * 64})
    elif change == "baseline":
        source.saved["baseline"] = state.baseline.model_copy(
            update={"status": "unknown"}
        )
    if change != "none":
        with pytest.raises(AssertionError):
            plan_source_actor(source, browser, actor, initial, params)
        return
    plan = plan_source_actor(source, browser, actor, initial, params)
    assert plan.run.purpose == "engineering" and plan.run.budget is None
    assert (
        tuple(m.role for m in plan.run.models) == ("actor",)
        and not plan.run.models[0].paid
    )
    assert (
        plan.request.initial_observation_ref == initial
        and plan.request.scope == state.baseline.scope
    )
    assert (
        len(plan.request.parameters_refs) == plan.trace.max_generations == 20
        and plan.trace.max_interactions == 16
    )
    assert (
        plan.request.generation_seconds == 120
        and plan.request.interaction_seconds == 30
    )
    assert (
        json.loads(state.store.read(plan.run.split_manifest_ref))[
            "formal_source_admission"
        ]
        is False
    )


@pytest.mark.parametrize(
    "change", ["none", "closed", "task", "baseline", "observation", "browser_state"]
)
def test_live_gate_requires_original_ready_baseline_and_both_acquired_resources(
    tmp_path: Path, change: str
) -> None:
    source, browser, actor, params, state, journal = setup(tmp_path)
    initial = state.baseline_inputs.observation_ref
    plan = plan_source_actor(source, browser, actor, initial, params)
    snapshot = TraceSnapshot(
        plan=plan.trace, creation_operation=plan.request.operation, events=()
    )
    session: Any = SimpleNamespace(
        observation_ref=initial, engine=SimpleNamespace(state="ready")
    )
    request = plan.request
    if change == "closed":
        journal.state = "closed"
    elif change == "task":
        request = request.model_copy(
            update={"task": request.task.model_copy(update={"goal": "changed"})}
        )
    elif change == "baseline":
        source.saved["baseline"] = state.baseline.model_copy(
            update={"status": "unknown"}
        )
    elif change == "observation":
        session.observation_ref = None
    elif change == "browser_state":
        session.engine.state = "broken"
    gate = SourceActorAuthority(source, browser, session, plan)
    if change == "none":
        gate.verify(request, snapshot, actor.controls.bind(request.operation))
    else:
        with pytest.raises(OwnershipConflict):
            gate.verify(request, snapshot, actor.controls.bind(request.operation))
