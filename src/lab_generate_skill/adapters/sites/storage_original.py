"""Read original journal/CAS primitives only inside the supervised site boundary.

No initialize, write, discovery or replay. Caller control remains bound through
the original journal lock/read; returned declarations still need live admission.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_storage_original import (
    SiteAcquiredFact,
    SiteStorageOriginal,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.ledger.original_resource import (
    BoundOriginalReadControls,
    OriginalResourceFacts,
)


class OriginalSiteAcquisitionReader:
    def read(
        self, configuration: SiteWorkerConfiguration, control: OperationControl
    ) -> SiteStorageOriginal:
        configuration = SiteWorkerConfiguration.model_validate(configuration)
        plan = configuration.private_evidence
        if configuration.site_id == "map" and configuration.map_inputs is not None:
            evidence_root = configuration.map_inputs.evidence_root
            journal_root = configuration.map_inputs.resource_journal_root
        elif configuration.site_id in ("gitlab", "reddit") and plan is not None:
            evidence_root = plan.config.evidence_root
            journal_root = plan.resource_journal_root
        else:
            raise OwnershipConflict(
                "Original private storage requires a declared fixed native site"
            )
        control.checkpoint()
        token = configuration.token
        operation = OperationContext(
            operation_id="site-storage-original-" + uuid4().hex,
            run_id=token.owner.run_id,
            owner_id=token.owner.owner_id,
            allocation_id=token.allocation_id,
            recovery_ref=token.recovery_ref,
            deadline=datetime.now(timezone.utc)
            + timedelta(seconds=min(60.0, control.checkpoint())),
        )
        facts = OriginalResourceFacts(evidence_root, "site")
        journal = FileResourceJournal(
            Path(journal_root),
            token.owner,
            BoundOriginalReadControls(operation, control),
            facts,
        )
        record = journal.read(token, operation)
        acquiring = [event for event in record.events if event.state == "acquiring"]
        acquired = [event for event in record.events if event.state == "acquired"]
        if len(acquiring) != 1 or len(acquired) != 1 or len(acquired[0].evidence) != 1:
            raise OwnershipConflict("Original site was not durably acquired")
        intent = facts.fact(
            acquiring[0].evidence[0],
            ResourceAcquisitionIntent,
            "resource-acquisition-intent/1",
            control,
        )
        spec = facts.fact(
            intent.configuration_ref, SiteResourceSpec, "site-resource-spec/1", control
        )
        obtained = facts.fact(
            acquired[0].evidence[0], SiteAcquiredFact, "site-resource-fact/1", control
        )
        if spec.configuration != configuration:
            raise OwnershipConflict(
                "Private storage changed original acquired configuration"
            )
        result = SiteStorageOriginal(
            record=record, intent=intent, spec=spec, acquired=obtained
        )
        control.checkpoint()
        return result
