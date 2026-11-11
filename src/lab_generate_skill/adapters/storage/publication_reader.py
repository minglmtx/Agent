"""Public read-only publication port backed exclusively by the fixed worker.

No current files or locks are touched in this parent. Actual process identity,
process creation and OS cleanup still need an outer hard-I/O supervisor; this
adapter does not claim interruption of uninterruptible kernel calls.
"""

from pathlib import Path
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.storage_scope import check_storage_scope_operation
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.adapters.processes.combined_control import CombinedControl
from .publication_protocol import PublicationReadCommand, check_publication_root
from .publication_transport import PublicationReadTransport, PublicationReadExecution


class StoragePublicationReader:
    def __init__(
        self, root: Path, launch: StorageLaunch, controls: OperationControls
    ) -> None:
        launch = StorageLaunch.model_validate(launch)
        if not isinstance(root, Path):
            raise ValueError("Publication root must be a Path")
        check_publication_root(str(root), launch.scope)
        self._root, self._launch, self._controls = root, launch, controls
        self._transport = PublicationReadTransport()
        self._last: PublicationReadExecution | None = None

    @property
    def last_execution(self) -> PublicationReadExecution | None:
        """Last confirmed read; failures retain their own capture, not this value."""
        return self._last

    def read(
        self, operation: OperationContext, *, control: OperationControl
    ) -> ReleaseCurrentSnapshot:
        operation = check_storage_scope_operation(self._launch.scope, operation)
        supervised = CombinedControl(control, self._controls.bind(operation))
        # Bind before the first caller poll and full request materialization, so
        # slow validation and a wall-clock rollback cannot extend this operation.
        supervised.checkpoint()
        command = PublicationReadCommand(
            scope=self._launch.scope,
            deployment=self._launch.deployment,
            root=str(self._root),
            operation=operation,
        )
        result = self._transport.execute(command, supervised)
        assert result.reply.snapshot is not None
        self._last = result
        return result.reply.snapshot
