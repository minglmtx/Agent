"""Source/phase/consumer and uncertain-commit gates over one nontraining case."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.application.export_targets import (
    export_targets,
    ExportUnconfirmed,
)
from lab_generate_skill.application.dataset_reader import load_dataset
from lab_generate_skill.adapters.training.dataset_encoding import encode_loaded_dataset
from lab_generate_skill.domain.dataset import TrainingExample, TrainingLabels
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportReceipt,
    DatasetLoadPlan,
    TrainingTargetQualification,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.policies.dataset_manifest import export_metadata, make_manifest
from export_targets_fixtures import ExportCase, export_case, UnitChatTokenizer
from construction_storage_fixtures import put


@dataclass(frozen=True)
class Saved:
    case: ExportCase
    plan: ExportPlan
    receipt: ExportReceipt
    receipt_ref: EvidenceRef
    data: LoadedDataset


@pytest.fixture(scope="module")
def saved(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Saved]:
    with pytest.MonkeyPatch.context() as patch:
        c = export_case(tmp_path_factory.mktemp("export-boundaries") / "case", patch)
        plan = c.plan("boundary-saved")
        receipt = export_targets(plan, c.deps)
        ref = evidence_reference(
            receipt.model_dump_json().encode(), export_metadata("export-receipt/1")
        )
        data = load_dataset(c.load_plan(ref, "boundary-initial-read"), c.deps)
        yield Saved(c, plan, receipt, ref, data)
        assert c.review.control.source.native.loader.session.calls == 5
        assert len(c.review.control.wire.transport.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "export-plan/0"},
        {"sources": ()},
        {"sources": []},
        {"seed": True},
        {"seed": "42"},
        {"seed": -1},
        {"validation_ratio": 0.0},
        {"validation_ratio": 1.0},
        {"validation_ratio": float("nan")},
        {"export_id": ""},
        {"scope_ref": None},
        {"unknown_field": True},
    ],
)
def test_export_plan_rejects_wrong_types_empty_versions_and_ranges(
    saved: Saved, change: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        ExportPlan.model_validate({**saved.plan.model_dump(), **change})


def test_duplicate_sources_heldout_scope_and_formal_engineering_scope_rejected(
    saved: Saved,
) -> None:
    p = saved.plan
    with pytest.raises(ValidationError, match="Duplicate export"):
        ExportPlan.model_validate({**p.model_dump(), "sources": p.sources * 2})
    scope = saved.case.scope
    heldout = scope.allowed_tasks[0].model_copy(update={"split": "test"})
    for change in (
        {"allowed_tasks": (heldout,)},
        {"kind": "formal", "allowed_evaluation_scopes": ("engineering",)},
    ):
        with pytest.raises(ValidationError):
            ExportScope.model_validate({**scope.model_dump(), **change})


def test_fixture_cannot_be_relabelled_or_sent_to_sft(saved: Saved) -> None:
    row = saved.data.examples[0]
    for labels in (
        {"training_data": True},
        {"teacher_mode": "authorized_api"},
        {"target_status": "environment_verified"},
    ):
        with pytest.raises(ValidationError, match="Fixture examples"):
            TrainingExample.model_validate(
                {**row.model_dump(), "labels": {**row.labels.model_dump(), **labels}}
            )
    read = saved.case.load_plan(saved.receipt_ref, "reject-fixture-sft")
    with pytest.raises(ValidationError, match="Fixture artifacts"):
        DatasetLoadPlan.model_validate({**read.model_dump(), "purpose": "sft"})
    with pytest.raises(EvidenceIntegrityError, match="Fixture, empty or accumulation"):
        encode_loaded_dataset(
            replace(saved.data, purpose="sft"),
            object(),
            max_seq_length=16384,
            control=saved.case.deps.controls.bind(read.operation),
        )
    with pytest.raises(EvidenceIntegrityError, match="artifact kind"):
        load_dataset(
            DatasetLoadPlan.model_validate(
                {**read.model_dump(), "expected_kind": "formal"}
            ),
            saved.case.deps,
        )


def test_formal_labels_do_not_qualify_actual_engineering_source(saved: Saved) -> None:
    c = saved.case
    store = c.review.control.source.data.store
    scope = ExportScope.model_validate(
        {
            **c.scope.model_dump(),
            "kind": "formal",
            "allowed_evaluation_scopes": ("benchmark",),
        }
    )
    scope_ref = put(store, scope, "export-scope/1")
    q = TrainingTargetQualification.model_validate_json(store.read(c.qualification_ref))
    forged = TrainingTargetQualification.model_validate(
        {
            **q.model_dump(),
            "kind": "formal",
            "scope_ref": scope_ref,
            "labels": TrainingLabels(
                training_data=True,
                output_purpose="training",
                target_status="environment_verified",
                teacher_mode="authorized_api",
            ),
        }
    )
    qref = put(store, forged, "training-target-qualification/1")
    original = c.plan("formal-label-forgery")
    source = original.sources[0].model_copy(update={"qualification_ref": qref})
    plan = ExportPlan.model_validate(
        {
            **original.model_dump(),
            "kind": "formal",
            "scope_ref": scope_ref,
            "sources": (source,),
        }
    )
    result = export_targets(plan, c.deps)
    assert (
        result.status == "empty"
        and result.dataset_ref is None
        and result.example_count == 0
    )
    assert result.decisions[0].reason_code == "unit_source_cannot_be_formal"
    ref = evidence_reference(
        result.model_dump_json().encode(), export_metadata("export-receipt/1")
    )
    read = DatasetLoadPlan(
        export_receipt_ref=ref,
        expected_kind="formal",
        purpose="inspect",
        sources=plan.sources,
        operation=plan.operation,
    )
    loaded = load_dataset(read, c.deps)
    assert loaded.examples == () and loaded.manifest is None
    assert (
        encode_loaded_dataset(
            loaded,
            object(),
            max_seq_length=16384,
            control=c.deps.controls.bind(read.operation),
        )
        == ()
    )


@pytest.mark.parametrize("mode", ["denied", "cancelled", "expired"])
def test_stop_before_publication_retains_primary_and_no_candidate_refs(
    saved: Saved, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    c = saved.case
    plan = c.plan("stop-" + mode)
    if mode == "denied":
        monkeypatch.setattr(c.authority, "denied", True)
    elif mode == "expired":
        now = datetime.now(timezone.utc) - timedelta(seconds=5)
        # Move all readonly operation deadlines together; do not create dispatch IDs.
        read = plan.sources[0].review_read
        read = read.model_copy(
            update={
                "operation": read.operation.model_copy(update={"deadline": now}),
                "tasks": tuple(
                    t.model_copy(
                        update={
                            "operation": t.operation.model_copy(
                                update={"deadline": now}
                            )
                        }
                    )
                    for t in read.tasks
                ),
                "teachers": tuple(
                    t.model_copy(
                        update={
                            "operation": t.operation.model_copy(
                                update={"deadline": now}
                            )
                        }
                    )
                    for t in read.teachers
                ),
            }
        )
        plan = ExportPlan.model_validate(
            {
                **plan.model_dump(),
                "sources": (plan.sources[0].model_copy(update={"review_read": read}),),
                "operation": plan.operation.model_copy(update={"deadline": now}),
            }
        )
    else:

        def cancelled(*args: object, **kwargs: object) -> None:
            raise OperationStopped("CANCELLED", plan.operation.operation_id)

        monkeypatch.setattr(c.authority, "verify_scope", cancelled)
    with pytest.raises(ExportUnconfirmed) as caught:
        export_targets(plan, c.deps)
    error = caught.value
    assert error.phase == "original_scope_and_sources" and error.retained == ()
    assert isinstance(
        error.primary, PermissionError if mode == "denied" else OperationStopped
    )
    assert error.__cause__ is not None


def test_repeated_exact_export_keeps_refs_and_does_not_repeat_roles(
    saved: Saved,
) -> None:
    assert export_targets(saved.plan, saved.case.deps) == saved.receipt


class LostAckStore:
    def __init__(self, original: EvidenceStore, fail_at: int) -> None:
        self.original, self.fail_at = original, fail_at
        self.committed: list[EvidenceRef] = []
        self.error = OSError("unit: committed CAS, acknowledgement lost")

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        return self.original.read(ref, control)

    def put(
        self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
    ) -> EvidenceRef:
        ref = self.original.put(data, metadata, control)
        self.committed.append(ref)
        if len(self.committed) == self.fail_at:
            raise self.error
        return ref


@pytest.mark.parametrize(
    "stage,phase",
    [
        (1, "publish_original_plan"),
        (2, "publish_example"),
        (3, "publish_manifest"),
        (4, "publish_receipt"),
    ],
)
def test_commit_with_lost_ack_retains_exact_refs_and_only_readback(
    saved: Saved, stage: int, phase: str
) -> None:
    c = saved.case
    store = LostAckStore(c.deps.evidence, stage)
    with pytest.raises(ExportUnconfirmed) as caught:
        export_targets(
            c.plan("lost-ack-" + str(stage)), replace(c.deps, evidence=store)
        )
    error = caught.value
    assert error.primary is store.error and error.phase == phase
    assert error.retained == tuple(store.committed) and len(error.retained) == stage
    assert len(error.decisions) == 1 and error.decisions[0].status == "exported"
    read_control = c.deps.controls.bind(c.plan("read-lost-" + str(stage)).operation)
    for ref in error.retained:
        metadata = EvidenceMetadata(
            media_type=ref.media_type,
            content_schema=ref.content_schema,
            visibility=ref.visibility,
            producer=ref.producer,
        )
        assert evidence_reference(store.read(ref, read_control), metadata) == ref
    assert len(store.committed) == stage  # resolution above is read-only, no retry.


@pytest.mark.parametrize("field", ["messages", "target_skill_ref", "goal_group_id"])
def test_self_consistent_forged_dataset_cannot_replace_original_source(
    saved: Saved, field: str
) -> None:
    c = saved.case
    row = saved.data.examples[0]
    change: dict[str, Any]
    if field == "messages":
        change = {
            "messages": (
                row.messages[0],
                row.messages[1].model_copy(
                    update={"content": "substituted public task"}
                ),
                row.messages[2],
            )
        }
    elif field == "target_skill_ref":
        other = c.review.sealed.project().candidates[0].response.skill
        ref = put(
            c.review.control.source.data.store, other, "compact-skill/1", "public"
        )
        change = {"target_skill_ref": ref}
    else:
        change = {"goal_group_id": "forged-goal-group"}
    forged = TrainingExample.model_validate({**row.model_dump(), **change})
    manifest = make_manifest(saved.plan, saved.receipt.export_plan_ref, (forged,))
    store = c.review.control.source.data.store
    for value, schema in (
        (forged, "training-example/1"),
        (manifest, "dataset-manifest/1"),
    ):
        store.put(value.model_dump_json().encode(), export_metadata(schema))
    mref = evidence_reference(
        manifest.model_dump_json().encode(), export_metadata("dataset-manifest/1")
    )
    receipt = ExportReceipt.model_validate(
        {**saved.receipt.model_dump(), "dataset_ref": mref}
    )
    ref = store.put(
        receipt.model_dump_json().encode(), export_metadata("export-receipt/1")
    )
    with pytest.raises(EvidenceIntegrityError, match="Manifest changed"):
        load_dataset(c.load_plan(ref, "tamper-" + field), c.deps)


def test_consumer_rechecks_authority_after_original_export(
    saved: Saved, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = saved.case
    monkeypatch.setattr(c.authority, "denied", True)
    with pytest.raises(RuntimeError) as caught:
        load_dataset(c.load_plan(saved.receipt_ref, "revoked-source-right"), c.deps)
    assert isinstance(getattr(caught.value, "primary", None), PermissionError)


def test_second_source_failure_retains_first_decision_without_partial_publication(
    saved: Saved, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = saved.case
    original = c.plan("partial-source")
    second = original.sources[0].model_copy(
        update={
            "example_id": "unit-second-unread-source",
            "legacy_id": "unit-second-unread-source",
        }
    )
    plan = ExportPlan.model_validate(
        {**original.model_dump(), "sources": (*original.sources, second)}
    )
    real_load = c.deps.inputs.load
    primary = OSError("unit second source read incomplete")
    count = 0

    def load(*args: Any, **kwargs: Any) -> Any:
        nonlocal count
        count += 1
        if count == 2:
            raise primary
        return real_load(*args, **kwargs)

    monkeypatch.setattr(c.deps.inputs, "load", load)
    with pytest.raises(ExportUnconfirmed) as caught:
        export_targets(plan, c.deps)
    assert caught.value.primary is primary and count == 2
    assert caught.value.retained == () and len(caught.value.decisions) == 1
    assert caught.value.decisions[0].status == "exported"
    assert len(getattr(caught.value.__cause__, "examples", ())) == 1
