"""Explicit software subprocess: review real file bytes with synthetic closures."""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.lifecycle import ResourceRecord, OperationContext
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.sites.map.evidence_schema import MapOverlayEvidence
from source_review_records import ReadOnlyEvidence, review_state
from source_actor_review import read_fact
from test_resource_journal import NoCancellation
from map_closed_review_access import ClosedMapReviewAccess
from map_closed_review_evaluation import ClosedMapEvaluation


def probe(path: Path) -> None:
    site = json.loads(path.read_bytes())
    assert site["original_process"] != os.getpid()
    store = ReadOnlyEvidence(Path(site["evidence_root"]))
    spec = SiteResourceSpec.model_validate_json(json.dumps(site["configuration"]))
    browser = BrowserResourceSpec.model_validate_json(
        json.dumps(site["prepared_browser"]["browser_spec"])
    )
    record = ResourceRecord.model_validate_json(json.dumps(site["resource_record"]))
    br = ResourceRecord.model_validate_json(
        json.dumps(site["prepared_browser"]["browser_record"])
    )
    owner = spec.token.owner
    op = OperationContext(
        operation_id="closed-software-review",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        attempt_id=browser.token.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=75),
        mode="cleanup",
        parent_operation_id="source",
    )
    controls = OperationGuards(SystemClock(), NoCancellation())
    control = controls.bind(op)
    access = ClosedMapReviewAccess(spec, browser, record, br, store, control)
    initial, reset = review_state(site, store, control)
    review = ClosedMapEvaluation(
        access,
        initial,
        SiteResourceStarted.model_validate_json(json.dumps(site["started"])),
        store,
        controls,
        op,
    )
    judgment = site["judgment"]
    selected = read_fact(
        store,
        EvidenceRef.model_validate(judgment["selected_evidence_ref"]),
        MapOverlayEvidence,
        control,
    )
    contract = read_fact(
        store,
        EvidenceRef.model_validate(judgment["contract_ref"]),
        EvaluationContract,
        control,
    )
    saved = read_fact(
        store,
        EvidenceRef.model_validate(judgment["evaluation_ref"]),
        Evaluation,
        control,
    )
    assert contract.task_contract_ref == initial.preparation.task_binding_ref
    evaluator = review.evaluator(selected)
    # Surface the original error before the evaluator deliberately classifies unknown.
    evaluator.loader(contract, selected, store, control)
    assert evaluator.evaluate(contract, store, control) == saved
    # A repeat is read-only recomputation, never a new capture/query/restore.
    assert review.evaluator(selected).evaluate(contract, store, control) == saved
    checked = review.reset(
        EvidenceRef.model_validate(site["qualified_source"]["reset_selection_ref"]),
        control,
    )
    assert (
        checked.task,
        checked.environment,
        checked.health,
        checked.plan,
        checked.closures,
    ) == (
        reset.task.checks,
        reset.environment.checks,
        reset.health.checks,
        reset.plan,
        reset.closures,
    )
    assert saved.status == "failure" and saved.reward == 0
    for phase in ("initialize", "write", "seal", "", None, 1):
        invalid: Any = phase
        with pytest.raises(OwnershipConflict):
            access.verify(access.browser_plan, invalid, control)
    bad_plans: tuple[Any, ...] = (None, {}, "", 1)
    for bad_plan in bad_plans:
        invalid_plan: Any = bad_plan
        with pytest.raises(ValueError):
            access.verify(invalid_plan, "read", control)
    foreign = access.browser_plan.model_copy(
        update={"private_root": str(path.parent / "foreign")}
    )
    with pytest.raises(OwnershipConflict):
        access.verify(foreign, "read", control)
    with ThreadPoolExecutor() as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(access.verify, access.browser_plan, "read", control).result()
    for partial_site, partial_browser in (
        (record.model_copy(update={"events": record.events[:-1]}), br),
        (record, br.model_copy(update={"events": br.events[:-1]})),
    ):
        with pytest.raises((ValueError, EvidenceIntegrityError)):
            ClosedMapReviewAccess(
                spec, browser, partial_site, partial_browser, store, control
            )
    # A valid but different configuration must not inherit original acquisition.
    assert spec.configuration.map_inputs is not None
    changed = spec.model_copy(
        update={
            "configuration": spec.configuration.model_copy(
                update={
                    "map_inputs": spec.configuration.map_inputs.model_copy(
                        update={"max_files": 999}
                    )
                }
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        ClosedMapReviewAccess(changed, browser, record, br, store, control)
    expired = controls.bind(
        op.model_copy(
            update={
                "operation_id": "expired-review",
                "deadline": datetime.now(timezone.utc) - timedelta(seconds=1),
            }
        )
    )
    with pytest.raises(OperationStopped):
        access.verify(access.browser_plan, "read", expired)
    with pytest.raises(OperationStopped):
        ClosedMapReviewAccess(spec, browser, record, br, store, expired)
    print(
        json.dumps(
            dict(
                separate_process=True,
                evaluation="failure",
                reset="safe",
                read_only=True,
            )
        )
    )


if __name__ == "__main__":
    probe(Path(sys.argv[1]))
