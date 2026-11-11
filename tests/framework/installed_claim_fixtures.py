"""Actual installed leaf fixtures; record creation here is engineering-only."""

from pathlib import Path
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.adapters.storage.claim_protocol import ClaimReadCommand
from installed_source_fixtures import InstalledFixture
from installed_publication_fixtures import setup as publication_setup
from storage_scope_fixtures import scope as original_scope
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.plans.claim_evidence import MAX_CLAIM_BYTES
from test_slurm_commands import guard


def setup(
    root: Path, installed: InstalledFixture
) -> tuple[StorageScope, SourceClaimRecord, ClaimReadCommand]:
    launch, _, original = publication_setup(root, installed)
    prototype = original_scope(source=True).claim
    assert prototype is not None
    claim = SourceClaimBinding(
        scope_id=prototype.scope_id, run=launch.scope.run, task=prototype.task
    )
    scope = StorageScope.model_validate(
        launch.scope.model_copy(
            update={
                "claim": claim,
                "binding": launch.scope.binding.model_copy(
                    update={
                        "scope": "source",
                        "source_task_id": claim.task.identity.source_task_id,
                    }
                ),
            }
        )
    )
    directory = root / "claims"
    directory.mkdir()
    record = SourceClaimRecord(binding=claim, operation=original.operation)
    with AtomicSnapshotFile(
        directory, claim.key.filename, max_bytes=MAX_CLAIM_BYTES
    ).locked(guard(30)) as transaction:
        transaction.write(record.model_dump_json().encode())
    return (
        scope,
        record,
        ClaimReadCommand(
            scope=scope, root=str(directory), operation=original.operation
        ),
    )
