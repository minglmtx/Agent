"""Read the exact early browser worker acquisition; no readiness or new dispatch."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.ledger.original_resource import (
    BoundOriginalReadControls,
    OriginalResourceFacts,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_storage_original import BrowserStorageOriginal
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourcePrepared,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl


class OriginalBrowserAcquisitionReader:
    def read(
        self, configuration: BrowserWorkerConfiguration, control: OperationControl
    ) -> BrowserStorageOriginal:
        configuration = BrowserWorkerConfiguration.model_validate(configuration)
        inputs = configuration.map_inputs
        if inputs is None:
            raise OwnershipConflict(
                "Original browser file access needs frozen Map inputs"
            )
        token = inputs.plan.token
        operation = OperationContext(
            operation_id="browser-storage-original-" + uuid4().hex,
            run_id=token.owner.run_id,
            owner_id=token.owner.owner_id,
            attempt_id=token.attempt_id,
            allocation_id=token.allocation_id,
            recovery_ref=token.recovery_ref,
            deadline=datetime.now(timezone.utc)
            + timedelta(seconds=min(60.0, control.checkpoint())),
        )
        facts = OriginalResourceFacts(inputs.evidence_root, "browser")
        journal = FileResourceJournal(
            Path(inputs.resource_journal_root),
            token.owner,
            BoundOriginalReadControls(operation, control),
            facts,
        )
        record = journal.read(token, operation)
        acquiring = [event for event in record.events if event.state == "acquiring"]
        acquired = [event for event in record.events if event.state == "acquired"]
        if (len(acquiring), len(acquired)) != (1, 1) or any(
            len(event.evidence) != 1 for event in (*acquiring, *acquired)
        ):
            raise OwnershipConflict("Original browser worker was not durably acquired")
        intent = facts.fact(
            acquiring[0].evidence[0],
            ResourceAcquisitionIntent,
            "resource-acquisition-intent/1",
            control,
        )
        spec = facts.fact(
            intent.configuration_ref,
            BrowserResourceSpec,
            "browser-resource-spec/4",
            control,
        )
        obtained = facts.fact(
            acquired[0].evidence[0],
            BrowserWorkerAcquiredFact,
            "browser-worker-acquired/1",
            control,
        )
        prepared = facts.fact(
            obtained.details.prepared_ref,
            BrowserResourcePrepared,
            "browser-resource-prepared/1",
            control,
        )
        if spec.configuration != configuration or prepared != obtained.details.prepared:
            raise OwnershipConflict(
                "Browser file access changed frozen configuration/worker"
            )
        result = BrowserStorageOriginal(
            record=record, intent=intent, spec=spec, acquired=obtained
        )
        control.checkpoint()
        return result
