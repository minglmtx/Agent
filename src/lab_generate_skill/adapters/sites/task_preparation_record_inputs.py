"""One task's exact preparation graph and accurate publication readback.

Only passing pure checks of exact inputs are retained with their checker identity.
Current source/storage permission and authority are checked on every consumption.
"""

from collections.abc import Callable
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
    PreparationInputs,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.contexts import ContextCurrentChecks
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.preparation_record_inputs import (
    LoadedPreparation,
    PreparationRecordScope,
)
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes


class TaskPreparationRecordInputs:
    def __init__(
        self, held: PreparationRecordScope, current: ContextCurrentChecks
    ) -> None:
        self.held, self.current = held, current
        self.graph: LoadedPreparation | None = None
        self.publication: tuple[PreparedPublication, tuple[bytes, bytes]] | None = None
        self.expected_publication: PreparedPublication | None = None
        self.checked: tuple[object, PreparationInputs, StateChecks] | None = None
        self.statistics = {
            name: 0
            for name in (
                "preparation_graph_reads",
                "preparation_graph_reuses",
                "publication_reads",
                "publication_reuses",
                "checks_executed",
                "checks_reused",
            )
        }

    def _check(self, op: OperationContext, control: OperationControl) -> None:
        self.held.check(op, control)
        self.current.check_context_current(op, control)
        self.held.check(op, control)

    def preparation_inputs(
        self,
        selection: PreparationSelection,
        op: OperationContext,
        control: OperationControl,
        read: Callable[[], LoadedPreparation],
    ) -> LoadedPreparation:
        self._check(op, control)
        value = self.graph
        if value is None:
            value = read()
            self.statistics["preparation_graph_reads"] += 1
        else:
            self.statistics["preparation_graph_reuses"] += 1
        inputs = value.inputs
        if value.private_spec is not None:
            require_complete_bytes(inputs.binding.private_spec_ref, value.private_spec)
        if value.snapshot is not None:
            if inputs.request.snapshot_ref is None:
                raise OwnershipConflict("Preparation snapshot lost original reference")
            require_complete_bytes(inputs.request.snapshot_ref, value.snapshot)
        original = inputs.request.operation
        if (
            inputs.selection != selection
            or inputs.binding.identity != self.held.task_identity
            or (original.run_id, original.owner_id, original.attempt_id)
            != self.held.preparation_scope
            or not (
                op == original
                or (
                    op.mode == "cleanup"
                    and op.parent_operation_id == original.operation_id
                    and (op.allocation_id, op.recovery_ref)
                    == (original.allocation_id, original.recovery_ref)
                )
            )
        ):
            raise OwnershipConflict("Preparation bodies changed original task/read")
        self._check(op, control)
        self.graph = value
        return value

    def publication_inputs(
        self,
        publication: PreparedPublication,
        op: OperationContext,
        control: OperationControl,
        read: Callable[[], tuple[bytes, bytes]],
    ) -> tuple[bytes, bytes]:
        self._check(op, control)
        if (
            self.expected_publication is not None
            and publication != self.expected_publication
        ):
            raise OwnershipConflict(
                "Source publication changed original complete references"
            )
        if self.graph is None or self.graph.inputs.selection != publication.selection:
            raise OwnershipConflict("Publication needs its exact original preparation")
        if self.publication is None:
            raw = read()
            self.statistics["publication_reads"] += 1
        else:
            selected, raw = self.publication
            if selected != publication:
                raise OwnershipConflict(
                    "Preparation publication changed complete references"
                )
            self.statistics["publication_reuses"] += 1
        for ref, body in zip(
            (publication.preparation_ref, publication.prepared_ref), raw, strict=True
        ):
            require_complete_bytes(ref, body)
        self._check(op, control)
        self.publication = publication, raw
        return raw

    def expect_publication(self, publication: PreparedPublication) -> None:
        publication = PreparedPublication.model_validate(publication)
        if (
            self.graph is None
            or self.graph.inputs.selection != publication.selection
            or self.expected_publication not in (None, publication)
        ):
            raise OwnershipConflict("Source publication lost its original preparation")
        # Exact producer references only: bodies must still be read accurately.
        self.expected_publication = publication

    def preparation_checks(
        self,
        inputs: PreparationInputs,
        checker: object,
        op: OperationContext,
        control: OperationControl,
        check: Callable[[], StateChecks],
    ) -> StateChecks:
        self._check(op, control)
        inputs = PreparationInputs.model_validate(inputs)
        if self.graph is None or inputs != self.graph.inputs:
            raise OwnershipConflict(
                "Preparation checks changed original verified inputs"
            )
        previous = self.checked
        if previous is not None and previous[0] is checker and previous[1] == inputs:
            checks = StateChecks.model_validate(previous[2])
            self.statistics["checks_reused"] += 1
        else:
            checks = StateChecks.model_validate(check())
            self.statistics["checks_executed"] += 1
        if checks.required != inputs.spec.preparation_checks:
            raise OwnershipConflict("Preparation checks narrowed original coverage")
        self._check(op, control)
        if checks.status == "pass":
            self.checked = checker, inputs, checks
        return checks

    def clear(self) -> None:
        self.graph = self.publication = None
        self.expected_publication = None
        self.checked = None
