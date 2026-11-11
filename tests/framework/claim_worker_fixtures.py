"""Synthetic scoped claim read packets; installation facts are test fixtures."""

import hashlib
from pathlib import Path
from lab_generate_skill.domain.claims import SourceClaimBinding, SourceClaimRecord
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.adapters.storage.claim_protocol import (
    ClaimReadCommand,
    ClaimReadReply,
    encode_claim_command,
    encode_claim_reply,
    ENTRY,
)
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from publication_worker_fixtures import (
    inputs as publication_inputs,
    reply as publication_reply,
)
from storage_scope_fixtures import scope as original_scope


def inputs(root: Path) -> tuple[StorageScope, SourceClaimRecord, ClaimReadCommand]:
    launch, snapshot, original = publication_inputs(root, entry=ENTRY)
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
    command = ClaimReadCommand(
        scope=scope, root=str(root / "claims"), operation=original.operation
    )
    record = SourceClaimRecord(binding=claim, operation=original.operation)
    return scope, record, command


def reply(command: ClaimReadCommand, record: SourceClaimRecord) -> ClaimReadReply:
    _, snapshot, original = publication_inputs(
        Path(command.scope.workspace_root), entry=ENTRY
    )
    observed = publication_reply(original, snapshot, entry=ENTRY)
    return ClaimReadReply(
        command_sha256=hashlib.sha256(encode_claim_command(command)).hexdigest(),
        worker=observed.worker,
        phase="completion",
        error=None,
        installed_sources=observed.installed_sources,
        membership=observed.membership,
        record=record,
    )


def capture(command: ClaimReadCommand, record: SourceClaimRecord) -> CommandCapture:
    observed = reply(command, record)
    return CommandCapture(
        (command.scope.config.installation.python_executable, "-I", "-B", "-m", ENTRY),
        0,
        encode_claim_reply(observed),
        b"",
        True,
        ProcessTermination(observed.worker.process_id, "reaped", 0, False),
    )
