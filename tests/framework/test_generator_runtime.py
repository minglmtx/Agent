"""Runtime input, original-result and failure boundaries with synthetic worker."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    DispatchAlreadyCommitted,
    EvidenceNotFound,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorFact,
    LocalGeneratorParameters,
)
from lab_generate_skill.adapters.models.generator_invocation import (
    ResourceGeneratorInvocation,
)
from lab_generate_skill.adapters.models.generator_execution_scope import (
    GeneratorExecutionScope,
)
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.domain.lifecycle import ResourceRecord
from generator_runtime_fixtures import (
    RuntimeCase,
    runtime as runtime,
    e as e,
    execution_template as execution_template,
)


def test_completion_replay_after_original_resource_closed(runtime: RuntimeCase) -> None:
    r = runtime
    ref = r.adapter.generate(r.local.request, r.local.operation)
    snap = r.adapter.inspect(r.local.request, r.local.cleanup)
    assert snap.fact_ref is not None
    r.close()
    r.worker.failure = AssertionError("historical verification cannot execute")
    assert r.adapter.generate(r.local.request, r.local.operation) == ref
    assert r.adapter.reconcile(r.local.request, snap.fact_ref, r.local.cleanup) == ref
    assert r.worker.calls == 1
    record = r.e.adapter.load(snap.intent, r.local.controls.bind(r.local.cleanup))
    assert record.acquired_ref == r.scope.acquired_ref


@pytest.mark.parametrize(
    "fault",
    [
        "record_missing",
        "record_corrupt",
        "reply_corrupt",
        "wrong_output",
        "acquisition_changed",
    ],
)
def test_completed_replay_revalidates_original_provenance(
    runtime: RuntimeCase, fault: str
) -> None:
    r = runtime
    r.adapter.generate(r.local.request, r.local.operation)
    snap = r.adapter.inspect(r.local.request, r.local.cleanup)
    control = r.local.controls.bind(r.local.cleanup)
    record = r.e.adapter.load(snap.intent, control)
    if fault.startswith("record_"):
        path = r.e.root / (snap.intent.key + ".generator-execution.json")
        if fault == "record_missing":
            path.unlink()
        else:
            path.write_bytes(b"{}")
    elif fault == "reply_corrupt":
        blob = r.e.store._blobs / record.reply_ref.sha256
        # Actual store layout is checked by direct lookup, no guessed alternative.
        assert blob.is_file()
        blob.chmod(0o644)
        blob.write_bytes(b"bad")
    elif fault == "wrong_output":
        assert snap.fact_ref is not None
        fact = LocalGeneratorFact.model_validate_json(r.e.store.read(snap.fact_ref))
        wrong = fact.model_copy(
            update={"output": fact.output.model_copy(update={"text": "forged"})}
        )
        with pytest.raises(EvidenceIntegrityError):
            r.actual.verify_completion(wrong, r.local.cleanup, control)
        assert r.worker.calls == 1
        return
    else:
        record0 = r.journal.record
        event = record0.events[-1].model_copy(
            update={"evidence": (r.e.put(b"other", "generator-resource-fact/1"),)}
        )
        r.journal.record = ResourceRecord(
            token=record0.token, events=(*record0.events[:-1], event)
        )
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound)):
        r.adapter.generate(r.local.request, r.local.operation)
    assert r.worker.calls == 1


@pytest.mark.parametrize("fault", ["worker_error", "publish_before", "publish_after"])
def test_unresolved_never_resends_and_original_reply_can_be_published(
    runtime: RuntimeCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    r = runtime
    records = r.e.adapter
    original = type(records).publish
    failure = OSError(fault)
    if fault == "worker_error":
        r.worker.failure = failure
    else:

        def broken(self: object, record: object, control: object) -> None:
            if fault == "publish_after":
                original(self, record, control)  # type: ignore[arg-type]
            raise failure

        monkeypatch.setattr(type(records), "publish", broken)
    with pytest.raises(OSError) as caught:
        r.adapter.generate(r.local.request, r.local.operation)
    assert caught.value is failure and r.worker.calls == 1
    with pytest.raises(DispatchAlreadyCommitted):
        r.adapter.generate(r.local.request, r.local.operation)
    assert r.worker.calls == 1
    snap = r.adapter.inspect(r.local.request, r.local.cleanup)
    assert snap.fact_ref is None
    if fault != "worker_error":
        record = getattr(failure, "generator_execution_candidate")
        monkeypatch.setattr(type(records), "publish", original)
        r.e.adapter.publish(record, r.local.controls.bind(r.local.cleanup))
        assert (
            r.e.adapter.load(snap.intent, r.local.controls.bind(r.local.cleanup))
            == record
        )


@pytest.mark.parametrize(
    "fault",
    ["closed", "source", "request", "parameters", "controller", "thread", "worker"],
)
def test_pre_send_mismatches_have_no_execution_or_invocation(
    runtime: RuntimeCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    r = runtime
    intent = r.e.record.intent
    params = LocalGeneratorParameters.model_validate_json(
        r.e.store.read(intent.parameters_ref)
    )
    request = r.local.request
    from lab_generate_skill.adapters.models import (
        generator_execution_scope as scope_module,
    )

    if fault == "closed":
        r.close()
    elif fault == "source":
        intent = intent.model_copy(
            update={
                "binding": intent.binding.model_copy(update={"source_task_id": "other"})
            }
        )
    elif fault == "request":
        request = request.model_copy(update={"request_id": "other"})
    elif fault == "parameters":
        params = params.model_copy(update={"seed": params.seed + 1})
    elif fault == "controller":
        monkeypatch.setattr(
            scope_module, "current_process_identity", lambda: r.scope.guard.worker
        )
    elif fault == "worker":
        monkeypatch.setattr(
            scope_module,
            "read_process_identity",
            lambda *args: r.scope.guard.controller,
        )

    def invoke() -> None:
        ResourceGeneratorInvocation(r.scope, r.e.adapter).invoke(
            intent, request, params, r.local.controls.bind(r.local.operation)
        )

    with pytest.raises(OwnershipConflict):
        if fault == "thread":
            with ThreadPoolExecutor(1) as executor:
                executor.submit(invoke).result()
        else:
            invoke()
    assert (
        r.worker.calls == 0
        and not list(r.local.root.iterdir())
        and not list(r.e.root.iterdir())
    )


def test_cancel_before_send_does_not_create_intent(runtime: RuntimeCase) -> None:
    from lab_generate_skill.domain.errors import OperationStopped

    r = runtime
    r.local.controls.bind(r.local.operation)._expires = -1
    with pytest.raises(OperationStopped):
        r.adapter.generate(r.local.request, r.local.operation)
    assert r.worker.calls == 0 and not list(r.local.root.iterdir())


def test_completion_failure_after_reply_reconciles_without_model(
    runtime: RuntimeCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = runtime
    cls = type(r.actual)
    original = cls.verify_completion

    def fail(*args: object) -> None:
        raise OSError("verification interrupted")

    monkeypatch.setattr(cls, "verify_completion", fail)
    with pytest.raises(OSError) as caught:
        r.adapter.generate(r.local.request, r.local.operation)
    observed = getattr(caught.value, "generator_execution")
    assert observed.fact_ref is not None
    monkeypatch.setattr(cls, "verify_completion", original)
    r.close()
    assert (
        r.adapter.reconcile(r.local.request, observed.fact_ref, r.local.cleanup)
        == observed.response_ref
    )
    assert r.worker.calls == 1


@pytest.mark.parametrize("field", ["owner", "release_ref", "model_binding_ref"])
def test_new_scope_cannot_rebind_original_acquisition(
    runtime: RuntimeCase, field: str
) -> None:
    r = runtime
    binding = r.scope.binding
    replacement = (
        binding.owner.model_copy(update={"worker_id": "other"})
        if field == "owner"
        else r.e.put(
            b"wrong",
            "release-manifest/1" if field == "release_ref" else "model-binding/1",
        )
    )
    with pytest.raises(OwnershipConflict):
        GeneratorExecutionScope(
            binding.model_copy(update={field: replacement}),
            r.scope.spec,
            r.scope.journal,
            r.scope.evidence,
            r.scope.engine,
            r.local.operation,
            r.local.controls.bind(r.local.operation),
        )
    assert r.worker.calls == 0


def test_two_sources_same_request_id_keep_separate_records(
    runtime: RuntimeCase,
) -> None:
    from lab_generate_skill.adapters.models.local_generator import (
        DurableGeneratorInference,
    )
    from lab_generate_skill.adapters.models.generator_execution_authority import (
        ResourceGeneratorExecutionAuthority,
    )

    r = runtime
    binding = r.scope.binding.model_copy(update={"source_task_id": "source-two"})
    scope = GeneratorExecutionScope(
        binding,
        r.scope.spec,
        r.scope.journal,
        r.scope.evidence,
        r.scope.engine,
        r.local.operation,
        r.local.controls.bind(r.local.operation),
    )
    second = DurableGeneratorInference(
        r.local.root,
        binding,
        ResourceGeneratorInvocation(scope, r.e.adapter),
        r.e.store,
        r.local.controls,
        ResourceGeneratorExecutionAuthority(scope, r.e.adapter),
    )
    first_ref = r.adapter.generate(r.local.request, r.local.operation)
    second_ref = second.generate(r.local.request, r.local.operation)
    one = r.adapter.inspect(r.local.request, r.local.cleanup)
    two = second.inspect(r.local.request, r.local.cleanup)
    assert one.intent.key != two.intent.key
    assert (
        r.e.adapter.load(one.intent, r.local.controls.bind(r.local.cleanup)).intent
        != r.e.adapter.load(two.intent, r.local.controls.bind(r.local.cleanup)).intent
    )
    assert r.worker.calls == 2
    assert r.adapter.generate(r.local.request, r.local.operation) == first_ref
    assert second.generate(r.local.request, r.local.operation) == second_ref
    assert (
        r.worker.calls == 2
    )  # Same-controller interleaving, not a parallel-source claim.


def test_foreign_cleanup_cannot_confirm_completion(runtime: RuntimeCase) -> None:
    r = runtime
    r.adapter.generate(r.local.request, r.local.operation)
    snap = r.adapter.inspect(r.local.request, r.local.cleanup)
    assert snap.fact_ref is not None
    fact = LocalGeneratorFact.model_validate_json(r.e.store.read(snap.fact_ref))
    op = r.local.cleanup.model_copy(
        update={"operation_id": "bad-parent", "parent_operation_id": "other"}
    )
    with pytest.raises(OwnershipConflict):
        r.actual.verify_completion(fact, op, r.local.controls.bind(op))
    assert r.worker.calls == 1


@pytest.mark.parametrize("fault", ["missing", "corrupt", "operation"])
def test_acquisition_change_refuses_before_inference(
    runtime: RuntimeCase, fault: str
) -> None:
    r = runtime
    if fault == "operation":
        from datetime import timedelta

        prior = r.journal.record
        acquired = prior.events[-1]
        changed = acquired.model_copy(
            update={
                "operation": acquired.operation.model_copy(
                    update={
                        "deadline": acquired.operation.deadline + timedelta(seconds=1)
                    }
                )
            }
        )
        r.journal.record = ResourceRecord(
            token=prior.token, events=(*prior.events[:-1], changed)
        )
    else:
        blob = r.e.store._blobs / r.scope.acquired_ref.sha256
        if fault == "missing":
            blob.unlink()
        else:
            blob.write_bytes(b"bad")
    with pytest.raises((EvidenceIntegrityError, EvidenceNotFound)):
        r.adapter.generate(r.local.request, r.local.operation)
    assert r.worker.calls == 0
    assert not list(r.e.root.iterdir())
    assert not list(r.local.root.glob("*.local-generator.json"))


def test_bad_returned_exchange_retains_bytes_without_retry(
    runtime: RuntimeCase,
) -> None:
    r = runtime
    r.worker.output = r.worker.output.model_copy(update={"prompt_tokens": 101})
    with pytest.raises(ValueError, match="frozen token limits") as caught:
        r.adapter.generate(r.local.request, r.local.operation)
    assert getattr(caught.value, "generator_execution_exchange").reply
    assert (
        getattr(caught.value, "generator_execution_candidate").intent.request_id
        == r.local.request.request_id
    )
    with pytest.raises(DispatchAlreadyCommitted):
        r.adapter.generate(r.local.request, r.local.operation)
    assert r.worker.calls == 1
