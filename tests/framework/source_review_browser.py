"""Independent current browser ownership/initial/closure reference reconstruction."""

import json
from typing import Any
from lab_generate_skill.domain.browser_resource import (
    BrowserResourceSpec,
    BrowserResourceStarted,
)
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.initial_observation import BrowserAcquiredFact
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


def review_browser_initial(
    config: dict[str, Any],
    acquired: dict[str, Any],
    ending: dict[str, Any],
    acquired_ref: EvidenceRef,
    store: EvidenceReader,
    control: OperationControl,
) -> BrowserResourceStarted:
    worker = BrowserWorkerAcquiredFact.model_validate_json(json.dumps(acquired))
    worker.check_spec(BrowserResourceSpec.model_validate_json(json.dumps(config)))
    prepared = worker.details.prepared
    if (
        store.read(worker.details.prepared_ref, control=control)
        != prepared.model_dump_json().encode()
    ):
        raise EvidenceIntegrityError("Original pre-navigation worker bytes changed")
    ref = EvidenceRef.model_validate_json(json.dumps(ending["initial_ready_ref"]))
    if (ref.content_schema, ref.visibility, ref.media_type, ref.producer) != (
        "browser-resource-fact/1",
        "private",
        "application/json",
        "fixed-browser-resource",
    ) or not 0 < ref.size_bytes <= 16 * 1024**2:
        raise EvidenceIntegrityError("Original bounded browser initial fact required")
    initial = BrowserAcquiredFact.model_validate_json(store.read(ref, control=control))
    actual = BrowserResourceStarted.model_validate_json(
        json.dumps(ending["attempt"]["started"])
    )
    if (
        initial.token != worker.token
        or initial.spec_sha256 != worker.spec_sha256
        or initial.details.worker_acquired_ref != acquired_ref
        or initial.details.started != actual
        or initial.operation.parent_operation_id != worker.operation.parent_operation_id
        or initial.operation.operation_id == worker.operation.operation_id
        or (actual.owner_guard, actual.step, actual.installed_sources)
        != (prepared.owner_guard, prepared.step, prepared.installed_sources)
    ):
        raise EvidenceIntegrityError(
            "Initialized browser changed original acquired worker"
        )
    return actual
