"""Default source entry and closed bootstrap; explicit synthetic resource gates."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.bootstrap.actor_context_runtime import (
    freeze_actor_context,
    live_actor_context,
)
from lab_generate_skill.bootstrap.actor_context_review import closed_actor_context
from lab_generate_skill.bootstrap.actor_context_policy import (
    accepted_actor_context_policy,
    ACTOR_CONTEXT_IMPLEMENTATION_FILES,
)
from lab_generate_skill.adapters.models.actor_context_counters import (
    ActorContextCounters,
    ActorContextCountReviews,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.models.actor_context_records import (
    actor_context_document,
)
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    MapRailsDiagnosticProjection,
    MapRailsAddressableProjection,
)
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.source_actor_policy import EngineeringActorPolicy
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.run_plan import ExecutionWorkload
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from source_actor_plan import plan_source_actor
from source_actor_projection import original_source_projection, read_source_projection
from source_actor_execution import execute_source_actor
from source_actor_review import review_actor
from source_review_records import ReadOnlyEvidence
from source_actor_context_fixtures import source_context_case
from test_run_journal import command


def test_default_source_execution_binds_same_count_send_policy_and_closed_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    result, failure = execute_source_actor(
        c.source,
        c.browser,
        c.session,
        c.actor,
        c.scope,
        c.params,
        tmp_path / "attempt",
        context_policy=c.policy,
    )
    if failure is not None:
        (tmp_path / "source-assembly-failure.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        raise failure
    assert result["runtime_error"] is None
    assert (
        result["generations"]
        == result["interactions"]
        == result["verified_model_returns"]
        == 1
    )
    assert c.loader.session.calls == c.session.calls == 1
    store = c.actor.evidence
    request = ActorRunRequest.model_validate_json(
        store.read(EvidenceRef.model_validate(result["planned_actor_request_ref"]))
    )
    snapshot = TraceSnapshot.model_validate_json(
        store.read(EvidenceRef.model_validate(result["trace_snapshot_ref"]))
    )
    executions = tuple(
        LocalActorExecution.model_validate_json(
            store.read(EvidenceRef.model_validate(x))
        )
        for x in result["executions"]
    )
    assert request.schema_version == "actor-run-request/2"
    assert all(x.call.intent.context_preparation_ref is not None for x in executions)
    assert c.resource_calls == [True, True, True, True, True, True, False]
    op = command("close-source-context", attempt=request.scope.attempt_id)
    c.client.close(c.actor.controls.bind(op))
    sent = len(c.channel.sent)
    readonly = ReadOnlyEvidence(tmp_path / "case")
    control = c.actor.controls.bind(op)
    project = original_source_projection(request, snapshot.plan, readonly, control)
    assert project == FullAxProjection()
    inputs = closed_actor_context(
        request,
        executions,
        readonly,
        EvidenceObservations(readonly, c.actor.controls),
        control=control,
    )
    from lab_generate_skill.bootstrap.actor_projection import build_actor_projection

    summary = review_actor(
        request,
        snapshot,
        executions,
        readonly,
        c.actor.controls,
        op,
        project=build_actor_projection(project),
        context=inputs,
    )
    assert summary["generations"] == 1 and len(c.channel.sent) == sent
    assert c.loader.session.calls == 1 and c.loader.session.closed == 1


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "candidate",
        "round",
        "context",
        "skill",
        "limits",
        "unknown",
        "noncanonical",
        "old_policy",
    ],
)
def test_policy3_exact_original_binding_and_historical_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    plan = plan_source_actor(
        c.source,
        c.browser,
        c.actor,
        c.session.observation_ref,
        c.params,
        context_policy=c.policy,
    )
    assert isinstance(plan.run.workload, ExecutionWorkload)
    ref = plan.run.workload.execution_policy_ref
    raw = c.actor.evidence.read(ref)
    assert ref.content_schema == "engineering-execution-policy/3"
    value = json.loads(raw)
    if change == "candidate":
        value["candidate_id"] = "foreign"
    elif change == "round":
        value["revision_round"] = 1
    elif change == "context":
        value["actor_context_ref"]["sha256"] = "a" * 64
    elif change == "skill":
        value["skill"]["description"] = "changed"
    elif change == "limits":
        value["max_interactions"] = 1
    elif change == "unknown":
        value["ignored"] = True
    if change not in ("none", "old_policy"):
        payload = (
            json.dumps(value, indent=2)
            if change == "noncanonical"
            else json.dumps(value, separators=(",", ":"))
        ).encode()
        ref = c.source.native.raw(payload, "engineering-execution-policy/3")
    if change == "old_policy":
        ref = c.source.native.raw(
            json.dumps(
                {
                    k: value[k]
                    for k in (
                        "engineering_only",
                        "skill",
                        "memory",
                        "max_generations",
                        "max_interactions",
                    )
                }
            ).encode(),
            "engineering-execution-policy/1",
        )
    control = c.actor.controls.bind(plan.request.operation)
    if change == "none":
        assert (
            original_source_projection(
                plan.request, plan.trace, c.actor.evidence, control
            )
            == FullAxProjection()
        )
        policy = EngineeringActorPolicy.model_validate_json(raw)
        assert (
            policy.candidate_id == plan.request.candidate_id
            and policy.actor_context_ref == plan.request.context_configuration_ref
        )
        config = actor_context_document(
            c.actor.evidence,
            policy.actor_context_ref,
            "actor-context-configuration/1",
            ActorContextConfiguration,
            16 * 1024**2,
            control,
        )
        assert len(config.profiles) == 20 and all(
            (p.input_limit, p.output_reserve, p.context_window, p.soft_target)
            == (28672, 4096, 32768, 24576)
            for p in config.profiles
        )
    else:
        with pytest.raises((EvidenceIntegrityError, ValidationError)):
            read_source_projection(
                ref, plan.request, plan.trace, c.actor.evidence, control
            )
    c.client.close(control)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("engineering_only", 1),
        ("revision_round", True),
        ("revision_round", 4),
        ("candidate_id", ""),
        ("max_generations", None),
        ("max_interactions", "16"),
        ("actor_context_ref", {}),
        ("ignored", False),
    ],
)
def test_policy3_strict_wrong_types_empty_extreme_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, bad: Any
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    plan = plan_source_actor(
        c.source,
        c.browser,
        c.actor,
        c.session.observation_ref,
        c.params,
        context_policy=c.policy,
    )
    assert isinstance(plan.run.workload, ExecutionWorkload)
    value = json.loads(c.actor.evidence.read(plan.run.workload.execution_policy_ref))
    value[field] = bad
    with pytest.raises(ValidationError):
        EngineeringActorPolicy.model_validate_json(json.dumps(value))
    c.client.close(c.actor.controls.bind(plan.request.operation))


@pytest.mark.parametrize(
    "change", ["route", "release", "installation", "controller", "window", "profile"]
)
def test_live_assembly_refuses_changed_original_pins_before_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    plan = plan_source_actor(
        c.source,
        c.browser,
        c.actor,
        c.session.observation_ref,
        c.params,
        context_policy=c.policy,
    )
    spec = c.actor.spec
    if change == "route":
        spec = spec.model_copy(
            update={
                "model_binding_ref": spec.model_binding_ref.model_copy(
                    update={"sha256": "e" * 64}
                )
            }
        )
    elif change == "release":
        spec = spec.model_copy(
            update={
                "release_ref": spec.release_ref.model_copy(update={"sha256": "e" * 64})
            }
        )
    elif change == "installation":
        spec = spec.model_copy(update={"python_executable": "/other/python"})
    elif change == "controller":
        spec = spec.model_copy(
            update={
                "slurm": spec.slurm.model_copy(
                    update={
                        "allocation": spec.slurm.allocation.model_copy(
                            update={
                                "facts": spec.slurm.allocation.facts.model_copy(
                                    update={
                                        "writer": spec.slurm.allocation.facts.writer.model_copy(
                                            update={"start_ticks": 999}
                                        ),
                                        "cgroup": spec.slurm.allocation.facts.cgroup.model_copy(
                                            update={
                                                "writer": spec.slurm.allocation.facts.writer.model_copy(
                                                    update={"start_ticks": 999}
                                                )
                                            }
                                        ),
                                    }
                                )
                            }
                        )
                    }
                )
            }
        )
    elif change == "window":
        spec = spec.model_copy(
            update={
                "engine_config": spec.engine_config.model_copy(
                    update={"context_window": 32767}
                )
            }
        )
    else:
        ref = plan.request.context_configuration_ref
        assert ref is not None
        config = ActorContextConfiguration.model_validate_json(
            c.actor.evidence.read(ref)
        )
        profile = config.profiles[0].model_copy(update={"model": "foreign"})
        config = config.model_copy(update={"profiles": (profile,) * 20})
        plan = plan.__class__(
            plan.run,
            plan.trace,
            plan.request.model_copy(
                update={"context_configuration_ref": c.source.native.put(config)}
            ),
            plan.projection,
        )
    sent = len(c.channel.sent)
    with pytest.raises((OwnershipConflict, ValueError)):
        live_actor_context(
            plan.request,
            spec,
            c.client,
            c.journal,
            c.actor.evidence,
            EvidenceObservations(c.actor.evidence, c.actor.controls),
            c.journal,
            c.actor.controls,
            control=c.actor.controls.bind(plan.request.operation),
        )
    assert len(c.channel.sent) == sent and c.loader.session.calls == 0
    c.client.close(c.actor.controls.bind(plan.request.operation))


@pytest.mark.parametrize("outcome", ["over_limit", "unknown_count"])
def test_default_context_failure_retains_evidence_and_never_dispatches_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    if outcome == "over_limit":
        c.loader.session.tokens = tuple(range(28673))
    else:
        c.channel.broken_reply = b"unknown original response"
    result, failure = execute_source_actor(
        c.source,
        c.browser,
        c.session,
        c.actor,
        c.scope,
        c.params,
        tmp_path / "attempt",
        context_policy=c.policy,
    )
    assert (
        failure is not None
        and result["verified_model_returns"]
        == c.loader.session.calls
        == c.session.calls
        == 0
    )
    operations = [decode_worker_command(x).operation for x in c.channel.sent]
    assert "generate" not in operations and operations.count("measure") == 1
    snapshot = TraceSnapshot.model_validate_json(
        c.actor.evidence.read(EvidenceRef.model_validate(result["trace_snapshot_ref"]))
    )
    assert not any(e.kind == "generation_planned" for e in snapshot.events)
    if outcome == "over_limit":
        rejection = result["context_rejection"]
        receipt = ContextPreparationReceipt.model_validate_json(
            c.actor.evidence.read(EvidenceRef.model_validate(rejection["reference"]))
        )
        assert (
            receipt.outcome == "budget_rejected"
            and receipt.decision is not None
            and receipt.decision.selected_input_ref is None
        )
        c.client.close(c.actor.controls.bind(command("close-refused")))
    else:
        assert c.channel.aborts == 1
        assert "context_rejection" not in result


def test_software_receipt_freezes_exact_common_policy_and_finite_candidate_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    value: dict[str, Any] = dict(
        schema_version="framework-check/3",
        passed=True,
        source_stable_during_checks=True,
        files={name: "a" * 64 for name in ACTOR_CONTEXT_IMPLEMENTATION_FILES},
    )
    for projection in (
        FullAxProjection(),
        MapRailsDiagnosticProjection(),
        MapRailsAddressableProjection(),
    ):
        raw = json.dumps(value).encode()
        ref = c.source.native.raw(raw, "framework-check/3")
        policy = accepted_actor_context_policy(ref, raw, projection)
        assert policy.candidate_order == (
            ("identity",)
            if isinstance(projection, FullAxProjection)
            else ("identity", "structural_ax")
        )
        assert (
            policy.role == "actor"
            and policy.software_evidence_ref == ref
            and policy.allow_identity_fallback
        )
    for field, bad in [
        ("passed", False),
        ("source_stable_during_checks", 1),
        ("schema_version", "framework-check/2"),
        ("files", {}),
        ("files", None),
    ]:
        raw = json.dumps({**value, field: bad}).encode()
        with pytest.raises((EvidenceIntegrityError, ValueError)):
            accepted_actor_context_policy(
                c.source.native.raw(raw, "framework-check/3"), raw, FullAxProjection()
            )
    with pytest.raises(EvidenceIntegrityError):
        accepted_actor_context_policy(ref, raw + b" ", FullAxProjection())
    with pytest.raises(ValueError):
        ActorContextCounters({})
    with pytest.raises(ValueError):
        ActorContextCountReviews({})
    c.client.close(c.actor.controls.bind(command("close-policy-test")))


def test_closed_factory_rejects_tampered_original_acquisition_without_worker_recount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch)
    result, failure = execute_source_actor(
        c.source,
        c.browser,
        c.session,
        c.actor,
        c.scope,
        c.params,
        tmp_path / "attempt",
        context_policy=c.policy,
    )
    if failure is not None:
        raise failure
    store = c.actor.evidence
    request = ActorRunRequest.model_validate_json(
        store.read(EvidenceRef.model_validate(result["planned_actor_request_ref"]))
    )
    original = LocalActorExecution.model_validate_json(
        store.read(EvidenceRef.model_validate(result["executions"][0]))
    )
    control = c.actor.controls.bind(
        command("closed-origin-check", attempt=request.scope.attempt_id)
    )
    c.client.close(control)
    sent = len(c.channel.sent)
    binding = original.call.binding
    acquired = json.loads(store.read(binding.acquired_ref))
    for change in (
        "worker",
        "operation",
        "step",
        "installation",
        "token",
        "spec",
        "unknown",
    ):
        changed = json.loads(json.dumps(acquired))
        if change == "worker":
            changed["worker"]["start_ticks"] += 1
        elif change == "operation":
            changed["operation"]["owner_id"] = "foreign"
        elif change == "step":
            changed["step"]["controller"]["target"]["step_name"] = "foreign"
        elif change == "installation":
            changed["installed_sources"]["executable"] = "/foreign/python"
        elif change == "token":
            changed["token"]["expected_resource_id"] = "foreign"
        elif change == "spec":
            changed["spec_sha256"] = "e" * 64
        else:
            changed["ignored"] = None
        ref = c.source.native.raw(json.dumps(changed).encode(), "actor-resource-fact/1")
        altered = original.model_copy(
            update={
                "call": original.call.model_copy(
                    update={"binding": binding.model_copy(update={"acquired_ref": ref})}
                )
            }
        )
        with pytest.raises(
            (EvidenceIntegrityError, OwnershipConflict, ValidationError)
        ):
            closed_actor_context(
                request,
                (altered,),
                store,
                EvidenceObservations(store, c.actor.controls),
                control=control,
            )
    with pytest.raises(EvidenceIntegrityError):
        closed_actor_context(
            request,
            (),
            store,
            EvidenceObservations(store, c.actor.controls),
            control=control,
        )
    assert len(c.channel.sent) == sent and c.loader.session.calls == 1


def test_profile_freeze_repeat_and_counter_registry_cancellation_unknown_profile_have_no_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.errors import OperationStopped
    from lab_generate_skill.ports.lifecycle import OperationControl

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-context-test")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    c = source_context_case(tmp_path / "case", monkeypatch)
    plan = plan_source_actor(
        c.source,
        c.browser,
        c.actor,
        c.session.observation_ref,
        c.params,
        context_policy=c.policy,
    )
    control = c.actor.controls.bind(plan.request.operation)
    one = freeze_actor_context(
        c.actor.spec,
        plan.request.parameters_refs,
        c.policy,
        c.actor.evidence,
        soft_target=24576,
        control=control,
    )
    two = freeze_actor_context(
        c.actor.spec,
        plan.request.parameters_refs,
        c.policy,
        c.actor.evidence,
        soft_target=24576,
        control=control,
    )
    assert one == two
    preparation, _ = live_actor_context(
        plan.request,
        c.actor.spec,
        c.client,
        c.journal,
        c.actor.evidence,
        EvidenceObservations(c.actor.evidence, c.actor.controls),
        c.journal,
        c.actor.controls,
        control=control,
    )
    sent = len(c.channel.sent)
    reference = c.source.native.raw(b"{}", "actor-model-input/1")
    stopped: OperationControl = Stopped()
    with pytest.raises(OperationStopped):
        preparation.counter.measure(
            reference, one.profiles[0], c.policy, control=stopped
        )
    with pytest.raises(OperationStopped):
        freeze_actor_context(
            c.actor.spec,
            plan.request.parameters_refs,
            c.policy,
            c.actor.evidence,
            soft_target=24576,
            control=stopped,
        )
    with pytest.raises(OwnershipConflict):
        preparation.counter.measure(
            reference,
            one.profiles[0].model_copy(update={"model": "unknown"}),
            c.policy,
            control=control,
        )
    assert len(c.channel.sent) == sent and c.loader.session.calls == 0
    c.client.close(control)
