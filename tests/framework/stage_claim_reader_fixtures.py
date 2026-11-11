"""Synthetic parent/current claim material, never production authorization."""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.claims import SourceClaimRecord, SourceClaimReceipt
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.source_stage_validation import SourceStageValidation
from lab_generate_skill.adapters.storage.claim_protocol import (
    ClaimReadCommand,
    StageValidationClaimReadCommand,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import AtomicSnapshotFile
from lab_generate_skill.adapters.plans.claim_evidence import MAX_CLAIM_BYTES
from test_run_plan import reference
from test_slurm_commands import guard


def declaration(
    current: SourceClaimRecord, command: ClaimReadCommand
) -> StageValidationClaimReadCommand:
    parent_run = current.binding.run.model_copy(
        update={
            "owner": current.binding.run.owner.model_copy(
                update={
                    "run_id": "parent-run",
                    "job_id": "parent-job",
                    "owner_id": "parent-owner",
                }
            ),
            "release_ref": reference("release-manifest/1"),
        }
    )
    parent = SourceClaimRecord(
        binding=current.binding.model_copy(update={"run": parent_run}),
        operation=current.operation.model_copy(
            update={"run_id": "parent-run", "owner_id": "parent-owner"}
        ),
    )
    raw = parent.model_dump_json().encode()
    digest = hashlib.sha256(raw).hexdigest()
    receipt = SourceClaimReceipt(
        record=parent,
        reference=EvidenceRef(
            uri="cas://sha256/" + digest,
            sha256=digest,
            size_bytes=len(raw),
            media_type="application/json",
            content_schema="source-claim/1",
            visibility="private",
            producer="unit-stage-reader",
        ),
    )
    validation = SourceStageValidation(
        parent=receipt,
        target_release_ref=current.binding.run.release_ref,
        authorization_ref=reference("task-stage-validation-authorization/1"),
    )
    return StageValidationClaimReadCommand(
        scope=command.scope,
        root=command.root,
        operation=command.operation,
        validation=validation,
    )


def write_fixture_claims(
    current: SourceClaimRecord, command: StageValidationClaimReadCommand
) -> None:
    root = Path(command.root)
    # Fixture setup only: neither record was issued by a real execution authority.
    for filename, record in (
        (
            command.validation.parent.record.binding.key.filename,
            command.validation.parent.record,
        ),
        (command.validation.filename, current),
    ):
        with AtomicSnapshotFile(root, filename, max_bytes=MAX_CLAIM_BYTES).locked(
            guard(30)
        ) as transaction:
            transaction.write(record.model_dump_json().encode())
