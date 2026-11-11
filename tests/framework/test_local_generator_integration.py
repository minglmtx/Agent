"""Actual public-role/CAS/durable-inference seam, explicit unit model only."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.local_generator import LocalGeneratorSnapshot
from lab_generate_skill.generator.candidates import RecordedGenerator
from generator_fixtures import fixture
from local_generator_fixtures import case


def test_role_uses_durable_inference_and_actual_parameters(tmp_path: Path) -> None:
    c = case(tmp_path)
    public_root = tmp_path / "public"
    public_root.mkdir()
    public = fixture(public_root)
    # All public and private evidence resides in one explicitly supplied CAS.
    c.evidence = public.evidence
    # Copy only the binding evidence; no production authority is implied.
    source = FileEvidenceStore(tmp_path / "evidence")
    for ref in (
        c.binding.release_ref,
        c.binding.model_binding_ref,
        c.binding.base_parameters_ref,
    ):
        assert (
            c.evidence.put(source.read(ref), local_metadata(ref.content_schema)) == ref
        )
    inference = DurableGeneratorInference(
        c.root, c.binding, c.engine, c.evidence, c.controls, c.authority
    )
    generator = RecordedGenerator(
        public.observations, inference, c.evidence, c.controls
    )
    result = generator.generate(public.request, c.operation)
    assert generator.generate(public.request, c.operation) == result
    assert c.engine.calls == 1
    assert c.evidence.read(result.response_ref)


def test_error_after_state_commit_preserves_known_refs_and_never_reexecutes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = case(tmp_path)
    write = SnapshotTransaction.write
    error = ExceptionGroup("sync and cleanup", [OSError("sync"), OSError("close")])

    def failed(tx: SnapshotTransaction, raw: bytes) -> None:
        write(tx, raw)
        if LocalGeneratorSnapshot.model_validate_json(raw).fact_ref is not None:
            raise error

    monkeypatch.setattr(SnapshotTransaction, "write", failed)
    with pytest.raises(ExceptionGroup) as caught:
        c.adapter().generate(c.request, c.operation)
    assert caught.value is error
    observed = getattr(error, "generator_execution")
    snapshot = c.adapter().inspect(c.request, c.cleanup)
    assert (
        snapshot.fact_ref == observed.fact_ref
        and snapshot.response_ref == observed.response_ref
    )
    monkeypatch.setattr(SnapshotTransaction, "write", write)
    assert c.adapter().generate(c.request, c.operation) == observed.response_ref
    assert c.engine.calls == 1
