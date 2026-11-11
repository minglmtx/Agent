"""Read-only retained production inputs, no current authority or resource action.

Run only under Slurm. The original graph readers validate immutable historical
contents; no new source/claim/permission, recovery, request or Actor is issued.
"""

import json
from pathlib import Path
from typing import Any
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_preparation import (
    SiteTaskPrepared,
    SiteTaskPreparationPlan,
)
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.preparation import PreparedTask, EnvironmentBaseline
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.baseline import BaselineReceipt
from lab_generate_skill.domain.reset import ResetPlan, ResetReceipt
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.domain.public_context import assemble_public_context
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
CASES = {
    "Admin": ("framework-admin-navigation-production-20261102-v1", 4923819),
    "Map": ("framework-map-navigation42-production-20261102-v1", 4923741),
}


def retained_inputs(site: str, *, job: int | None = None) -> dict[str, Any]:
    package, default_job = CASES[site]
    job = default_job if job is None else job
    root = W / "experiments" / package / f"production-{job}"
    blobs = root / "evidence/blobs"

    class ReadOnly:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            control.checkpoint()
            path = blobs / reference.sha256
            assert path.is_file() and not path.is_symlink()
            raw = path.read_bytes()
            require_complete_bytes(reference, raw)
            control.checkpoint()
            return raw

    store = ReadOnly()
    reads = StateReads(store)
    control = guard(120)
    journals = list((root / "run").glob("*.run.json"))
    assert len(journals) == 1
    entries = json.loads(journals[0].read_text())["entries"]
    refs = {
        EvidenceRef.model_validate(x)
        for e in entries
        for x in e.get("event", {}).get("outputs", [])
        if x["content_schema"] == "task-execution-plan/2"
    }
    assert len(refs) == 1
    plan = reads.parse(
        next(iter(refs)), "task-execution-plan/2", TaskExecutionPlan, control
    )
    # The original plan intentionally defers initialization declaration creation.
    # Locate that one original immutable result, not another run/attempt/input.
    selected = []
    for path in blobs.iterdir():
        control.checkpoint()
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            continue
        with path.open("rb") as stream:
            prefix = stream.read(128)
            if b'"schema_version":"task-initialization-plan/2"' not in prefix:
                continue
            raw = prefix + stream.read()
        d = TaskInitializationPlan.model_validate_json(raw)
        if (d.scope.task, d.scope.attempt_id, d.scope.owner) == (
            plan.intent.binding.task,
            plan.intent.binding.attempt_id,
            plan.intent.binding.run.owner,
        ):
            selected.append(d)
    assert len(selected) == 1
    declaration = selected[0]
    original = reads.parse(
        declaration.prepared_result_ref,
        "site-task-prepared/2",
        SiteTaskPrepared,
        control,
    )
    prepared_plan = reads.parse(
        original.declaration_ref,
        "site-task-preparation-plan/2",
        SiteTaskPreparationPlan,
        control,
    )
    prepared = reads.parse(
        original.publication.prepared_ref, "prepared-task/1", PreparedTask, control
    )
    environment = reads.parse(
        original.environment_ref, "environment-baseline/1", EnvironmentBaseline, control
    )
    receipt = reads.parse(
        declaration.source_context_receipt_ref,
        "public-context-receipt/1",
        PublicContextReceipt,
        control,
    )
    baseline = reads.parse(
        receipt.baseline_ref, "baseline-receipt/1", BaselineReceipt, control
    )
    reset_receipt = reads.parse(
        receipt.reset_ref, "reset-receipt/1", ResetReceipt, control
    )
    context = reads.parse(
        receipt.public_context_ref,
        "public-construction-context/1",
        PublicConstructionContext,
        control,
        visibility="public",
    )
    inputs = PublicContextInputs(
        context=context,
        context_ref=receipt.public_context_ref,
        baseline_inputs=BaselineEvidenceReader(store).verify(baseline, control),
        baseline=baseline,
        baseline_ref=receipt.baseline_ref,
        reset_inputs=ResetEvidenceReader(store).verify(reset_receipt, control),
        reset=reset_receipt,
        reset_ref=receipt.reset_ref,
    )
    assert assemble_public_context(inputs, receipt.operation) == receipt
    return dict(
        plan=plan,
        declaration=declaration,
        original=original,
        prepared_plan=prepared_plan,
        prepared=prepared,
        environment=environment,
        source=receipt,
        source_inputs=inputs,
        reset=reads.parse(plan.reset_plan_ref, "reset-plan/1", ResetPlan, control),
        browser=reads.parse(
            declaration.browser_spec_ref,
            "browser-resource-spec/4",
            BrowserResourceSpec,
            control,
        ),
        acquired=reads.parse(
            original.acquired_ref, "site-task-acquired/1", SiteTaskAcquired, control
        ),
        request=reads.parse(
            original.publication.selection.request_ref,
            "site-task-request/2",
            SiteTaskRequest,
            control,
        ),
    )
