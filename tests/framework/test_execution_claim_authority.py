"""Actual Slurm caller/owner checks with explicitly synthetic source facts only.

No website, model, Actor, paid calls or production source/claim is admitted.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, cast
import pytest
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.ledger.claims import FileSourceClaims
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_resource import SiteResourceSpec, SiteSlurmBinding
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_scope import StateScope
from execution_task_source_fixtures import source_case
from site_worker_fixtures import configuration
import state_contract_fixtures as states
from test_linux_cgroups import actual_slurm_execution
from test_run_journal import command
from test_slurm_commands import guard


def test_original_execution_claim_owner_actual_kernel_and_frozen_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    original_scope = states.scope

    def scope() -> StateScope:
        old = original_scope()
        return old.model_copy(
            update={"owner": old.owner.model_copy(update={"job_id": execution.job_id})}
        )

    monkeypatch.setattr(states, "scope", scope)
    spec = SiteResourceSpec(
        configuration=configuration(job_id=execution.job_id),
        slurm=SiteSlurmBinding(
            execution=execution,
            parent=controller,
            srun_executable="/usr/bin/srun",
            scontrol_executable="/usr/bin/scontrol",
        ),
    )
    original_checks = states.checks

    def checks(required: tuple[str, ...]) -> StateChecks:
        old = original_checks(required)
        reference = cast(
            Callable[[object, str], EvidenceRef], getattr(states, "reference")
        )
        ref = reference(spec, spec.schema_version)
        return old.model_copy(
            update={
                "checks": tuple(
                    c.model_copy(update={"evidence": (*c.evidence, ref)})
                    for c in old.checks
                )
            }
        )

    monkeypatch.setattr(states, "checks", checks)
    c = source_case(tmp_path / "source")
    bound, task = c.binding.run, c.run.tasks[0]
    controls = c.data.adapter.controls
    a = OriginalExecutionClaimAuthority(
        "unit-single",
        bound,
        task,
        execution,
        controller,
        evidence=c.data.store,
        plans=c.plans,
        contexts=c.data.adapter,
        controls=controls,
    )
    binding = SourceClaimBinding(scope_id="unit-single", run=bound, task=task)
    op = command("actual-owner-claim")
    a.authorize_create(binding, c.run, op)
    # Reopen the same fixture claim/root with the actual-owner supplier. A replay
    # only recovers its existing immutable receipt, never another task dispatch.
    ledger = FileSourceClaims(
        tmp_path / "source/claims", "unit-single", controls, c.data.store, c.plans, a
    )
    receipt = ledger.claim(binding, op)
    assert receipt.reference == c.binding.claim_ref
    assert ledger.claim(binding, op) == receipt
    with pytest.raises(OwnershipConflict):
        a.authorize_create(binding.model_copy(update={"scope_id": "other"}), c.run, op)
    with pytest.raises(OwnershipConflict):
        a.authorize_create(
            binding, c.run, op.cleanup("not-create", now=op.deadline, seconds=30)
        )
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(a.verify_owner, receipt.record, op).result()
    with pytest.raises(OwnershipConflict):
        changed = controller.model_copy(
            update={
                "writer": controller.writer.model_copy(
                    update={"start_ticks": controller.writer.start_ticks + 1}
                )
            }
        )
        wrong = OriginalExecutionClaimAuthority(
            "unit-single",
            bound,
            task,
            execution,
            changed,
            evidence=c.data.store,
            plans=c.plans,
            contexts=c.data.adapter,
            controls=controls,
        )
        wrong.verify_owner(receipt.record, op)
    c.data.authority.denied_context = True
    with pytest.raises(OwnershipConflict):
        a.authorize_create(binding, c.run, op)
    # Original cleanup/ownership reads stay possible after new source permission
    # is revoked; no source requalification or external work occurs on this read.
    a.verify_owner(
        receipt.record, op.cleanup("owner-cleanup", now=op.deadline, seconds=30)
    )
    for invalid in ("", None):
        value: Any = invalid
        with pytest.raises((TypeError, ValueError)):
            OriginalExecutionClaimAuthority(
                value,
                bound,
                task,
                execution,
                controller,
                evidence=c.data.store,
                plans=c.plans,
                contexts=c.data.adapter,
                controls=controls,
            )
