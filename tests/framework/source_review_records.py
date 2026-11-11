"""Engineering independent review: retained acquisition, state and closure facts."""

import json
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.storage.filesystem import FileEvidenceStore
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import ResourceRecord, AllocationToken
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    assemble_baseline,
)
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt, assemble_reset
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from source_actor_review import read_fact


class ReadOnlyEvidence:
    def __init__(self, root: Path) -> None:
        self.primitive = FileEvidenceStore(root, initialize=False)

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        result = self.primitive.read(reference)
        control.checkpoint()
        return result

    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        raise PermissionError("Independent review has no write capability")


def raw_json(
    store: ReadOnlyEvidence, reference: Any, control: OperationControl
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
    store: ReadOnlyEvidence,
    control: OperationControl,
) -> dict[str, Any]:
    record = ResourceRecord.model_validate_json(json.dumps(value))
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
    acquisition = read_fact(
        store, record.events[1].evidence[0], ResourceAcquisitionIntent, control
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
            from source_review_browser import review_browser_initial

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
        ending["primary"] is not None
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
    # Inspect the retained observations rather than accepting the summary flag.
    for command in raw["commands"]:
        if not command["complete"] or command["returncode"] != 0:
            raise EvidenceIntegrityError("Original closure query did not complete")
    return dict(configuration=config, acquired=acquired, ending=ending, target=target)


def review_state(
    site: dict[str, Any], store: ReadOnlyEvidence, control: OperationControl
) -> tuple[BaselineInputs, ResetInputs]:
    observed, qualified = site["prepared_browser"], site["qualified_source"]
    initial = BaselineInputs.model_validate_json(
        store.read(EvidenceRef.model_validate(observed["baseline_inputs_ref"]), control)
    )
    baseline = read_fact(
        store,
        EvidenceRef.model_validate(qualified["baseline_ref"]),
        BaselineReceipt,
        control,
    )
    reset_inputs = ResetInputs.model_validate_json(
        store.read(EvidenceRef.model_validate(qualified["reset_inputs_ref"]), control)
    )
    reset = read_fact(
        store, EvidenceRef.model_validate(qualified["reset_ref"]), ResetReceipt, control
    )
    if (
        assemble_baseline(initial, baseline.operation) != baseline
        or baseline.status != "ready"
        or assemble_reset(reset_inputs, reset.operation) != reset
        or reset.status != "safe"
    ):
        raise EvidenceIntegrityError("Independent baseline/reset recomputation differs")
    pairs = (
        (initial.binding.public_task_ref, initial.public_task),
        (initial.binding.private_spec_ref, None),
        (initial.spec_ref, initial.spec),
        (initial.environment_ref, initial.environment),
        (initial.preparation_ref, initial.preparation),
        (initial.prepared_ref, initial.prepared),
        (initial.observation_ref, initial.observation),
        (initial.initial_ref, initial.initial),
        (reset_inputs.plan_ref, reset_inputs.plan),
        (reset_inputs.task_ref, reset_inputs.task),
        (reset_inputs.environment_ref, reset_inputs.environment),
        (reset_inputs.health_ref, reset_inputs.health),
    )
    for ref, model in pairs:
        data = store.read(ref, control)
        if model is not None and data != model.model_dump_json().encode():
            raise EvidenceIntegrityError(
                "Independent state input changed retained referenced fact"
            )
    for ref, closure in zip(
        reset_inputs.closure_refs, reset_inputs.closures, strict=True
    ):
        if (
            store.read(ref, control) != closure.model_dump_json().encode()
            or closure.status != "closed"
        ):
            raise EvidenceIntegrityError(
                "Reset lacks original confirmed browser closure"
            )
    if (
        reset.scope != baseline.scope
        or baseline.observation_ref
        != EvidenceRef.model_validate(observed["initial_observation_ref"])
    ):
        raise EvidenceIntegrityError(
            "Independent recovery changed original attempt/initial observation"
        )
    return initial, reset_inputs
