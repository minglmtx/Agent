"""Commit original observed worker ownership before any browser start command."""

import hashlib
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourcePrepared,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
    BrowserWorkerAcquiredDetails,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext, ResourceRecord
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, ResourceJournal
from .resource_records import phase, put, acknowledged


def commit_original_worker(
    spec: BrowserResourceSpec,
    prepared: BrowserResourcePrepared,
    prepared_ref: EvidenceRef,
    operation: OperationContext,
    acquiring: ResourceRecord,
    journal: ResourceJournal,
    evidence: EvidenceStore,
    control: OperationControl,
) -> EvidenceRef:
    op = phase(operation, "worker-acquired")
    fact = BrowserWorkerAcquiredFact(
        spec_sha256=hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
        token=spec.token,
        operation=op,
        details=BrowserWorkerAcquiredDetails(
            prepared=prepared,
            prepared_ref=prepared_ref,
            browser_started=False,
        ),
    )
    fact.check_spec(spec)
    reference = put(
        evidence, fact.model_dump_json().encode(), fact.schema_version, control
    )
    acknowledged(
        journal.advance(spec.token, "acquired", (reference,), acquiring.revision, op),
        spec,
        "acquired",
        op,
        reference,
        acquiring.revision + 1,
    )
    control.checkpoint()
    return reference
