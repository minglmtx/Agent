"""Complete immutable category closure facts for a separate readonly reviewer."""

import os
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.execution_task_result import ExecutionTaskResult
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.local_actor import LocalActorExecution
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from .shopping_category_owned_execution import OwnedCategoryNavigationExecution


def completed_category_review_material(
    owned: OwnedCategoryNavigationExecution,
    source: ClosedCategoryNavigationReadMaterial,
    result: ExecutionTaskResult,
    actor_record: ResourceRecord,
    snapshot: TraceSnapshot,
    executions: tuple[LocalActorExecution, ...],
    evidence_root: Path,
) -> dict[str, Any]:
    if not isinstance(owned, OwnedCategoryNavigationExecution):
        raise TypeError("Original category owned execution required")
    source = ClosedCategoryNavigationReadMaterial.model_validate(source)
    result = ExecutionTaskResult.model_validate(result)
    actor_record = ResourceRecord.model_validate(actor_record)
    initial = owned.bundle.initialization.original().state
    final = owned.bundle.finalization.state
    capture = owned.bundle.capture.state
    site = owned.resources.site
    browser = owned.resources.browser()
    if (
        site.spec.configuration.site_id != "shopping"
        or source.site.token.owner != site.spec.token.owner
        or initial.result is None
        or initial.baseline_inputs is None
        or initial.baseline_ref is None
        or final.reset_inputs is None
        or final.reset_ref is None
        or final.reset_selection_ref is None
        or final.reset is None
        or final.reset.status != "safe"
        or capture.selection_ref is None
        or site.closed is None
        or browser is None
        or browser.closed is None
        or actor_record.state != "closed"
    ):
        raise ValueError(
            "Actual category initial/capture/Reset and original resource closures required"
        )
    return dict(
        schema_version="shopping-category-owned-closed-review-inputs/1",
        original_process=os.getpid(),
        engineering_only=True,
        source_material=source.model_dump(mode="json"),
        evidence_root=str(evidence_root),
        site=site.spec.model_dump(mode="json"),
        browser=browser.spec.model_dump(mode="json"),
        started=site.site.model_dump(mode="json"),
        site_record=site.closed.model_dump(mode="json"),
        browser_record=browser.closed.model_dump(mode="json"),
        actor_record=actor_record.model_dump(mode="json"),
        baseline_inputs=initial.baseline_inputs.model_dump(mode="json"),
        baseline_ref=initial.baseline_ref.model_dump(mode="json"),
        reset_inputs=final.reset_inputs.model_dump(mode="json"),
        reset_ref=final.reset_ref.model_dump(mode="json"),
        reset_selection_ref=final.reset_selection_ref.model_dump(mode="json"),
        selected_evidence_ref=capture.selection_ref.model_dump(mode="json"),
        evaluation_contract=owned.resources.plan.evaluation.model_dump(mode="json"),
        attempt_ref=result.attempt_ref.model_dump(mode="json"),
        trace_snapshot=snapshot.model_dump(mode="json"),
        model_executions=[x.model_dump(mode="json") for x in executions],
    )
