"""Original failed Map consumer is readable only with complete retained closure.

The fixed historical train resource is an offline regression fixture. No live
kernel inspection, old source permit, browser action or restoration is issued.
Negative variants exist in memory and never alter original CAS or journals.
"""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.closed_resource import review_resource
from lab_generate_skill.adapters.map_artifacts.closed_access import (
    ClosedMapSourceAccess,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.ports.lifecycle import OperationControl

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1/production-4957659"
)
ENDING = "a9c4e49976d7d556fe482ec36c4852251bb9ad19f7f737d8b747460e62264245"


class RetainedOnly:
    def __init__(self) -> None:
        self.variants: dict[EvidenceRef, bytes] = {}

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        raw = self.variants.get(reference)
        if raw is None:
            raw = (ROOT / "evidence/blobs" / reference.sha256).read_bytes()
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (
            reference.size_bytes,
            reference.sha256,
        ):
            raise EvidenceIntegrityError(
                "Retained original or in-memory negative bytes changed"
            )
        return raw

    def variant(self, original: EvidenceRef, body: dict[str, Any]) -> EvidenceRef:
        raw = json.dumps(body, sort_keys=True).encode()
        metadata = EvidenceMetadata(
            media_type=original.media_type,
            content_schema=original.content_schema,
            visibility=original.visibility,
            producer=original.producer,
        )
        ref = evidence_reference(raw, metadata)
        self.variants[ref] = raw
        return ref


def original() -> tuple[ResourceRecord, RetainedOnly]:
    matches = []
    for path in (ROOT / "resources").glob("*.resource.json"):
        record = ResourceRecord.model_validate_json(path.read_bytes())
        if record.token.allocation_id == "execution.site":
            matches.append(record)
    assert len(matches) == 1 and matches[0].events[-1].evidence[0].sha256 == ENDING
    return matches[0], RetainedOnly()


def test_explicit_failed_consumer_read_keeps_original_primary_and_checks_complete_closure() -> (
    None
):
    record, store = original()
    control = DeadlineControl(30, "retained-failed-consumer-read")
    with pytest.raises(EvidenceIntegrityError, match="primary or cleanup failure"):
        review_resource(record.model_dump(mode="json"), record.token, store, control)
    result = review_resource(
        record.model_dump(mode="json"),
        record.token,
        store,
        control,
        allow_failed_consumer=True,
    )
    ending = json.loads(store.read(record.events[-1].evidence[0], control))
    assert result["ending"]["primary"] == ending["details"]["primary"]
    assert result["ending"]["primary"] is not None
    assert result["ending"]["cleanup_errors"] == []
    assert result["ending"]["termination"]["state"] == "reaped"


@pytest.mark.parametrize(
    "fault",
    ["cleanup_error", "unconfirmed_termination", "foreign_worker", "failed_query"],
)
def test_failed_consumer_option_never_bypasses_cleanup_or_original_worker_proof(
    fault: str,
) -> None:
    record, store = original()
    control = DeadlineControl(30, "retained-failed-consumer-negative")
    ref = record.events[-1].evidence[0]
    ending = json.loads(store.read(ref, control))
    details = ending["details"]
    if fault == "cleanup_error":
        details["cleanup_errors"] = [{"type_name": "UnitCleanupFailure"}]
    elif fault == "unconfirmed_termination":
        details["termination"]["state"] = "unconfirmed"
    elif fault == "foreign_worker":
        details["step_closed"]["quiescence"]["original"]["writer"]["process_id"] += 1
    else:
        step_ref = EvidenceRef.model_validate(details["step_closed"]["evidence"])
        raw = json.loads(store.read(step_ref, control))
        raw["commands"][0]["returncode"] = 37
        details["step_closed"]["evidence"] = store.variant(step_ref, raw).model_dump(
            mode="json"
        )
    changed = store.variant(ref, ending)
    last = record.events[-1].model_copy(update={"evidence": (changed,)})
    altered = record.model_copy(update={"events": (*record.events[:-1], last)})
    with pytest.raises(EvidenceIntegrityError):
        review_resource(
            altered.model_dump(mode="json"),
            record.token,
            store,
            control,
            allow_failed_consumer=True,
        )


def test_failed_consumer_read_rejects_foreign_resource_and_non_boolean_selection() -> (
    None
):
    record, store = original()
    control = DeadlineControl(30, "retained-failed-consumer-identity")
    foreign = record.token.model_copy(update={"allocation_id": "foreign-site"})
    with pytest.raises(EvidenceIntegrityError, match="fully acquired then closed"):
        review_resource(
            record.model_dump(mode="json"),
            foreign,
            store,
            control,
            allow_failed_consumer=True,
        )
    with pytest.raises(TypeError, match="explicit boolean"):
        invalid: Any = 1
        review_resource(
            record.model_dump(mode="json"),
            record.token,
            store,
            control,
            allow_failed_consumer=invalid,
        )


def test_original_map_closed_constructor_explicitly_consumes_failed_site_and_browser_facts() -> (
    None
):
    site_record, store = original()
    control = DeadlineControl(30, "retained-original-map-constructor")
    browsers = [
        ResourceRecord.model_validate_json(path.read_bytes())
        for path in (ROOT / "resources").glob("*.resource.json")
    ]
    matches = [
        record
        for record in browsers
        if record.token.allocation_id == "execution.browser"
    ]
    assert len(matches) == 1
    browser_record = matches[0]
    site_intent = ResourceAcquisitionIntent.model_validate_json(
        store.read(site_record.events[1].evidence[0], control)
    )
    browser_intent = ResourceAcquisitionIntent.model_validate_json(
        store.read(browser_record.events[1].evidence[0], control)
    )
    site = SiteResourceSpec.model_validate_json(
        store.read(site_intent.configuration_ref, control)
    )
    browser = BrowserResourceSpec.model_validate_json(
        store.read(browser_intent.configuration_ref, control)
    )
    with pytest.raises(EvidenceIntegrityError, match="primary or cleanup failure"):
        ClosedMapSourceAccess(
            site, browser, site_record, browser_record, store, control
        )
    access = ClosedMapSourceAccess(
        site,
        browser,
        site_record,
        browser_record,
        store,
        control,
        allow_failed_consumer=True,
    )
    assert access.site == site and access.browser == browser
    assert access.browser_closure.status == "closed"
