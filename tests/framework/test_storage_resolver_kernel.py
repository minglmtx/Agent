"""A missing proc component is not absence; never signal a reused original PID."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.processes.worker_identity import (
    current_evidence_worker,
)
from lab_generate_skill.adapters.storage.resolver_authority import (
    StorageResolverAuthority,
)
from lab_generate_skill.adapters.storage.observed_inspection import (
    ObservedStorageInspection,
)
from evidence_session_fixtures import intent
from test_storage_resolver_protocol import resolution
from test_slurm_commands import guard


def test_actual_live_incarnation_rejected_and_prior_incarnation_not_signalled(
    tmp_path: Path,
) -> None:
    cmd = resolution(tmp_path)
    assert cmd.original.io is not None
    worker = current_evidence_worker()
    authority = StorageResolverAuthority(
        cmd, worker, -1, guard(10), ObservedStorageInspection(cmd.original.io)
    )
    original = intent().model_copy(update={"worker": worker})
    with pytest.raises(OwnershipConflict, match="still exists"):
        authority._original_ended(original)
    old = original.model_copy(
        update={
            "worker": worker.model_copy(update={"start_ticks": worker.start_ticks - 1})
        }
    )
    authority._original_ended(old)
    # Without a durable intent there is no original start_ticks. A live PID,
    # including a possible reused incarnation, must therefore be refused.
    with pytest.raises(OwnershipConflict, match="still exists"):
        authority._process_ended(worker.process_id, None)


@pytest.mark.parametrize(
    "fault", ["missing_component", "absent_pid", "permission", "wrong_boot"]
)
def test_missing_subfile_or_denial_is_not_termination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    cmd = resolution(tmp_path)
    assert cmd.original.io is not None
    worker = current_evidence_worker()
    authority = StorageResolverAuthority(
        cmd, worker, -1, guard(10), ObservedStorageInspection(cmd.original.io)
    )
    original = intent().model_copy(update={"worker": worker})
    if fault == "absent_pid":
        original = original.model_copy(
            update={"worker": worker.model_copy(update={"process_id": 2147483647})}
        )
    elif fault == "wrong_boot":
        original = original.model_copy(
            update={"worker": worker.model_copy(update={"boot_id": "other-boot"})}
        )
    calls = []

    def missing(*args: object, **kwargs: object) -> None:
        calls.append(1)
        if fault == "permission":
            raise PermissionError("kernel unreadable")
        raise FileNotFoundError("component missing")

    monkeypatch.setattr(
        "lab_generate_skill.adapters.storage.resolver_authority.read_process_identity",
        missing,
    )
    if fault == "absent_pid":
        authority._original_ended(original)
    else:
        with pytest.raises(
            PermissionError if fault == "permission" else OwnershipConflict
        ):
            authority._original_ended(original)
    assert len(calls) == (0 if fault == "wrong_boot" else 1)
