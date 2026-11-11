"""Public role, actual CAS records and construction digest compatibility."""

from lab_generate_skill.ports.lifecycle import OperationControl

import hashlib
import json
from pathlib import Path
from datetime import timedelta
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.generation import Generator
from generator_fixtures import fixture, put
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.lifecycle import OperationContext
from release_current_fixtures import op


def test_role_uses_saved_response_and_preserves_construction_input_identity(
    tmp_path: Path,
) -> None:
    case = fixture(tmp_path)
    operation = op("generate")
    role: Generator = case.generator
    result = role.generate(case.request, operation)
    assert (
        result.input_sha256
        == hashlib.sha256(case.request.model_dump_json().encode()).hexdigest()
    )
    assert case.inference.saved is not None
    assert result.input_sha256 != case.inference.saved[0].model_input_sha256
    assert role.generate(case.request, operation) == result
    assert case.inference.calls == 2 and case.inference.executions == 1
    assert case.evidence.read(result.response_ref)


@pytest.mark.parametrize(
    "fault", ["request", "source_digest", "wire_digest", "seed", "temperature"]
)
def test_return_binding_and_actual_sampling_mismatch_stop_without_retry(
    tmp_path: Path, fault: str
) -> None:
    case = fixture(tmp_path)
    case.inference.mismatch = fault
    with pytest.raises(OwnershipConflict) as caught:
        case.generator.generate(case.request, op("generate"))
    assert case.inference.calls == 1 and case.inference.saved is not None
    assert getattr(caught.value, "generator_response_ref") == case.inference.saved[1]
    assert case.evidence.read(case.inference.saved[1])


@pytest.mark.parametrize("fault", ["empty", "length", "bad_json"])
def test_bad_model_result_stays_saved_and_never_resampled(
    tmp_path: Path, fault: str
) -> None:
    case = fixture(tmp_path)
    if fault == "empty":
        case.inference.text = ""
    elif fault == "length":
        case.inference.finish = "length"
    else:
        case.inference.text = "{bad"
    with pytest.raises(ValueError) as caught:
        case.generator.generate(case.request, op("generate"))
    assert case.inference.calls == 1 and case.inference.saved is not None
    assert getattr(caught.value, "generator_response_ref") == case.inference.saved[1]


def test_store_failure_after_saved_response_preserves_chain_and_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = fixture(tmp_path)
    read = case.evidence.read
    error = ExceptionGroup("read and close", [OSError("read"), OSError("close")])

    def fail(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if reference.content_schema == "generator-model-response/1":
            raise error
        return read(reference)

    monkeypatch.setattr(case.evidence, "read", fail)
    with pytest.raises(ExceptionGroup) as caught:
        case.generator.generate(case.request, op("generate"))
    assert caught.value is error and case.inference.calls == 1
    assert read(getattr(error, "generator_response_ref"))


def test_bad_store_bytes_are_not_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = fixture(tmp_path)
    read = case.evidence.read

    def wrong(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if reference.content_schema == "generator-model-response/1":
            return b"corrupted"
        return read(reference)

    monkeypatch.setattr(case.evidence, "read", wrong)
    with pytest.raises(EvidenceIntegrityError):
        case.generator.generate(case.request, op("generate"))
    assert case.inference.calls == 1


def test_cleanup_attempt_and_expired_operations_do_not_infer(tmp_path: Path) -> None:
    case = fixture(tmp_path)
    original = op("generate")
    for operation in (
        original.model_copy(update={"mode": "cleanup", "parent_operation_id": "prior"}),
        original.model_copy(update={"attempt_id": "attempt"}),
    ):
        with pytest.raises(OwnershipConflict):
            case.generator.generate(case.request, operation)
    expired = original.model_copy(
        update={"deadline": original.deadline - timedelta(seconds=120)}
    )
    with pytest.raises(OperationStopped):
        case.generator.generate(case.request, expired)
    assert case.inference.calls == 0


@pytest.mark.parametrize("fault", ["public", "schema", "oversize", "noncanonical"])
def test_invalid_completion_envelope_retains_original_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = fixture(tmp_path)
    original = case.inference.generate

    def invalid(
        request: GeneratorModelRequest, operation: OperationContext
    ) -> EvidenceRef:
        reference = original(request, operation)
        if fault == "public":
            return reference.model_copy(update={"visibility": "public"})
        if fault == "schema":
            return reference.model_copy(update={"content_schema": "old/1"})
        if fault == "oversize":
            return reference.model_copy(update={"size_bytes": 1024 * 1024 + 1})
        raw = json.dumps(json.loads(case.evidence.read(reference)), indent=2).encode()
        return put(case.evidence, raw, "generator-model-response/1")

    monkeypatch.setattr(case.inference, "generate", invalid)
    with pytest.raises((ValueError, EvidenceIntegrityError)) as caught:
        case.generator.generate(case.request, op("generate"))
    assert hasattr(caught.value, "generator_response_ref")
    assert case.inference.calls == 1 and case.inference.saved is not None
    assert case.evidence.read(case.inference.saved[1])


def test_stop_after_saved_inference_preserves_response_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = fixture(tmp_path)
    operation = op("generate")
    control = case.controls.bind(operation)
    original = case.inference.generate

    def stopped() -> float:
        raise OperationStopped("CANCELLED", operation.operation_id)

    def generate(
        request: GeneratorModelRequest, current: OperationContext
    ) -> EvidenceRef:
        result = original(request, current)
        monkeypatch.setattr(control, "checkpoint", stopped)
        return result

    monkeypatch.setattr(case.inference, "generate", generate)
    with pytest.raises(OperationStopped) as caught:
        case.generator.generate(case.request, operation)
    assert case.inference.calls == 1
    assert case.evidence.read(getattr(caught.value, "generator_response_ref"))
