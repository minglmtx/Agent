"""Engineering storage scope, explicit synthetic business permission only."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_termination import StorageProcessEnd
from lab_generate_skill.domain.evidence_sessions import check_evidence_cleanup
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    RegisteredStorageCommand,
)
from evidence_session_fixtures import binding, capacity
from evidence_worker_fixtures import command
from installed_source_fixtures import InstalledFixture
from storage_installation_fixtures import storage_installation


def request(
    root: Path,
    *,
    create: bool = False,
    reading: bool = False,
    installation: InstalledFixture | None = None,
) -> RegisteredStorageCommand:
    config = EvidenceStorageConfig(
        storage_id="store-1",
        evidence_root=str(root / "data"),
        session_root=str(root / "sessions"),
        max_object_bytes=1024,
        capacity=capacity(),
        installation=storage_installation(installation),
    )
    bound = binding().model_copy(
        update={
            "storage_config_sha256": config.sha256,
            "release_id": config.installation.manifest.release_id,
        }
    )
    op = OperationContext(
        operation_id="create" if create else "io",
        run_id=bound.owner.run_id,
        owner_id=bound.owner.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=90),
    )
    io = (
        None
        if create
        else command(
            root / "data", b"evidence", "read" if reading else "put"
        ).model_copy(update={"max_object_bytes": 1024})
    )
    return RegisteredStorageCommand(
        action="create" if create else "exchange",
        binding=bound,
        config=config,
        operation=op,
        controller=current_process_identity(),
        expected_revision=None if create else 0,
        io=io,
    )


class ExplicitAdmission:
    def __init__(self, expected: RegisteredStorageCommand) -> None:
        self.expected, self.calls = expected, 0

    def authorize_storage(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        assert binding == self.expected.binding and config == self.expected.config
        assert operation == self.expected.operation
        control.checkpoint()
        self.calls += 1

    def authorize_cleanup(
        self,
        binding: EvidenceSessionBinding,
        config: EvidenceStorageConfig,
        original: OperationContext,
        cleanup: OperationContext,
        ending: StorageProcessEnd | None,
        control: OperationControl,
    ) -> None:
        assert binding == self.expected.binding and config == self.expected.config
        assert original == self.expected.operation
        check_evidence_cleanup(original, cleanup)
        control.checkpoint()
        self.calls += 1


def roots(root: Path) -> None:
    (root / "data").mkdir()
    (root / "sessions").mkdir()
