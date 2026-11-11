"""Read-only publication selection before storage activation; no CAS recursion.

Publication's mandatory authority establishes acceptance at switching time.
This gate verifies the selected immutable identities and rejects concurrent
changes; it neither inspects opaque acceptance bytes nor grants task execution.
"""

from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.domain.storage_launch import StorageLaunch
from lab_generate_skill.domain.storage_scope import check_storage_scope_operation
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.release_current import ReleaseCurrentReader


class StorageLaunchGate:
    def __init__(self, launch: StorageLaunch, current: ReleaseCurrentReader) -> None:
        self._launch = StorageLaunch.model_validate(launch)
        self._current = current

    def observe(
        self, operation: OperationContext, control: OperationControl
    ) -> ReleaseCurrentSnapshot:
        operation = check_storage_scope_operation(self._launch.scope, operation)
        control.checkpoint()
        observed: ReleaseCurrentSnapshot | None = None
        try:
            observed = ReleaseCurrentSnapshot.model_validate(
                self._current.read(operation, control=control)
            )
            control.checkpoint()
            if observed.deployment != self._launch.deployment:
                raise OwnershipConflict(
                    "Storage publication belongs to another deployment"
                )
            if (
                observed.revision != self._launch.revision
                or observed.active != self._launch.activation
            ):
                raise RevisionConflict(
                    "Storage publication differs from the selected revision"
                )
            return observed
        except BaseException as error:
            error.storage_publication_observed = observed  # type: ignore[attr-defined]
            raise

    def confirm(
        self,
        original: ReleaseCurrentSnapshot,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        original = ReleaseCurrentSnapshot.model_validate(original)
        observed = self.observe(operation, control)
        if observed != original:
            error = RevisionConflict(
                "Storage publication history changed during activation"
            )
            error.storage_publication_observed = observed  # type: ignore[attr-defined]
            raise error
