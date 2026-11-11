"""The actual isolated fixed worker reads both records; no business grant."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.claim_reader import StorageClaimReader
from lab_generate_skill.adapters.storage.claim_transport import ClaimReadFailure
from lab_generate_skill.adapters.processes.capture import require_reaped
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.runtime.lifecycle import OperationGuards
from claim_fixtures import UnitClaimAuthority
from installed_claim_fixtures import setup
from stage_claim_reader_fixtures import declaration, write_fixture_claims
from test_run_journal import CancelSwitch
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing-parent",
        "corrupt-parent",
        "parent-lock",
        "wrong-child",
        "no-validation",
        "outer-revoked",
    ],
)
def test_installed_validation_read_keeps_parent_and_requires_current_authority(
    tmp_path: Path,
    installed_sources: InstalledFixture,
    case: str,
) -> None:
    scope, current, original = setup(tmp_path, installed_sources)
    command = declaration(current, original)
    write_fixture_claims(current, command)
    root = Path(command.root)
    parent = root / command.validation.parent.record.binding.key.filename
    child = root / command.validation.filename
    if case == "missing-parent":
        parent.unlink()
    elif case == "corrupt-parent":
        parent.write_bytes(b"{}")
    elif case == "parent-lock":
        parent.with_name(parent.name + ".lock").unlink()
    elif case == "wrong-child":
        child.write_bytes(
            current.model_copy(
                update={
                    "binding": current.binding.model_copy(
                        update={
                            "task": current.binding.task.model_copy(
                                update={"registration_id": "other"}
                            )
                        }
                    )
                }
            )
            .model_dump_json()
            .encode()
        )
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    authority = UnitClaimAuthority()
    authority.denied = case == "outer-revoked"
    reader = StorageClaimReader(
        root,
        scope,
        OperationGuards(SystemClock(), CancelSwitch()),
        authority,
        validation=None if case == "no-validation" else command.validation,
    )
    if case == "valid":
        for _ in range(2):
            assert (
                reader.read(current.binding.key, command.operation, control=guard(60))
                == current
            )
            observed = reader.last_execution
            assert observed is not None and observed.reply.worker != scope.writer
            assert (
                require_reaped(observed.capture).process_id
                == observed.reply.worker.process_id
            )
        assert authority.read_calls == 2 and authority.create_calls == 0
    elif case == "outer-revoked":
        with pytest.raises(OwnershipConflict) as outer_error:
            reader.read(current.binding.key, command.operation, control=guard(60))
        assert (
            hasattr(outer_error.value, "claim_read") and reader.last_execution is None
        )
        assert authority.read_calls == 1
    else:
        with pytest.raises(ClaimReadFailure) as read_error:
            reader.read(current.binding.key, command.operation, control=guard(60))
        assert read_error.value.capture is not None
        require_reaped(read_error.value.capture)
        assert reader.last_execution is None and authority.read_calls == 0
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before
