"""Separate readonly review of the original closed category member."""

from pathlib import Path
import json
import time
from typing import Any
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import Clock, OperationControls
from .shopping_category_production_member import CategoryNavigationMemberCompletion


def review_completed_category_member(
    completed: CategoryNavigationMemberCompletion,
    python_executable: str,
    output: Path,
    operation: OperationContext,
    controls: OperationControls,
    clock: Clock,
    facts: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(completed, CategoryNavigationMemberCompletion):
        raise TypeError("Original completed category member required")
    path = output / "independent-review-inputs.json"
    with path.open("x") as stream:
        stream.write(json.dumps(completed.review_material, indent=2) + "\n")
    path.chmod(0o600)
    review_operation = operation.cleanup(
        "category.independent-readonly-review", now=clock.utcnow(), seconds=660
    )
    before = time.monotonic()
    capture = ProcessRunner(max_output_bytes=8 * 1024**2).run(
        (
            python_executable,
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.shopping_category_production_review",
            str(path),
        ),
        controls.bind(review_operation),
    )
    (output / "independent-review.stdout").write_bytes(capture.stdout)
    (output / "independent-review.stderr").write_bytes(capture.stderr)
    if not capture.complete or capture.returncode != 0:
        raise ValueError("Original independent category review unconfirmed")
    review = json_object(capture.stdout)
    result = completed.result
    if (
        review.get("passed") is not True
        or review.get("separate_process") is not True
        or review.get("read_only") is not True
        or review.get("business_result") != result.evaluation.status
        or review.get("generations") != result.generations
        or review.get("interactions") != result.interactions
        or review.get("reset") != "safe"
        or review.get("formal_training_qualification") is not False
    ):
        raise ValueError(
            "Independent category review changed original judgment/counters/closure"
        )
    facts.update(
        independent_review=review,
        independent_review_seconds=time.monotonic() - before,
        phase="member_closed_reviewed",
    )
    return review
