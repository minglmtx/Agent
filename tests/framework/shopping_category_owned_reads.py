"""Synchronous unit transport of real category producer bytes, never live authority."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from lab_generate_skill.ports.contexts import ContextFactReads
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    ClosedSourceBindingBodies,
)
from lab_generate_skill.adapters.plans.task_bindings import TaskBindingEvidenceReader
from lab_generate_skill.adapters.plans.qualified_binding_facts import (
    require_qualified_binding_facts,
)
from lab_generate_skill.adapters.plans.evidence import check_run_plan_input_evidence
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.claim_evidence import ClaimEvidence
from lab_generate_skill.domain.claims import SourceClaimReceipt
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.bootstrap.closed_map_source_read import (
    read_execution_source_facts,
)


class CategoryUnitRead(ClosedSourceReadTransport):
    def __init__(self, source: Any, root: Path, operation: Any) -> None:
        self.source, self.root, self.operation = source, root, operation
        self.store = source.site.evidence
        self.calls = 0
        self.read_operation = operation.cleanup(
            operation.operation_id + ".unit-category-read",
            now=source.site.clock.utcnow(),
            seconds=120,
        )

    def require_current(self, material: Any, operation: Any) -> None:
        owner = self.source.owner
        assert material.site.token.owner == owner.scope.owner
        assert material.site.slurm.execution == owner.execution
        assert material.site.slurm.parent == owner.controller
        assert operation.run_id == owner.scope.owner.run_id

    def check_current(self, control: Any) -> None:
        control.checkpoint()

    def read(
        self,
        material: Any,
        control: Any,
        *,
        binding: Any = None,
        publication: Any = None,
        plan_inputs: Any = None,
        binding_reference: Any = None,
        execution_plan: Any = None,
        **additional_reads: Any,
    ) -> Any:
        self.calls += 1
        evidence = ReadOnlyEvidence(
            self.root, max_object_bytes=64 * 1024**2, proposed=publication
        )
        read, source = self.read_operation, self.source
        contexts = bind_closed_source_read(material).contexts(
            evidence, source.site.controls, read
        )
        assert not set(additional_reads) - {"context_inputs", "baseline_read"}
        if additional_reads.get("context_inputs", False):
            assert isinstance(contexts, ContextFactReads)
            result, inputs = contexts.load_context_inputs(material.context_ref, read)
            self.last_reply = cast(Any, SimpleNamespace(context_inputs=inputs))
        elif additional_reads.get("baseline_read") is not None:
            from lab_generate_skill.adapters.plans.baseline_read import (
                read_baseline_inputs,
            )

            bodies = read_baseline_inputs(
                additional_reads["baseline_read"],
                material,
                contexts,
                evidence,
                control,
                read,
            )
            result = contexts.load_context(material.context_ref, read)
            self.last_reply = cast(Any, SimpleNamespace(baseline_bodies=bodies))
        else:
            result = contexts.load_context(material.context_ref, read)
        if binding is not None:
            require_qualified_binding_facts(
                material.context_ref,
                contexts,
                evidence,
                source.owner.scope.owner,
                binding.binding,
                binding.public_task,
                binding.private_spec_json.encode(),
                binding.baseline_json.encode(),
                read,
                control,
            )
        if binding_reference is not None:
            tasks = TaskBindingEvidenceReader(evidence)
            task = tasks.load(binding_reference, control)
            public, public_raw, private, baseline = tasks.dependencies_with_bodies(
                task, control
            )
            require_qualified_binding_facts(
                material.context_ref,
                contexts,
                evidence,
                source.owner.scope.owner,
                task,
                public,
                private,
                baseline,
                read,
                control,
            )
            self.last_reply = cast(
                Any,
                SimpleNamespace(
                    binding=task,
                    binding_reference=binding_reference,
                    binding_bodies=ClosedSourceBindingBodies(
                        binding=task,
                        public_task_json=public_raw.decode(),
                        private_spec_json=private.decode(),
                        baseline_json=baseline.decode(),
                    ),
                ),
            )
        if execution_plan is not None:
            facts = read_execution_source_facts(
                execution_plan,
                material,
                evidence,
                source.site.controls,
                contexts,
                read,
                result,
                control,
            )
            ref = facts.source.intent.binding.claim_ref
            claim = ClaimEvidence(
                evidence, EvidenceRunPlans(evidence, source.site.controls)
            ).load(ref, control)
            self.last_reply = cast(
                Any,
                SimpleNamespace(
                    execution_source=facts,
                    execution_claim=SourceClaimReceipt(record=claim, reference=ref),
                ),
            )
        if plan_inputs is not None:
            check_run_plan_input_evidence(plan_inputs, evidence, control)
        return result
