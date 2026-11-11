"""Retained original Actor acquisition and physical close; no live controller.

The Actor branch follows the original engineering source_review_records reader.
Site/browser closure remains with the existing strict closed_resource reader.
"""

from typing import Any
from lab_generate_skill.adapters.plans.closed_resource import raw_json
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.lifecycle import AllocationToken, ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from .closed_actor_review import read_fact


def review_actor_resource(
    value: dict[str, Any],
    token: AllocationToken,
    store: EvidenceStore,
    control: OperationControl,
) -> dict[str, Any]:
    record = ResourceRecord.model_validate(value)
    if (
        token.resource_kind != "actor"
        or record.token != token
        or [e.state for e in record.events]
        != ["registered", "acquiring", "acquired", "closing", "closed"]
    ):
        raise EvidenceIntegrityError(
            "Original Actor was not fully acquired then closed"
        )
    acquisition = read_fact(
        store, record.events[1].evidence[0], ResourceAcquisitionIntent, control
    )
    if acquisition.token != token:
        raise EvidenceIntegrityError("Original Actor acquisition changed token")
    config = raw_json(store, acquisition.configuration_ref, control)
    acquired = raw_json(store, record.events[2].evidence[0], control)
    ended = raw_json(store, record.events[-1].evidence[0], control)
    if (
        acquired["token"] != token.model_dump(mode="json")
        or ended["token"] != token.model_dump(mode="json")
        or acquired["spec_sha256"] != acquisition.configuration_ref.sha256
        or ended["spec_sha256"] != acquisition.configuration_ref.sha256
    ):
        raise EvidenceIntegrityError("Original Actor changed acquisition/configuration")
    target = acquired["step"]["controller"]["target"]
    closed = ended["step_closed"]
    if (
        ended["primary"] is not None
        or ended["cleanup_errors"]
        or ended["termination"]["state"] != "reaped"
        or ended["termination"]["cleanup_errors"]
    ):
        raise EvidenceIntegrityError("Original Actor has primary or cleanup failure")
    if (
        closed["target"] != target
        or closed["quiescence"]["original"] != target["worker"]
        or closed["quiescence"].get("writer_status") not in ("missing", "reused")
    ):
        raise EvidenceIntegrityError("Original Actor closure changed original worker")
    raw = raw_json(store, closed["evidence"], control)
    if (
        raw["phase"] != "closed"
        or raw["target"] != target
        or not raw["kernel"]
        or not raw["commands"]
        or raw["error"] is not None
        or any(not c["complete"] or c["returncode"] != 0 for c in raw["commands"])
    ):
        raise EvidenceIntegrityError(
            "Original Actor domain closure lacks kernel/controller proof"
        )
    return dict(configuration=config, acquired=acquired, ending=ended, target=target)
