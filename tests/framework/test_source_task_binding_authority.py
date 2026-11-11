"""Original closed-source binding, with explicit synthetic physical premises."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from lab_generate_skill.adapters.plans.source_task_binding_authority import (
    OriginalSourceTaskBindingAuthority,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.errors import OwnershipConflict
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path


def test_closed_source_binding_exact_bytes_foreign_caller_and_current_consumer(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch) as (c, r):
        j, p = c.journals, c.p
        controls = p.original.resource.controls
        a = OriginalSourceTaskBindingAuthority(
            r.owner.authority, j.source_ref, j.source_reader.contexts, r.owner.evidence
        )
        bindings = EvidenceTaskBindings(r.owner.evidence, controls, a)
        op = p.plan.read_operation
        ref = p.plan.evaluation.task_contract_ref
        binding = bindings.load(ref, op)
        public, private, baseline = bindings.reader.dependencies(
            binding, controls.bind(op)
        )
        assert binding == r.owner.task
        for changed in (
            (
                binding.model_copy(update={"registration_id": "foreign-registration"}),
                public,
                private,
                baseline,
            ),
            (
                binding,
                public.model_copy(update={"goal": "foreign goal"}),
                private,
                baseline,
            ),
            (binding, public, private + b" ", baseline),
            (binding, public, private, baseline + b" "),
        ):
            with pytest.raises(OwnershipConflict):
                a.verify_binding(*changed, op, controls.bind(op))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(OwnershipConflict):
                pool.submit(bindings.load, ref, op).result()
        assert c.native.loader.session.calls == 0 and p.requests == []
        # Original execution source now consumes this real binding authority;
        # it must read its independent closed context without recursive calls.
        j.source_reader.bindings = bindings
        result = c.bundle.task.execute(p.plan.intent, p.plan.operation)
        assert result.evaluation.status == "success"
        assert c.bundle.finalization.state.reset is not None
        assert c.bundle.finalization.state.reset.status == "safe"
