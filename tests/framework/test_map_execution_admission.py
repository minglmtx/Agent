"""Assembly on explicit synthetic closed-source/physical premises, no new scope."""

from pathlib import Path
from typing import Any, cast
from types import SimpleNamespace
import pytest
from lab_generate_skill.bootstrap.map_execution_admission import (
    admit_map_execution_source,
)
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.bootstrap.map_execution_admission as module
import lab_generate_skill.bootstrap.execution_source_admission as admission


def test_admission_reuses_original_persistent_claim_and_rejects_revocation(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        j, p = c.journals, c.p
        run = j.plans.load(r.owner.run, p.plan.read_operation)
        original_claim_bytes = tuple(
            (f.name, f.read_bytes()) for f in sorted(j.claims._root.glob("*.json"))
        )

        class Caller(OriginalExecutionClaimAuthority):
            def __init__(
                self,
                scope: str,
                binding: Any,
                task: Any,
                execution: Any,
                controller: Any,
                **kwargs: Any,
            ) -> None:
                assert (scope, binding, task, execution, controller) == (
                    j.claims._scope,
                    r.owner.run,
                    r.owner.task,
                    r.owner.authority.execution,
                    r.owner.authority.controller,
                )
                self.run, self.task = binding, task
                self.contexts = kwargs["contexts"]

            def require_caller(self, op: OperationContext) -> None:
                r.owner.authority.require_caller(op)

            def authorize_create(
                self, binding: SourceClaimBinding, plan: RunPlan, op: OperationContext
            ) -> None:
                pytest.fail("Existing original claim may not be recreated")

            def verify_owner(
                self, record: SourceClaimRecord, op: OperationContext
            ) -> None:
                self.require_caller(op)
                j.claim_authority.verify_owner(record, op)

        def closed(*args: Any, **kwargs: Any) -> Any:
            return j.source_reader.contexts

        monkeypatch.setattr(admission, "OriginalExecutionClaimAuthority", Caller)
        monkeypatch.setattr(module, "closed_map_source_contexts", closed)

        def admit(value: RunPlan = run) -> Any:
            return admit_map_execution_source(
                value,
                r.owner.run,
                cast(Any, SimpleNamespace(context_ref=j.source_ref)),
                r.owner.authority.execution,
                r.owner.authority.controller,
                p.plan.read_operation.model_copy(
                    update={"operation_id": "original-admission"}
                ),
                claim_root=j.claims._root,
                claim_scope=j.claims._scope,
                evidence=r.owner.evidence,
                controls=p.original.resource.controls,
            )

        with pytest.raises(OwnershipConflict):
            admit(run.model_copy(update={"purpose": "evaluation"}))
        admitted = admit()
        assert admitted.claim.reference == r.owner.claim_ref
        assert admitted.published.source_ref == p.plan.source_ref
        assert admit().claim == admitted.claim
        assert original_claim_bytes == tuple(
            (f.name, f.read_bytes()) for f in sorted(j.claims._root.glob("*.json"))
        )
        j.claim_authority.denied = True
        with pytest.raises(OwnershipConflict):
            admit()
        j.claim_authority.denied = False
        assert p.requests == [] and c.native.loader.session.calls == 0
        # Use this assembled immutable source on the already existing consumer.
        # Actual Slurm claim ownership remains independently checked by its
        # original supplier tests; these premises do not qualify a real task.
        old = j.source_reader
        old.plans, old.claims, old.contexts, old.bindings = (
            admitted.plans,
            admitted.claims,
            admitted.contexts,
            admitted.bindings,
        )
        result = c.bundle.task.execute(p.plan.intent, p.plan.operation)
        assert result.evaluation.status == "success"
