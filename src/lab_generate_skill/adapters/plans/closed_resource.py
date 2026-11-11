"""Read retained original site/browser closure without a live controller or writes.

This is a historical read capability, never source, claim or execution approval.
The former engineering reviewer is reused with the actual worker envelope required;
synthetic closure schemas cannot pass the production boundary.
"""

import json
from typing import Any, Literal
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.domain.lifecycle import ResourceRecord, AllocationToken
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


def raw_json(
    store: EvidenceReader, reference: Any, control: OperationControl
) -> dict[str, Any]:
    ref = EvidenceRef.model_validate(reference)
    if not 0 < ref.size_bytes <= 16 * 1024 * 1024:
        raise EvidenceIntegrityError("Independent JSON read exceeds boundary")
    value = json.loads(store.read(ref, control))
    if not isinstance(value, dict):
        raise EvidenceIntegrityError("Independent JSON fact must be an object")
    return value


def review_resource(
    value: dict[str, Any],
    token: AllocationToken,
    store: EvidenceReader,
    control: OperationControl,
    *,
    allow_failed_consumer: bool = False,
) -> dict[str, Any]:
    if type(allow_failed_consumer) is not bool:
        raise TypeError(
            "Closed-read consumer failure selection must be explicit boolean"
        )
    record = ResourceRecord.model_validate_json(json.dumps(value))
    if token.resource_kind not in ("site", "browser"):
        raise EvidenceIntegrityError(
            "Closed source supports only original site/browser resources"
        )
    if record.token != token or [e.state for e in record.events] != [
        "registered",
        "acquiring",
        "acquired",
        "closing",
        "closed",
    ]:
        raise EvidenceIntegrityError(
            "Original resource is not fully acquired then closed"
        )
    acquisition = StateReads(store).parse(
        record.events[1].evidence[0],
        "resource-acquisition-intent/1",
        ResourceAcquisitionIntent,
        control,
    )
    if acquisition.token != token:
        raise EvidenceIntegrityError("Original resource acquisition changed token")
    config = raw_json(store, acquisition.configuration_ref, control)
    acquired = raw_json(store, record.events[2].evidence[0], control)
    ended = raw_json(store, record.events[-1].evidence[0], control)
    if (
        acquired["token"] != token.model_dump(mode="json")
        or ended["token"] != token.model_dump(mode="json")
        or acquired["spec_sha256"] != acquisition.configuration_ref.sha256
        or ended["spec_sha256"] != acquisition.configuration_ref.sha256
    ):
        raise EvidenceIntegrityError(
            "Original resource fact changed acquisition/configuration"
        )
    if token.resource_kind == "actor":
        started, ending = acquired["step"], ended
        closed = ending["step_closed"]
        target = started["controller"]["target"]
    else:
        starting, ending = acquired["details"], ended["details"]
        if (
            token.resource_kind == "browser"
            and config["schema_version"] == "browser-resource-spec/4"
        ):
            from .closed_browser import review_browser_initial

            actual = review_browser_initial(
                config, acquired, ending, record.events[2].evidence[0], store, control
            )
            started = actual.model_dump(mode="json")
        else:
            # Frozen older business receipts retain their original acquired shape.
            started = (
                starting["ready"]
                if token.resource_kind == "site"
                else starting["started"]
            )
        closed = ending["step_closed"]
        step = started if token.resource_kind == "site" else started["step"]
        target = step["controller"]["target"]
    if (
        (ending["primary"] is not None and not allow_failed_consumer)
        or ending["cleanup_errors"]
        or ending["termination"]["state"] != "reaped"
        or ending["termination"]["cleanup_errors"]
    ):
        raise EvidenceIntegrityError("Original resource has primary or cleanup failure")
    if (
        closed["target"] != target
        or closed["quiescence"]["original"] != target["worker"]
        or closed["quiescence"].get("writer_status") not in ("missing", "reused")
    ):
        raise EvidenceIntegrityError("Original resource closure changed actual worker")
    raw = raw_json(store, closed["evidence"], control)
    if (
        raw["phase"] != "closed"
        or raw["target"] != target
        or not raw["kernel"]
        or not raw["commands"]
        or raw["error"] is not None
    ):
        raise EvidenceIntegrityError(
            "Original domain closure lacks retained kernel/controller proof"
        )
    role: Literal["site", "browser"] = (
        "site" if token.resource_kind == "site" else "browser"
    )
    WorkerStepEvidence(role).require(
        store,
        EvidenceRef.model_validate(closed["evidence"]),
        SlurmStepTarget.model_validate_json(json.dumps(target)),
        "closed",
        control,
    )
    # Inspect the retained observations rather than accepting the summary flag.
    for command in raw["commands"]:
        if not command["complete"] or command["returncode"] != 0:
            raise EvidenceIntegrityError("Original closure query did not complete")
    return dict(configuration=config, acquired=acquired, ending=ending, target=target)
