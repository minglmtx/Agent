"""Current adoption never grants native rights or weakens ordinary wire data."""

import json
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.bootstrap.current_initial_adoption import (
    stage_initial_adoption_checks,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.initial_adoption import InitialAdoptionInputs
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceChecks,
    EquivalenceReceipt,
    assemble_equivalence,
)
from current_initial_adoption_fixtures import CurrentInitialCase, current_initial_case


@pytest.fixture(scope="module")
def case(tmp_path_factory: pytest.TempPathFactory) -> CurrentInitialCase:
    return current_initial_case(tmp_path_factory.mktemp("initial-adoption") / "case")


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "null",
        "type",
        "source-digest",
        "source-version",
        "old-owner",
        "attempt",
        "context",
    ],
)
def test_adoption_requires_complete_exact_current_selection(
    case: CurrentInitialCase, fault: str
) -> None:
    assert case.inputs.adoption is not None
    body = json.loads(case.inputs.adoption.model_dump_json())
    if fault == "missing":
        del body["source"]
    elif fault == "null":
        body["source"] = None
    elif fault == "type":
        body["binding"] = []
    elif fault == "source-digest":
        body["binding"]["execution_source_ref"]["sha256"] = "f" * 64
    elif fault == "source-version":
        body["binding"]["execution_source_ref"][
            "content_schema"
        ] = "execution-task-source/1"
    elif fault == "old-owner":
        body["binding"]["scope"]["owner"] = json.loads(
            case.inputs.source.scope.owner.model_dump_json()
        )
    elif fault == "attempt":
        body["binding"]["scope"]["attempt_id"] = "other"
    else:
        body["binding"]["source_context_ref"]["sha256"] = "f" * 64
    with pytest.raises((ValidationError, OwnershipConflict, ValueError)):
        InitialAdoptionInputs.model_validate_json(json.dumps(body))


@pytest.mark.parametrize(
    "fault", ["none", "parent", "current", "historical", "owner", "thread", "cancel"]
)
def test_every_read_rechecks_current_claim_parent_and_cancellation(
    case: CurrentInitialCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = case
    op = c.receipt.operation
    gate: OperationControl = c.records.controls.bind(op)
    assert c.inputs.adoption is not None
    c.live.verify_adoption(c.inputs.adoption, op, gate)
    if fault in ("parent", "current"):
        monkeypatch.setattr(c.original.authority, "denied", fault)
    elif fault == "historical":
        monkeypatch.setattr(c.original.contexts, "denied", True)
    elif fault == "owner":
        op = op.model_copy(update={"owner_id": "other"})
    elif fault == "thread":
        monkeypatch.setattr(c.live, "owner", (-1, -1))
    elif fault == "cancel":

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", op.operation_id)

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        gate = Cancelled()
    if fault == "none":
        c.live.verify_adoption(c.inputs.adoption, op, gate)
    else:
        with pytest.raises((OwnershipConflict, PermissionError, OperationStopped)):
            c.live.verify_adoption(c.inputs.adoption, op, gate)


def test_no_implicit_cross_owner_read_downgrade_or_source_republication(
    case: CurrentInitialCase,
) -> None:
    c = case
    ordinary = EvidenceContextRecords(c.records.store, c.records.controls, c.authority)
    with pytest.raises(OwnershipConflict):
        ordinary.load_context(c.inputs.source_ref, c.receipt.operation)
    with pytest.raises(OwnershipConflict):
        ordinary.facts.verify_equivalence_inputs(
            c.inputs,
            c.receipt,
            c.receipt.operation,
            c.records.controls.bind(c.receipt.operation),
        )
    with pytest.raises(OwnershipConflict):
        c.records.publish_context(c.inputs.source, c.receipt.operation)
    with pytest.raises(OwnershipConflict):
        c.records.facts.verify_adoption(
            None, c.receipt.operation, c.records.controls.bind(c.receipt.operation)
        )


@pytest.mark.parametrize("kind", ["checks", "receipt"])
def test_ordinary_schema_forbids_even_null_adoption_and_new_schema_requires_it(
    case: CurrentInitialCase, kind: str
) -> None:
    cls = EquivalenceChecks if kind == "checks" else EquivalenceReceipt
    value = case.inputs.checks if kind == "checks" else case.receipt
    body = json.loads(value.model_dump_json())
    body["schema_version"] = "equivalence-" + kind + "/1"
    body["adoption"] = None
    if kind == "receipt":
        body["checks_ref"]["content_schema"] = "equivalence-checks/1"
    with pytest.raises(ValidationError):
        cls.model_validate_json(json.dumps(body))
    del body["adoption"]
    original = cls.model_validate_json(json.dumps(body))
    assert "adoption" not in json.loads(original.model_dump_json())
    body["schema_version"] = "equivalence-" + kind + "/2"
    if kind == "receipt":
        body["checks_ref"]["content_schema"] = "equivalence-checks/2"
    with pytest.raises((ValidationError, OwnershipConflict)):
        cls.model_validate_json(json.dumps(body))


def test_missing_complete_adoption_cannot_assemble_current_equivalence(
    case: CurrentInitialCase,
) -> None:
    with pytest.raises(OwnershipConflict):
        assemble_equivalence(
            case.inputs.model_copy(update={"adoption": None}), case.receipt.operation
        )


def test_unit_claim_or_closed_data_cannot_select_production_initial_adoption(
    case: CurrentInitialCase,
) -> None:
    with pytest.raises(TypeError, match="Actual stage-admitted"):
        stage_initial_adoption_checks(
            case.original.plan,
            case.receipt.scope,
            case.original.reader,
            case.receipt.operation,
            case.records.controls,
        )
