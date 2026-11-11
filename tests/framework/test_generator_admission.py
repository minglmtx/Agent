"""Construction → actual input verification → durable inference → role parsing.

All model/environment/live permission facts are explicitly synthetic. Tests
prove the data/state seam, not a production release or real Slurm permission.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.domain.construction import CallCompleted, CallUncertain
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    EvidenceIntegrityError,
    InvalidTransition,
    OwnershipConflict,
    OperationStopped,
    RevisionConflict,
)
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorIntent,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.lifecycle import CancellationRef
from generator_admission_fixtures import Case, case
from construction_storage_fixtures import put
from test_run_journal import command


def intent(c: Case) -> LocalGeneratorIntent:
    return LocalGeneratorIntent(
        binding=c.binding,
        request_id=c.request.request_id,
        request_ref=evidence_reference(
            c.request.model_dump_json().encode(),
            local_metadata("generator-model-request/1"),
        ),
        parameters_ref=c.event.call.parameters_ref,
        operation=c.operation,
    )


def test_real_journals_role_completion_and_replay_after_stop(tmp_path: Path) -> None:
    c = case(tmp_path)
    result = c.role.generate(c.generation, c.operation)
    assert result.input_sha256 == c.event.call.input_ref.sha256
    assert result.parameters_sha256 == c.event.call.parameters_ref.sha256
    progress = c.deps.construction.read(command())
    done = CallCompleted(operation=command("record-result"), response=result)
    final = c.deps.construction.append(done, progress.revision, done.operation)
    assert final.project().candidates[0].response == result
    c.stop()
    c.execution.denied = "generate"
    c.data.claim_authority.denied = True
    assert c.role.generate(c.generation, c.operation) == result
    assert c.engine.calls == c.engine.validations == 1
    assert c.deps.construction.read(command()) == final


@pytest.mark.parametrize("state", ["unplanned", "uncertain", "stopped", "completed"])
def test_invalid_state_never_reaches_engine(tmp_path: Path, state: str) -> None:
    c = case(tmp_path, planned=state != "unplanned")
    if state == "stopped":
        c.stop()
    elif state == "uncertain":
        progress = c.deps.construction.read(command())
        event = CallUncertain(
            operation=command(),
            request_id=c.request.request_id,
            evidence_ref=put(c.data.store, {"unknown_request": c.request.request_id}),
        )
        c.deps.construction.append(event, progress.revision, event.operation)
    elif state == "completed":
        result = c.role.generate(c.generation, c.operation)
        progress = c.deps.construction.read(command())
        event_done = CallCompleted(operation=command(), response=result)
        c.deps.construction.append(event_done, progress.revision, event_done.operation)
        with pytest.raises(InvalidTransition):
            c.authority.authorize_generate(
                intent(c).model_copy(update={"operation": command()}),
                c.request,
                c.parameters,
                c.controls.bind(command()),
            )
        assert c.engine.calls == 1
        return
    before = c.deps.construction.read(command())
    with pytest.raises(InvalidTransition):
        c.local.generate(c.request, c.operation)
    c.assert_no_inference()
    assert c.deps.construction.read(command()) == before


@pytest.mark.parametrize(
    "which", ["claim", "context", "retrieval", "plan", "access", "generate"]
)
def test_authority_rejections_do_not_publish_intent(tmp_path: Path, which: str) -> None:
    c = case(tmp_path)
    if which == "claim":
        c.data.claim_authority.denied = True
    elif which == "context":
        c.data.context_authority.denied_context = True
    elif which == "retrieval":
        c.data.retrieval_authority.denied = True
    elif which == "plan":
        c.data.authority.denied = True
    else:
        c.execution.denied = which
    with pytest.raises(OwnershipConflict):
        c.local.generate(c.request, c.operation)
    c.assert_no_inference()


@pytest.mark.parametrize(
    "field",
    [
        "source_task_id",
        "release_ref",
        "model_binding_ref",
        "base_parameters_ref",
        "owner",
    ],
)
def test_full_binding_mismatch(tmp_path: Path, field: str) -> None:
    c = case(tmp_path)
    value: object
    if field == "source_task_id":
        value = "other-source"
    elif field == "owner":
        value = c.binding.owner.model_copy(update={"worker_id": "other-worker"})
    else:
        old = getattr(c.binding, field)
        raw = c.data.store.read(old)
        value = c.data.store.put(
            raw,
            local_metadata(old.content_schema).model_copy(
                update={"producer": "other-provenance"}
            ),
        )
    binding = c.binding.model_copy(update={field: value})
    local = DurableGeneratorInference(
        c.root, binding, c.engine, c.data.store, c.controls, c.authority
    )
    with pytest.raises(OwnershipConflict):
        local.generate(c.request, c.operation)
    c.assert_no_inference()


@pytest.mark.parametrize(
    "field",
    ["messages", "generation_input_sha256", "request_id", "seed", "temperature"],
)
def test_actual_message_and_request_tampering(tmp_path: Path, field: str) -> None:
    c = case(tmp_path)
    values: dict[str, object] = {
        "messages": (
            c.request.messages[0],
            c.request.messages[1].model_copy(
                update={"content": "injected private data"}
            ),
        ),
        "generation_input_sha256": "a" * 64,
        "request_id": "unregistered",
        "seed": c.request.seed + 1,
        "temperature": 0.2,
    }
    request = c.request.model_copy(update={field: values[field]})
    with pytest.raises(OwnershipConflict):
        c.local.generate(request, c.operation)
    c.assert_no_inference()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_input_tokens", 1),
        ("max_new_tokens", 1),
        ("top_p", 0.5),
        ("enable_thinking", True),
    ],
)
def test_every_parameter_is_checked_not_only_seed(
    tmp_path: Path, field: str, value: object
) -> None:
    c = case(tmp_path)
    parameters = LocalGeneratorParameters.model_validate(
        c.parameters.model_copy(update={field: value})
    )
    with pytest.raises(OwnershipConflict):
        c.authority.authorize_generate(
            intent(c), c.request, parameters, c.controls.bind(c.operation)
        )
    c.assert_no_inference()


@pytest.mark.parametrize("corrupt", [False, True])
@pytest.mark.parametrize(
    "dependency", ["input", "observation", "parameters", "context", "retrieval"]
)
def test_missing_or_damaged_dependencies(
    tmp_path: Path, corrupt: bool, dependency: str
) -> None:
    c = case(tmp_path)
    reference = {
        "input": c.event.call.input_ref,
        "observation": c.generation.context.initial_observation_ref,
        "parameters": c.event.call.parameters_ref,
        "context": c.data.plan.context_receipt_ref,
        "retrieval": c.data.plan.retrieval_ref,
    }[dependency]
    blob = tmp_path / "evidence" / "blobs" / reference.sha256
    if corrupt:
        blob.write_bytes(b"corrupted")
    else:
        blob.unlink()
    with pytest.raises(EvidenceIntegrityError if corrupt else EvidenceNotFound):
        c.local.generate(c.request, c.operation)
    c.assert_no_inference()


@pytest.mark.parametrize("which", ["run", "construction"])
def test_concurrent_journal_change_is_detected(tmp_path: Path, which: str) -> None:
    c = case(tmp_path)

    def change() -> None:
        if which == "run":
            c.stop()
        else:
            progress = c.deps.construction.read(command())
            event = CallUncertain(
                operation=command(),
                request_id=c.request.request_id,
                evidence_ref=put(
                    c.data.store, {"unknown_request": c.request.request_id}
                ),
            )
            c.deps.construction.append(event, progress.revision, event.operation)

    c.execution.callback = change
    with pytest.raises(RevisionConflict):
        c.local.generate(c.request, c.operation)
    c.assert_no_inference()


@pytest.mark.parametrize("which", ["cancel", "expired", "operation_reuse", "cleanup"])
def test_control_and_operation_boundaries(tmp_path: Path, which: str) -> None:
    c = case(tmp_path)
    operation = c.operation
    expected: type[Exception] = OwnershipConflict
    if which == "cancel":
        operation = command("cancelled-inference").model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="generator-stop", run_id="run", owner_id="owner"
                )
            }
        )
        c.cancel.cancelled = True
        expected = OperationStopped
    elif which == "expired":
        operation = command("expired-inference").model_copy(
            update={"deadline": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        expected = OperationStopped
    elif which == "operation_reuse":
        operation = c.event.operation
    else:
        operation = command(cleanup_parent=c.operation.operation_id)
    with pytest.raises(expected):
        c.local.generate(c.request, operation)
    c.assert_no_inference()


@pytest.mark.parametrize("bad", [None, {}, [], "", True])
def test_invalid_input_types(tmp_path: Path, bad: object) -> None:
    c = case(tmp_path)
    with pytest.raises(ValidationError):
        c.authority.authorize_generate(
            intent(c),
            cast(GeneratorModelRequest, bad),
            c.parameters,
            c.controls.bind(c.operation),
        )
    c.assert_no_inference()


def test_actual_fact_can_reconcile_after_run_stops(tmp_path: Path) -> None:
    c = case(tmp_path)
    c.execution.denied = "completion"
    with pytest.raises(OwnershipConflict) as failure:
        c.local.generate(c.request, c.operation)
    observation = getattr(failure.value, "generator_execution")
    assert observation.fact_ref is not None
    c.stop()
    c.data.claim_authority.denied = True
    c.execution.denied = "generate"
    cleanup = command(cleanup_parent=c.operation.operation_id)
    assert (
        c.local.reconcile(c.request, observation.fact_ref, cleanup)
        == observation.response_ref
    )
    assert c.engine.calls == c.engine.validations == 1


def test_exact_repeated_admission_itself_grants_no_execution(tmp_path: Path) -> None:
    c = case(tmp_path)
    for _ in range(2):
        c.authority.authorize_generate(
            intent(c), c.request, c.parameters, c.controls.bind(c.operation)
        )
    c.assert_no_inference()
    ref = c.local.generate(c.request, c.operation)
    assert c.local.generate(c.request, c.operation) == ref
    assert c.engine.calls == 1


@pytest.mark.parametrize(
    "which", ["request_hash", "request_size", "parameters_metadata"]
)
def test_intent_reference_must_match_actual_request_and_call(
    tmp_path: Path, which: str
) -> None:
    c = case(tmp_path)
    original = intent(c)
    if which == "request_hash":
        reference = c.data.store.put(
            b"unrelated request", local_metadata("generator-model-request/1")
        )
        changed = original.model_copy(update={"request_ref": reference})
    elif which == "request_size":
        changed = original.model_copy(
            update={
                "request_ref": original.request_ref.model_copy(
                    update={"size_bytes": original.request_ref.size_bytes + 1}
                )
            }
        )
    else:
        changed = original.model_copy(
            update={
                "parameters_ref": original.parameters_ref.model_copy(
                    update={"producer": "another-source"}
                )
            }
        )
    with pytest.raises(OwnershipConflict):
        c.authority.authorize_generate(
            changed, c.request, c.parameters, c.controls.bind(c.operation)
        )
    c.assert_no_inference()


def test_cancellation_during_authority_prevents_new_intent(tmp_path: Path) -> None:
    c = case(tmp_path)
    operation = command("cancel-during-admission").model_copy(
        update={
            "cancellation_ref": CancellationRef(
                channel_id="generator-stop", run_id="run", owner_id="owner"
            )
        }
    )
    c.execution.callback = lambda: setattr(c.cancel, "cancelled", True)
    with pytest.raises(OperationStopped, match="CANCELLED"):
        c.local.generate(c.request, operation)
    c.assert_no_inference()


@pytest.mark.parametrize("journal", ["construction", "runs"])
def test_wrong_journal_binding_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: str
) -> None:
    c = case(tmp_path)
    other = c.data.plan.run.model_copy(
        update={
            "release_ref": c.data.plan.run.release_ref.model_copy(
                update={"producer": "other-release"}
            )
        }
    )
    if journal == "construction":
        progress = c.deps.construction.read(command())
        changed_progress = progress.model_copy(
            update={"plan": progress.plan.model_copy(update={"run": other})}
        )
        monkeypatch.setattr(c.deps.construction, "read", lambda op: changed_progress)
    else:
        snapshot = c.deps.runs.read(command())
        changed_snapshot = snapshot.model_copy(update={"binding": other})
        monkeypatch.setattr(c.deps.runs, "read", lambda op: changed_snapshot)
    with pytest.raises(OwnershipConflict):
        c.local.generate(c.request, c.operation)
    c.assert_no_inference()
