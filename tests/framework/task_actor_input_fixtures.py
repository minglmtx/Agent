"""Explicit fixed source transport premise over the real retained unit graph.

Only transport/current-storage edges are synthetic. Claim and run journals,
source adapter, resource owners, task lifecycle and Actor constructors are real.
"""

from typing import Any
from types import SimpleNamespace
import pytest
from lab_generate_skill.domain.execution_task_source import ClaimedExecutionSourceFacts
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.domain.errors import OwnershipConflict


def fixed_task_source_inputs(c: Any, r: Any, patch: pytest.MonkeyPatch) -> Any:
    source = c.journals.source_reader
    op = c.p.plan.read_operation
    control = c.p.original.resource.controls.bind(op)
    original = source.load(c.p.plan, op, control)
    record = source.claims.require_source(
        c.p.plan.intent.binding.claim_ref, original.source.run, original.source.task, op
    )
    facts = ClaimedExecutionSourceFacts(
        **vars(original),
        claim=SourceClaimReceipt(
            record=record, reference=c.p.plan.intent.binding.claim_ref
        ),
    )
    state = SimpleNamespace(denied=False, current_calls=0, loads=0)

    def current(operation: Any, bounded: Any) -> None:
        bounded.checkpoint()
        state.current_calls += 1
        if state.denied:
            raise OwnershipConflict("Original unit storage authority revoked")

    class Fixed:
        def load_source(self, plan: Any, operation: Any, bounded: Any) -> Any:
            state.loads += 1
            self.verify_current(plan, facts, operation, bounded)
            return facts

        def verify_current(
            self, plan: Any, value: Any, operation: Any, bounded: Any
        ) -> None:
            assert plan == c.p.plan and value == facts
            current(operation, bounded)

    patch.setattr(source, "source_checks", Fixed())
    patch.setattr(source.contexts, "check_context_current", current)
    patch.setattr(r.owner, "source_run_reads", r.owner.sources)
    import lab_generate_skill.adapters.sites.task_resource_owner as resources

    original_observe = getattr(resources, "observe_process_cgroup")

    def observe(execution: Any, worker: Any, bounded: Any) -> Any:
        bounded.checkpoint()
        held = r.inputs
        if held is not None and held.browser_acquired is not None:
            acquired = held.browser_acquired[1].details.prepared
            if worker == acquired.owner_guard.worker:
                return SimpleNamespace(
                    membership=acquired.step.controller.target.worker
                )
        return original_observe(execution, worker, bounded)

    patch.setattr(resources, "observe_process_cgroup", observe)
    if r.inputs is not None:
        from lab_generate_skill.adapters.sites.task_preparation_inputs import (
            TaskPreparationDeclarationInputs,
        )

        assert c.bundle.preparation.declared_inputs is None
        declared = TaskPreparationDeclarationInputs(
            c.p.plan, c.p.declaration, r.inputs, source.contexts
        )
        r.inputs.preparation_declarations = declared
        c.bundle.preparation.bind_declared_inputs(declared)
    return state
