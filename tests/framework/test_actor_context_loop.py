"""Full original loop/intent/native frames/closed review; synthetic engines only."""

from dataclasses import replace
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.actor_loop import (
    ActorLoopFailure,
    RecordedActorRunner,
)
from lab_generate_skill.application.actor_model_admission import TraceActorAuthority
from lab_generate_skill.application.actor_context_preparation import (
    ActorContextRejected,
)
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.adapters.models.context_count_review import (
    ActorContextCountReviewer,
)
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.actor_generation import ActorGeneration
from lab_generate_skill.domain.trace_events import GenerationIntent, GenerationPlanned
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.local_actor import LocalActorCall
from actor_context_loop_fixtures import context_loop_case
from map_actor_view_fixtures import ROOT
from source_actor_review import review_actor
from source_review_records import ReadOnlyEvidence
from test_run_journal import command


def test_legacy_map_request_keeps_exact_canonical_bytes_and_rejects_v2_null_fields() -> (
    None
):
    raw = (ROOT / "map-actor-budget-request.json").read_bytes()
    old = ActorRunRequest.model_validate_json(raw)
    assert old.model_dump_json().encode() == raw
    assert ActorRunRequest.model_validate(old) == old
    for field in ("candidate_id", "revision_round", "context_configuration_ref"):
        with pytest.raises(ValidationError):
            ActorRunRequest.model_validate({**old.model_dump(), field: None})


def test_original_loop_uses_same_prepared_bytes_intent_actual_generation_and_closed_review(
    tmp_path: Path,
) -> None:
    c = context_loop_case(tmp_path)
    c.base.loader.session.output = c.base.loader.session.output.model_copy(
        update={"text": '{"action":"send_msg_to_user(\'Done\')"}'}
    )
    result = c.runner.run(c.request)
    trace = result.project().sealed
    assert (
        trace is not None
        and trace.stop_reason == "finished"
        and trace.generations == trace.interactions == 1
    )
    assert c.base.loader.session.calls == 1 and len(c.executions) == 1
    intent = next(e.intent for e in result.events if isinstance(e, GenerationPlanned))
    assert (
        intent.schema_version == "actor-generation-intent/2"
        and intent.context_preparation_ref is not None
    )
    assert (
        trace.turns[0].generation.schema_version == "actor-generation/2"
        and trace.turns[0].generation.context_preparation_ref
        == intent.context_preparation_ref
    )
    receipt = ContextPreparationReceipt.model_validate_json(
        c.base.loop.store.read(intent.context_preparation_ref)
    )
    assert isinstance(receipt.request.source, ActorContextSource)
    assert (
        receipt.decision is not None
        and receipt.decision.selected_input_ref == intent.input_ref
    )
    assert (
        receipt.request.request_id == intent.request_id
        and receipt.request.source.candidate_id == c.request.candidate_id
    )
    assert receipt.request.source.revision_round == c.request.revision_round == 0
    guard, sources = c.base.client.owner_guard, c.base.client.installed_sources
    assert guard is not None and sources is not None
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-context-worker", attempt="attempt")
        )
    )
    sent = len(c.base.channel.sent)
    readonly = ReadOnlyEvidence(tmp_path / "evidence")
    counts = ActorContextCountReviewer(
        readonly,
        c.config.profiles[0],
        c.model_binding,
        c.params,
        c.base.client.artifact,
        c.base.client.config,
        session_id=c.base.client.session_id,
        guard=guard,
        installed_sources=sources,
    )
    project, protect = build_actor_context(c.config.policy)
    inputs = RecordedActorContextInputs(
        readonly,
        EvidenceObservations(readonly, c.base.loop.journal.controls),
        project,
        protect,
        counts,
    )
    op = command(
        "closed-context-review",
        attempt="attempt",
        cleanup_parent="original-context-run",
    )
    summary = review_actor(
        c.request,
        result,
        tuple(c.executions),
        readonly,
        c.base.loop.journal.controls,
        op,
        project=c.base.loop.runner.deps.project,
        context=inputs,
    )
    assert summary == dict(generations=1, interactions=1, stop_reason="finished")
    assert (
        len(c.base.channel.sent) == sent
        and c.base.loader.loads == c.base.loader.session.closed == 1
    )
    with pytest.raises(ActorLoopFailure):
        c.runner.run(c.request)
    assert c.base.loader.session.calls == 1


def test_context_budget_refusal_saves_receipt_without_model_intent_or_effective_failure(
    tmp_path: Path,
) -> None:
    c = context_loop_case(tmp_path, input_limit=1)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert isinstance(caught.value.primary, ActorContextRejected)
    prepared = caught.value.primary.prepared
    assert prepared.outcome == "budget_rejected" and prepared.selected_input_ref is None
    snapshot = caught.value.snapshot
    assert snapshot is not None and not any(
        isinstance(e, GenerationPlanned) for e in snapshot.events
    )
    assert c.base.loader.session.calls == c.base.loop.browser.calls == 0
    assert not any(
        decode_worker_command(raw).operation == "generate"
        for raw in c.base.channel.sent
    )
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-refused-context", attempt="attempt")
        )
    )


def test_v2_missing_context_dependency_never_loads_or_dispatches(
    tmp_path: Path,
) -> None:
    c = context_loop_case(tmp_path)
    runner = RecordedActorRunner(replace(c.runner.deps, context=None))
    with pytest.raises(ActorLoopFailure) as caught:
        runner.run(c.request)
    assert (
        isinstance(caught.value.primary, OwnershipConflict)
        and c.base.loader.loads == c.base.loader.session.calls == 0
    )
    with pytest.raises(ValueError):
        TraceActorAuthority(
            c.request,
            c.base.loop.journal,
            c.base.loop.store,
            c.base.loop.runner.deps.observations,
            c.base.loop.runner.deps.project,
            c.base.loop.authority,
            c.base.loop.journal.controls,
        )
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-missing-context", attempt="attempt")
        )
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_id", None),
        ("revision_round", None),
        ("revision_round", True),
        ("revision_round", 4),
        ("context_configuration_ref", None),
        ("schema_version", "actor-run-request/3"),
    ],
)
def test_v2_requires_exact_candidate_round_and_context_config(
    tmp_path: Path, field: str, value: object
) -> None:
    c = context_loop_case(tmp_path)
    with pytest.raises(ValidationError):
        ActorRunRequest.model_validate({**c.request.model_dump(), field: value})
    assert c.base.loader.loads == 0
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-invalid-context", attempt="attempt")
        )
    )


def test_same_original_request_key_cannot_be_renewed_by_context_format_or_version(
    tmp_path: Path,
) -> None:
    c = context_loop_case(tmp_path)
    old = c.base.intent
    reference = c.request.context_configuration_ref
    assert reference is not None
    # Key does not include preparation/format/version; this is not admission.
    from retrieval_fixtures import reference as ref

    fake = ref({}, "context-preparation/2", store=c.base.loop.store)
    new = GenerationIntent.model_validate(
        {
            **old.model_dump(),
            "schema_version": "actor-generation-intent/2",
            "context_preparation_ref": fake,
        }
    )
    assert (
        LocalActorCall(binding=c.base.binding, intent=old).key
        == LocalActorCall(binding=c.base.binding, intent=new).key
    )
    with pytest.raises(ValidationError):
        GenerationIntent.model_validate(
            {**new.model_dump(), "context_preparation_ref": None}
        )
    with pytest.raises(ValidationError):
        ActorGeneration.model_validate(
            {
                **new.model_dump(exclude={"schema_version"}),
                "schema_version": "actor-generation/2",
                "status": "uncertain",
                "failure_ref": ref({}, "generation-failure/1", store=c.base.loop.store),
                "context_preparation_ref": None,
            }
        )
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-key-context", attempt="attempt")
        )
    )


def test_lost_native_generation_return_preserves_original_context_and_pending_intent_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.ports.lifecycle import OperationControl

    c = context_loop_case(tmp_path)
    original = c.base.channel.exchange

    def exchange(payload: bytes, control: OperationControl) -> bytes:
        raw = original(payload, control)
        if decode_worker_command(payload).operation == "generate":
            raise OSError("original generation return lost")
        return raw

    monkeypatch.setattr(c.base.channel, "exchange", exchange)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    before = caught.value.snapshot
    assert (
        before is not None
        and before.project().intent is not None
        and before.project().sealed is None
    )
    pending = before.project().intent
    assert pending is not None and pending.context_preparation_ref is not None
    prepared = ContextPreparationReceipt.model_validate_json(
        c.base.loop.store.read(pending.context_preparation_ref)
    )
    assert (
        prepared.decision is not None
        and prepared.decision.selected_input_ref == pending.input_ref
    )
    calls = len(c.base.channel.sent)
    with pytest.raises(ActorLoopFailure):
        c.runner.run(c.request)
    assert (
        c.base.loader.session.calls == 1
        and c.base.loop.browser.calls == 0
        and len(c.base.channel.sent) == calls
    )
    assert (
        sum(
            decode_worker_command(raw).operation == "generate"
            for raw in c.base.channel.sent
        )
        == 1
    )


def test_original_public_source_commit_uncertain_never_counts_or_creates_model_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
    from lab_generate_skill.ports.lifecycle import OperationControl

    c = context_loop_case(tmp_path)
    original = c.base.loop.store.put

    def put(
        raw: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        result = original(raw, metadata, control, exchange_id=exchange_id)
        if metadata.producer == "actor-context-input-v1":
            raise OSError("public source write acknowledgement lost")
        return result

    monkeypatch.setattr(c.base.loop.store, "put", put)
    with pytest.raises(ActorLoopFailure) as caught:
        c.runner.run(c.request)
    assert getattr(caught.value.primary, "actor_context_source_candidates")
    assert (
        c.base.loader.loads
        == c.base.loader.session.calls
        == c.base.loop.browser.calls
        == 0
    )
    assert caught.value.snapshot is not None and not any(
        isinstance(e, GenerationPlanned) for e in caught.value.snapshot.events
    )
    c.base.client.close(
        c.base.loop.journal.controls.bind(
            command("close-source-uncertain", attempt="attempt")
        )
    )
