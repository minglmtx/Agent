"""Complete state file ownership/budgets/partial publication; no production permission."""

import hashlib
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.writer import MapArtifactWriter
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from map_overlay_lifecycle_fixtures import OverlayCase
from test_map_overlay_lifecycle import overlay
from test_map_service_generations import generations
from test_map_instance import case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_large_complete_file_is_not_limited_by_task_reply(overlay: OverlayCase) -> None:
    c = overlay
    raw = b"complete synthetic file bytes\n" * 80000
    result = c.publisher.publish(c.request("snapshot"), raw, "a" * 64, guard())
    assert len(raw) > 1024**2 and len(result.model_dump_json().encode()) < 1024**2
    assert (
        c.read(result) == raw and result.file.sha256 == hashlib.sha256(raw).hexdigest()
    )
    assert c.publisher.writers[0].state == "sealed"
    with pytest.raises(InvalidTransition):
        c.publisher.publish(c.request("snapshot"), raw, "a" * 64, guard())
    assert len(c.publisher.writers) == 1


@pytest.mark.parametrize(
    "raw,digest",
    [
        (b"", "a" * 64),
        (None, "a" * 64),
        ("text", "a" * 64),
        (b"x", None),
        (b"x", ""),
        (b"x", "g" * 64),
        (b"x", "a" * 65),
    ],
)
def test_bad_state_input_no_plan_or_write(
    overlay: OverlayCase, raw: Any, digest: Any
) -> None:
    c = overlay
    with pytest.raises(ValueError):
        c.publisher.publish(c.request("snapshot"), raw, digest, guard())
    assert (
        c.publisher.state == "ready"
        and not c.publisher.attempts
        and not c.publisher.writers
        and not c.authority.plans
    )


@pytest.mark.parametrize("field", ["workspace", "attempt", "allocation", "task"])
def test_wrong_plan_rejected_before_initialization(
    overlay: OverlayCase, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    c = overlay
    original = c.authority.plan

    def plan(
        request: SiteTaskRequest, control: OperationControl
    ) -> MapPrivateArtifactPlan:
        value = original(request, control)
        if field == "workspace":
            return MapPrivateArtifactPlan.model_validate(
                {**value.model_dump(), "workspace_root": str(c.workspace.parent)}
            )
        if field == "attempt":
            return value.model_copy(
                update={"scope": value.scope.model_copy(update={"attempt_id": "other"})}
            )
        if field == "task":
            return value.model_copy(
                update={
                    "scope": value.scope.model_copy(
                        update={
                            "task": value.scope.task.model_copy(
                                update={"split": "test"}
                            )
                        }
                    )
                }
            )
        return value.model_copy(
            update={"token": value.token.model_copy(update={"allocation_id": "other"})}
        )

    monkeypatch.setattr(c.authority, "plan", plan)
    with pytest.raises((ValueError, OwnershipConflict)):
        c.publisher.publish(c.request("snapshot"), b"data", "a" * 64, guard())
    assert c.publisher.state == "failed" and not c.publisher.writers
    assert not list((c.workspace / "task-state").iterdir())


def test_seal_lost_ack_preserves_original_handle_and_blocks_lifecycle_replay(
    overlay: OverlayCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = overlay
    original = MapArtifactWriter.seal
    error = OSError("seal complete but ack unknown")

    def seal(writer: MapArtifactWriter, control: OperationControl) -> Any:
        original(writer, control)
        raise error

    monkeypatch.setattr(MapArtifactWriter, "seal", seal)
    with pytest.raises(OSError) as caught:
        c.snapshot()
    assert caught.value is error is c.publisher.error is c.lifecycle.error
    assert c.publisher.state == "failed" and c.lifecycle.phase == "quarantined"
    assert len(c.publisher.writers) == 1 and c.publisher.writers[0].handle is not None
    assert c.publisher.writers[0].state == "sealed" and not c.publisher.results
    with pytest.raises(InvalidTransition):
        c.lifecycle.execute_task(c.request("snapshot", "again"), control=guard())
    assert len(c.publisher.writers) == 1


def test_budget_failure_keeps_intent_and_no_incomplete_state_result(
    overlay: OverlayCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = overlay
    original = c.authority.plan

    def plan(
        request: SiteTaskRequest, control: OperationControl
    ) -> MapPrivateArtifactPlan:
        value = original(request, control)
        small = MapPrivateArtifactPlan.model_validate(
            {**value.model_dump(), "max_file_bytes": 1}
        )
        c.authority.plans[small.digest] = small
        return small

    monkeypatch.setattr(c.authority, "plan", plan)
    with pytest.raises(ValueError, match="budget"):
        c.snapshot()
    assert len(c.publisher.writers) == 1 and c.publisher.writers[0].root.is_dir()
    assert not c.publisher.results and c.lifecycle.phase == "quarantined"
