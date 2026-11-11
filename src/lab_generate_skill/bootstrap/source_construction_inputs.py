"""Inspect the original group source index before constructing missing task facts.

The index can refuse redundant/uncertain work, never grant a source or action.
Installation/assets, actual instance/owner, journals and claim remain real gates.
"""

import hashlib
from pathlib import Path
from typing import Any
from lab_generate_skill.adapters.map_runtime.metadata import object_json
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.ports.lifecycle import OperationControl


def source_construction_inputs(
    plan: Path,
    task: TaskIdentity,
    current_job: str,
    control: OperationControl,
    *,
    checkpoint_path: tuple[str, ...] = ("group_execution_plan", "evidence_checkpoints"),
) -> dict[str, Any]:
    task = TaskIdentity.model_validate(task)
    if (
        type(checkpoint_path) is not tuple
        or not 1 <= len(checkpoint_path) <= 16
        or any(
            type(part) is not str or not part or len(part) > 256
            for part in checkpoint_path
        )
    ):
        raise ValueError("Exact bounded original checkpoint path required")
    control.checkpoint()
    if (
        not isinstance(plan, Path)
        or not plan.is_absolute()
        or plan.resolve(strict=True) != plan
        or not plan.is_file()
        or not 0 < plan.stat().st_size <= 8 * 1024**2
        or type(current_job) is not str
        or not current_job.isdecimal()
        or int(current_job) <= 0
    ):
        raise ValueError(
            "Original bounded source catalogue and current Slurm job required"
        )
    with plan.open("rb") as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if len(raw) > 8 * 1024**2:
        raise ValueError("Original source catalogue exceeds its bound")
    body = object_json(raw)
    try:
        current = body
        for part in checkpoint_path:
            current = current[part]
        members = current["members"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Missing original source checkpoint mapping; do not default to rebuilding"
        ) from error
    if not isinstance(members, dict) or any(
        not isinstance(member, dict)
        or not isinstance(member.get("source_task_id"), str)
        for member in members.values()
    ):
        raise ValueError("Invalid original source member index")
    selected = [
        member
        for member in members.values()
        if member["source_task_id"] == task.source_task_id
    ]
    for member in selected:
        if type(member.get("historical")) is not bool:
            raise ValueError(
                "Original task source attempt applicability is unconfirmed"
            )
        if member["historical"]:
            raise OwnershipConflict(
                "Original historical attempt is retained; source construction cannot replay it"
            )
        rows = member.get("checkpoints")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Original member source checkpoints are incomplete")
        sources = [row for row in rows if row.get("id") == "member.source"]
        if len(sources) != 1:
            raise ValueError("Exactly one original member source checkpoint required")
        source = sources[0]
        if source.get("status") == "通过":
            raise OwnershipConflict(
                "Qualified task source is indexed; consume matching original material or resolve its scope, never rebuild by default"
            )
        if (
            source.get("status") not in {"未开始", "进行中"}
            or source.get("evidence") != []
            or member.get("attempt_job") != current_job
        ):
            raise OwnershipConflict(
                "Prior or uncertain source evidence requires original reconciliation, not reconstruction"
            )
    control.checkpoint()
    return {
        "schema_version": "source-construction-input-needs/1",
        "source_task_id": task.source_task_id,
        "catalogue": str(plan),
        "catalogue_sha256": hashlib.sha256(raw).hexdigest(),
        "input_gap": (
            "current attempt has no task source"
            if selected
            else "no task-specific source indexed"
        ),
        "reuse": [
            "accepted installation/dependencies and readonly asset declarations",
            "task-independent SourceBrowserAssets policy",
        ],
        "required_new_facts": [
            "exact task/private/public binding",
            "current source-instance environment and initial measurements",
            "unique public initial observation",
            "original restoration and close facts",
        ],
        "reason": "Existing source facts bind their original task/owner/instance; no applicable complete task artifact is indexed. Current instance facts cannot be inherited from common assets or a shared start path.",
        "runtime_or_resume_authority": False,
    }
