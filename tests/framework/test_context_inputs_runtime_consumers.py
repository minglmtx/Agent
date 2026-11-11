"""Exact outer consumer and retained real close producer; no new website task."""

import json
from pathlib import Path
from typing import Any
import pytest
import production_runtime as runtime
import production_task_plan as map_plan
import admin_production_task_plan as admin_plan
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
P = W / "experiments/framework-combined-release-20261030-v1"
MP = W / "experiments/framework-map-navigation42-production-20261102-v1"
AP = W / "experiments/framework-admin-navigation-production-20261102-v1"


def test_actual_isolated_consumers_and_original_family_budgets() -> None:
    assert Path(runtime.__file__).parent == MP / "runtime-context-inputs-candidate"
    assert Path(map_plan.__file__).parent == MP / "runtime-context-inputs-candidate"
    assert Path(admin_plan.__file__).parent == AP / "runtime-context-inputs-candidate"
    assert not (AP / "runtime-context-inputs-candidate/production_runtime.py").exists()
    for package in (MP, AP):
        current = package / "runtime-context-inputs-candidate"
        original = package / "runtime-source-admission-handoff-candidate"
        for name in (
            "entry-budgets.json",
            "job-budgets.json",
            "source-recovery-budgets.json",
        ):
            assert (current / name).read_bytes() == (original / name).read_bytes()
        job = OperationWindowBudgets.model_validate_json(
            (current / "job-budgets.json").read_bytes()
        )
        recovery = SourceRecoveryBudgets.model_validate_json(
            (current / "source-recovery-budgets.json").read_bytes()
        )
        assert recovery.complete_recovery_path_seconds <= job.cleanup_seconds
        assert job.execution_seconds > 0


@pytest.mark.parametrize("fault", ["none", "revoke", "write", "both"])
def test_retained_actual_physical_observation_reaches_outer_result_without_clean_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    actual = json.loads(
        (
            P / "context-inputs-check-4923642/site-storage-loss-original-close.json"
        ).read_bytes()
    )
    original = OSError("Original initialization/storage failure")
    setattr(
        original, "site_resource_physical_observation", actual["physical_observation"]
    )
    combined = BaseExceptionGroup(
        "Original task and cleanup", [original, InvalidCleanup()]
    )
    output = tmp_path / "output"
    output.mkdir()
    facts: dict[str, Any] = {"formal_training_qualification": False}
    revoked: list[bool] = []

    def revoke() -> None:
        revoked.append(True)
        if fault in ("revoke", "both"):
            raise OSError("Original revoke failed")

    if fault in ("write", "both"):

        original_write = Path.write_text

        def failed_write(path: Path, *args: Any, **kwargs: Any) -> Any:
            if path == output / "member-result.json":
                raise OSError("Original result write failed")
            return original_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", failed_write)
    if fault == "none":
        runtime.finish_member_metadata(output, facts, revoke, combined)
        saved = json.loads((output / "member-result.json").read_bytes())
        assert saved == facts
    else:
        with pytest.raises(BaseExceptionGroup) as caught:
            runtime.finish_member_metadata(output, facts, revoke, combined)
        assert caught.value.exceptions[0] is combined
        assert len(caught.value.exceptions) == (3 if fault == "both" else 2)
    assert revoked == [True]
    assert facts["site_resource_physical_observations"] == [
        actual["physical_observation"]
    ]
    assert not facts["site_resource_physical_observations"][0][
        "durable_resource_close_confirmed"
    ]
    assert not facts["formal_training_qualification"]


class InvalidCleanup(RuntimeError):
    pass


def test_observation_traversal_handles_duplicate_links_and_has_finite_bound() -> None:
    leaf = OSError("physical close recording failed")
    setattr(
        leaf,
        "site_resource_physical_observation",
        {"durable_resource_close_confirmed": False},
    )
    root = BaseExceptionGroup("same original primary twice", [leaf, leaf])
    values, truncated = runtime.original_site_close_observations(root)
    assert values == [{"durable_resource_close_confirmed": False}] and not truncated
    current: BaseException = root
    for _ in range(130):
        parent = RuntimeError("retained linked error")
        parent.__cause__ = current
        current = parent
    _, truncated = runtime.original_site_close_observations(current)
    assert truncated
