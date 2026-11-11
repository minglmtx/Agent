"""Actual Slurm source caller; task/evidence are explicit metadata premises."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore
from state_contract_fixtures import scope as unit_scope
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard


def test_source_qualification_actual_caller_thread_attempt_and_sealed_cleanup() -> None:
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    old = unit_scope()
    selected = old.model_copy(
        update={"owner": old.owner.model_copy(update={"job_id": execution.job_id})}
    )
    evidence = Mock(spec=EvidenceStore)
    owner = OriginalSourceQualificationOwner(selected, execution, controller, evidence)
    from datetime import datetime, timezone, timedelta

    op = OperationContext(
        operation_id="source-owner-check",
        run_id=selected.owner.run_id,
        owner_id=selected.owner.owner_id,
        attempt_id=selected.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    owner.require(op, guard(30), new_work=True)
    for changed in (
        op.model_copy(update={"owner_id": "foreign"}),
        op.model_copy(update={"attempt_id": "foreign"}),
    ):
        with pytest.raises(OwnershipConflict):
            owner.require(changed, guard(30), new_work=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(owner.require_caller, op, guard(30)).result()
    owner.seal(op, guard(30))
    with pytest.raises(OwnershipConflict):
        owner.require(op, guard(30), new_work=True)
    owner.require(
        op.cleanup("source-owner-cleanup", now=op.deadline, seconds=30),
        guard(30),
        new_work=False,
    )
    assert evidence.mock_calls == []
