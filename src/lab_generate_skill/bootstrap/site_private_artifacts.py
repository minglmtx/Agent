"""Only trusted bootstrap chooses original worker/controller private storage roles."""

from typing import Literal
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.storage_admission import (
    OriginalSiteStorageAdmission,
)
from lab_generate_skill.adapters.sites.storage_original import (
    OriginalSiteAcquisitionReader,
)
from lab_generate_skill.adapters.sites.private_artifacts import (
    OriginalSitePrivateArtifacts,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.lifecycle import OperationContext
from .evidence_store import assemble_evidence_store


class _IndependentCleanupControls:
    def bind(self, operation: OperationContext) -> OperationControl:
        # The resolver cleanup operation was already derived/validated against
        # its original physical operation. Its own finite deadline is separate.
        from datetime import datetime, timezone

        operation = OperationContext.model_validate(operation)
        if (
            operation.mode != "cleanup"
            or operation.parent_operation_id is None
            or operation.cancellation_ref is not None
        ):
            raise ValueError(
                "Private storage requires independent linked cleanup operation"
            )
        seconds = (operation.deadline - datetime.now(timezone.utc)).total_seconds()
        return DeadlineControl(seconds, operation.operation_id)


def build_site_private_artifacts(
    configuration: SiteWorkerConfiguration,
    participant: Literal["worker", "controller"],
    worker_guard: SiteWorkerGuard | None,
    control: OperationControl,
) -> OriginalSitePrivateArtifacts:
    configuration = SiteWorkerConfiguration.model_validate(configuration)
    plan = configuration.private_evidence
    if configuration.site_id not in ("gitlab", "reddit") or plan is None:
        raise OwnershipConflict(
            "Selected site requires explicit original artifact plan"
        )
    control.checkpoint()
    admission = OriginalSiteStorageAdmission(
        configuration, participant, OriginalSiteAcquisitionReader(), worker_guard, None
    )
    clock = SystemClock()
    # A physical operation derives an independent run-level ID while polling
    # the original caller control. No RunPlan/source claim is synthesized here.
    store = assemble_evidence_store(
        plan.binding,
        plan.config,
        plan.config.installation.python_executable,
        admission,
        clock,
        _IndependentCleanupControls(),
        control,
        max_io_seconds=60,
        cleanup_seconds=30,
    )
    return OriginalSitePrivateArtifacts(plan, store, admission)
