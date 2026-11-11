"""Production source publisher from actual frozen CAS/claim ports; resource rights unit-only."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.execution_task_source import (
    publish_execution_task_source,
    ExecutionSourcePublicationUnconfirmed,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_fixtures import execution_case
from test_run_journal import command
from construction_storage_fixtures import put


def test_original_frozen_source_publication_is_reused_by_same_real_task_plan(
    tmp_path: Path,
) -> None:
    c = execution_case(tmp_path / "single")
    s = c.source
    op = command("readonly-republish-source")
    before = c.deps.runs.read(c.plan.read_operation)
    published = publish_execution_task_source(
        s.binding.run,
        s.binding.claim_ref,
        op,
        reader=s.source_reader,
        evidence=c.deps.evidence,
        controls=c.deps.controls,
    )
    assert (
        published.source == s.source
        and published.source_ref == s.source_ref == c.plan.source_ref
    )
    assert (
        ExecutionTaskSource.model_validate_json(
            c.source.data.store.read(published.source_ref)
        )
        == s.source
    )
    assert c.deps.runs.read(c.plan.read_operation) == before
    assert not c.phases.calls and c.model.calls == c.browser.calls == 0


def test_source_manifest_identity_is_checked_before_private_dependency_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "single")
    source = c.source.source
    other = source.model_copy(
        update={
            "intent": source.intent.model_copy(
                update={
                    "binding": source.intent.binding.model_copy(
                        update={"attempt_id": "foreign-attempt"}
                    )
                }
            )
        }
    )
    ref = put(c.source.data.store, other, other.schema_version)
    plan = c.plan.model_copy(update={"source_ref": ref})

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "A substituted manifest must be denied before reading its private graph"
        )

    monkeypatch.setattr(c.source.source_reader, "verify_source", forbidden)
    with pytest.raises(OwnershipConflict, match="manifest changed"):
        c.source.source_reader.load(
            plan, plan.read_operation, c.deps.controls.bind(plan.read_operation)
        )
    assert not c.phases.calls


@pytest.mark.parametrize(
    "fault", ["claim-revoked", "foreign-owner", "attempt-scope", "legacy-claim"]
)
def test_invalid_source_or_scope_cannot_publish_or_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = execution_case(tmp_path / "single")
    s = c.source
    op = command("bad-source")
    claim = s.binding.claim_ref
    if fault == "claim-revoked":
        s.claim_authority.denied = True
    elif fault == "foreign-owner":
        op = op.model_copy(update={"owner_id": "foreign"})
    elif fault == "attempt-scope":
        op = op.model_copy(update={"attempt_id": s.binding.attempt_id})
    else:
        claim = s.source.source_context_receipt_ref
    puts = []

    def no_put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        puts.append(metadata.content_schema)
        raise AssertionError("Invalid source may not publish")

    monkeypatch.setattr(c.deps.evidence, "put", no_put)
    with pytest.raises((OwnershipConflict, ValueError)):
        publish_execution_task_source(
            s.binding.run,
            claim,
            op,
            reader=s.source_reader,
            evidence=c.deps.evidence,
            controls=c.deps.controls,
        )
    assert puts == [] and not c.phases.calls


def test_partial_source_publication_retains_candidate_and_original_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "single")
    s = c.source
    put = c.deps.evidence.put
    failure = OSError("original source publication acknowledgement lost")
    known = []

    def lost(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        ref = put(raw, metadata, control=control)
        known.append(ref)
        raise failure

    monkeypatch.setattr(c.deps.evidence, "put", lost)
    with pytest.raises(ExecutionSourcePublicationUnconfirmed) as caught:
        publish_execution_task_source(
            s.binding.run,
            s.binding.claim_ref,
            command("source-publish-lost"),
            reader=s.source_reader,
            evidence=c.deps.evidence,
            controls=c.deps.controls,
        )
    assert caught.value.primary is failure and caught.value.__cause__ is failure
    assert caught.value.candidates == tuple(known) == (s.source_ref,)
    assert not c.phases.calls and c.model.calls == 0
    assert s.claims.require_source(
        s.binding.claim_ref, s.binding.run, s.source.task, command()
    )


def test_source_permission_revoked_during_publication_is_unconfirmed_without_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = execution_case(tmp_path / "single")
    s = c.source
    put = c.deps.evidence.put

    def revoke(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        ref = put(raw, metadata, control=control)
        s.claim_authority.denied = True
        return ref

    monkeypatch.setattr(c.deps.evidence, "put", revoke)
    with pytest.raises(ExecutionSourcePublicationUnconfirmed) as caught:
        publish_execution_task_source(
            s.binding.run,
            s.binding.claim_ref,
            command("source-revoked-after-put"),
            reader=s.source_reader,
            evidence=c.deps.evidence,
            controls=c.deps.controls,
        )
    assert isinstance(caught.value.primary, OwnershipConflict)
    assert caught.value.candidates == (s.source_ref,)
    assert not c.phases.calls


def test_expired_source_publication_stops_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timezone

    c = execution_case(tmp_path / "single")
    s = c.source
    op = command("expired-source").model_copy(
        update={"deadline": datetime(2000, 1, 1, tzinfo=timezone.utc)}
    )
    puts = []

    def no_put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        puts.append(metadata)
        raise AssertionError("Expired source may not publish")

    monkeypatch.setattr(c.deps.evidence, "put", no_put)
    with pytest.raises(OperationStopped):
        publish_execution_task_source(
            s.binding.run,
            s.binding.claim_ref,
            op,
            reader=s.source_reader,
            evidence=c.deps.evidence,
            controls=c.deps.controls,
        )
    assert puts == [] and not c.phases.calls


@pytest.mark.parametrize("bad", [None, {}, [], True, "", 0])
def test_empty_or_wrong_claim_input_refuses_before_publication(
    tmp_path: Path, bad: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import cast

    c = execution_case(tmp_path / "single")
    s = c.source
    puts = []

    def no_put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        puts.append(metadata)
        raise AssertionError("Malformed claim may not publish")

    monkeypatch.setattr(c.deps.evidence, "put", no_put)
    with pytest.raises(ValueError):
        publish_execution_task_source(
            s.binding.run,
            cast(EvidenceRef, bad),
            command("bad-claim-type"),
            reader=s.source_reader,
            evidence=c.deps.evidence,
            controls=c.deps.controls,
        )
    assert puts == [] and not c.phases.calls
