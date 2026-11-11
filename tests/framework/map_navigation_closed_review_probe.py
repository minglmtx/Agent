"""Rebuild only retained original records/files in an independent process."""

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.bootstrap.map_navigation_evaluation import (
    map_navigation_evaluator,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import ResourceRecord, OperationContext
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import ResetSelection
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.sites.map.evidence_schema import MapNavigationEvidence
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from source_actor_review import read_fact
from source_review_records import ReadOnlyEvidence, review_state
from map_closed_review_access import ClosedMapReviewAccess
from map_closed_review_records import preparations
from map_closed_review_evaluation import ClosedMapEvaluation
from test_resource_journal import NoCancellation


def probe(path: Path) -> None:
    facts = json.loads(path.read_bytes())
    assert facts["engineering_only"] is True and facts["synthetic_kernel"] is True
    assert facts["original_process"] != os.getpid()
    store = ReadOnlyEvidence(Path(facts["evidence_root"]))
    site = SiteResourceSpec.model_validate_json(json.dumps(facts["configuration"]))
    b = facts["prepared_browser"]
    browser = BrowserResourceSpec.model_validate_json(json.dumps(b["browser_spec"]))
    site_record = ResourceRecord.model_validate_json(
        json.dumps(facts["resource_record"])
    )
    browser_record = ResourceRecord.model_validate_json(json.dumps(b["browser_record"]))
    started = SiteResourceStarted.model_validate_json(json.dumps(facts["started"]))
    op = OperationContext(
        operation_id="closed-navigation-review",
        run_id=site.token.owner.run_id,
        owner_id=site.token.owner.owner_id,
        attempt_id=browser.token.attempt_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=75),
        mode="cleanup",
        parent_operation_id="original-software-source",
    )
    controls = OperationGuards(SystemClock(), NoCancellation())
    control = controls.bind(op)
    access = ClosedMapReviewAccess(
        site, browser, site_record, browser_record, store, control
    )
    initial, reset = review_state(facts, store, control)
    files = OriginalMapStateReader(
        Path(site.configuration.files.workspace_root), access, access
    )
    records = preparations(initial, access, files, store, controls)
    judgment = facts["judgment"]
    evidence = read_fact(
        store,
        EvidenceRef.model_validate(judgment["selected_evidence_ref"]),
        MapNavigationEvidence,
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
    review = ClosedMapEvaluation(access, initial, started, store, controls, op)
    evaluator = review.evaluator(evidence)
    # Do not accept agreement on an unknown caused by broken assembly.
    evaluator.loader(contract, evidence, store, control)
    assert saved.status == facts["expected_status"] and saved.status in (
        "success",
        "failure",
    )
    assert evaluator.evaluate(contract, store, control) == saved
    assert evaluator.evaluate(contract, store, control) == saved
    selected_ref = EvidenceRef.model_validate(
        facts["qualified_source"]["reset_selection_ref"]
    )
    selected = read_fact(store, selected_ref, ResetSelection, control)
    checks = OverlayStateChecks(store, files, site, started).reset(
        selected, selected_ref, control
    )
    assert (
        checks.task,
        checks.environment,
        checks.health,
        checks.plan,
        checks.closures,
    ) == (
        reset.task.checks,
        reset.environment.checks,
        reset.health.checks,
        reset.plan,
        reset.closures,
    )
    with pytest.raises(OwnershipConflict, match="no MapData"):
        _ = access.browser_plan
    original = next(iter(access.plans.values()))
    for phase in ("initialize", "write", "seal", "", None, 1):
        invalid: Any = phase
        with pytest.raises(OwnershipConflict):
            access.verify(original, invalid, control)
    foreign = original.model_copy(update={"private_root": str(path.parent / "foreign")})
    with pytest.raises(OwnershipConflict):
        access.verify(foreign, "read", control)
    for sr, br in (
        (
            site_record.model_copy(update={"events": site_record.events[:-1]}),
            browser_record,
        ),
        (
            site_record,
            browser_record.model_copy(update={"events": browser_record.events[:-1]}),
        ),
    ):
        with pytest.raises((ValueError, EvidenceIntegrityError)):
            ClosedMapReviewAccess(site, browser, sr, br, store, control)
    print(
        json.dumps(
            dict(
                separate_process=True,
                evaluation=saved.status,
                reset="safe",
                read_only=True,
                engineering_only=True,
            )
        )
    )


if __name__ == "__main__":
    probe(Path(sys.argv[1]))
