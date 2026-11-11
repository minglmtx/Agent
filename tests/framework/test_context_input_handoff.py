"""Original CAS producer to actual context consumer; authority doubles explicit."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
import json
import os
import pytest
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.plans.context_evidence import ContextEvidenceReader
from lab_generate_skill.adapters.plans.task_context_read import (
    OriginalSourceContextRead,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.ports.contexts import ContextInputRead
from lab_generate_skill.ports.lifecycle import OperationControl
from context_storage_fixtures import fixture
from test_run_journal import command


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "reference",
        "body",
        "permission",
        "storage",
        "cancel",
        "final",
        "partial",
    ],
)
def test_real_context_graph_handoff_and_original_gates(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    op = command("context-input-handoff", attempt="candidate")
    bounded = c.adapter.controls.bind(op)
    source = c.inputs.source

    class UnitOwner:
        calls = 0

        def caller(
            self, operation: OperationContext, control: OperationControl
        ) -> None:
            assert operation == op
            control.checkpoint()
            self.calls += 1
            if fault == "permission" and self.calls == 2:
                raise OwnershipConflict("Current original caller revoked")

    class UnitFixedProof:
        """Emulates only worker transport; actual graph/authority algorithm used."""

        loads = 0
        current = 0

        def load_context_inputs(
            self, reference: EvidenceRef, operation: OperationContext
        ) -> tuple[PublicContextReceipt, PublicContextInputs]:
            assert reference == c.inputs.source_ref and operation == op
            self.loads += 1
            receipt, inputs = c.adapter.load_context_inputs(reference, operation)
            if fault == "reference" or (fault == "final" and self.loads == 2):
                inputs = inputs.model_copy(
                    update={
                        "context_ref": inputs.context_ref.model_copy(
                            update={"producer": "other-producer"}
                        )
                    }
                )
            elif fault == "body":
                inputs = inputs.model_copy(
                    update={
                        "context": inputs.context.model_copy(
                            update={
                                "task": inputs.context.task.model_copy(
                                    update={"goal": "changed"}
                                )
                            }
                        )
                    }
                )
            return receipt, inputs

        def check_context_current(
            self, operation: OperationContext, control: OperationControl
        ) -> None:
            assert operation == op
            control.checkpoint()
            self.current += 1
            if fault == "storage" and self.current == 2:
                raise PermissionError("Original storage admission revoked")
            if fault == "cancel" and self.current == 2:
                raise OperationStopped("CANCELLED", op.operation_id)
            if fault == "partial" and self.current == 3:
                raise OSError("Original final storage check failed")

    owner, fixed = UnitOwner(), UnitFixedProof()
    held: list[OriginalSourceContextRead] = []

    class UnitProvider:
        def read_inputs(
            self,
            receipt: PublicContextReceipt,
            operation: OperationContext,
            control: OperationControl,
        ) -> ContextInputRead:
            actual, inputs = fixed.load_context_inputs(c.inputs.source_ref, operation)
            assert actual == receipt
            value = OriginalSourceContextRead(
                cast(ClaimedRunResourceOwner, owner),
                fixed,
                c.inputs.source_ref,
                receipt,
                inputs,
                operation,
                control,
            )
            held.append(value)
            return value

    # Actual parent consumer must not remotely read any dependency again.
    class NoParentLeafReads:
        def read(
            self, reference: EvidenceRef, control: OperationControl | None = None
        ) -> bytes:
            pytest.fail("Verified graph was reread per leaf in parent")

    reader = ContextEvidenceReader(
        NoParentLeafReads(), c.authority, input_reads=UnitProvider()
    )
    if fault == "none":
        for _ in range(2):
            assert reader.context(source, op, bounded) == c.inputs.source_inputs
        assert fixed.loads == 4 and fixed.current == 6 and owner.calls == 8
        if output := os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
            (Path(output) / "context-input-read-counts.json").write_text(
                json.dumps(
                    {
                        "fixture_only": True,
                        "whole_graph_proofs_per_call": 2,
                        "fresh_current_storage_gates": 3,
                        "parent_dependency_reads": 0,
                        "original_three_semantic_gates": True,
                        "final_full_proof": True,
                    }
                )
            )
    else:
        with pytest.raises(
            (OwnershipConflict, PermissionError, OperationStopped, OSError, ValueError)
        ):
            reader.context(source, op, bounded)
    assert held
    for read in held:
        with pytest.raises(OwnershipConflict, match="call/thread"):
            _ = read.inputs
        with pytest.raises(OwnershipConflict):
            read.verify_context(c.inputs.source_inputs, source, op)


def test_transient_context_read_rejects_foreign_thread_scope_and_order(
    tmp_path: Path,
) -> None:
    c = fixture(tmp_path)
    op = command("context-input-boundary", attempt="candidate")
    control = c.adapter.controls.bind(op)

    class UnitOwner:
        def caller(self, op: OperationContext, control: OperationControl) -> None:
            control.checkpoint()

    class UnitSource:
        def load_context_inputs(
            self, reference: EvidenceRef, op: OperationContext
        ) -> tuple[PublicContextReceipt, PublicContextInputs]:
            return c.adapter.load_context_inputs(reference, op)

        def check_context_current(
            self, op: OperationContext, control: OperationControl
        ) -> None:
            control.checkpoint()

    read = OriginalSourceContextRead(
        cast(ClaimedRunResourceOwner, UnitOwner()),
        UnitSource(),
        c.inputs.source_ref,
        c.inputs.source,
        c.inputs.source_inputs,
        op,
        control,
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(lambda: read.inputs).result()
        with pytest.raises(OwnershipConflict, match="operation/order"):
            read.verify_reset(
                c.inputs.source_inputs.reset_inputs, c.inputs.source_inputs.reset, op
            )
        with pytest.raises(OwnershipConflict):
            read.verify_baseline(
                c.inputs.source_inputs.baseline_inputs,
                c.inputs.source_inputs.baseline,
                op.model_copy(update={"attempt_id": "other"}),
            )
        assert read.inputs == c.inputs.source_inputs
    finally:
        read.close()
