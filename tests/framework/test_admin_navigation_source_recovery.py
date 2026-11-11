"""Source lineage with original full-state codecs; service/kernel are synthetic."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.sites.shopping_admin.tasks.navigation_source_recovery import (
    NavigationSourceRecoveryChecks,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.errors import OwnershipConflict
from admin_navigation_state_fixtures import qualified
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault", ["none", "restore-result", "snapshot", "resume-result", "restored-bytes"]
)
def test_original_navigation_restore_resume_lineage_keeps_full_reset_checks(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as q:
        store, reset = q["store"], q["reset"]
        request = SiteTaskRequest.model_validate_json(
            store.read(reset.restore_request_ref)
        )
        restored = SiteTaskResult.model_validate_json(
            store.read(reset.restore_result_ref)
        )
        resumed = SiteResumeResult.model_validate_json(
            store.read(reset.resume_result_ref)
        )
        codec = NavigationSourceRecoveryChecks()
        snapshot_ref = q["environment"].snapshot_ref
        raw = q["snapshot"].model_dump_json().encode()
        if fault in ("restore-result", "snapshot"):
            if fault == "restore-result":
                restored = restored.model_copy(update={"request_sha256": "0" * 64})
            else:
                snapshot_ref = snapshot_ref.model_copy(
                    update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
                )
            with pytest.raises(OwnershipConflict):
                codec.restore(request, restored, snapshot_ref, raw, guard(30))
            return
        codec.restore(request, restored, snapshot_ref, raw, guard(30))
        if fault != "none":
            if fault == "resume-result":
                resumed = resumed.model_copy(update={"request_sha256": "0" * 64})
            else:
                restored = restored.model_copy(
                    update={"private_result": restored.private_result + " "}
                )
            with pytest.raises(OwnershipConflict):
                codec.resume(q["resume"], resumed, restored, guard(30))
            return
        codec.resume(q["resume"], resumed, restored, guard(30))
        qualified_reset = q["records"].publish_reset_facts(
            q["reset_ref"], q["reset_op"]
        )
        assert qualified_reset.task.checks.status == "pass"
        assert qualified_reset.environment.checks.status == "pass"
        assert qualified_reset.health.checks.status == "pass"
        assert qualified_reset.task.checks.required == (
            "admin.database.restored",
            "admin.artifacts.restored",
            "admin.cache.cleared",
            "admin.search.restored",
        )
