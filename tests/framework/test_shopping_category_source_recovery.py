"""Actual native producer bodies through source policy and restoration consumer."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_source_records import (
    CategoryNavigationSourceRecordPolicy,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.sites.shopping.tasks.navigation_source_recovery import (
    CategoryNavigationSourceRecoveryChecks,
)
from shopping_category_native_fixtures import worker, request
from test_shopping_category_navigation_input import originals as originals, reference
from test_shopping_order_eta_inputs import reference as evidence_ref
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "snapshot-bytes",
        "snapshot-ref",
        "restore-request",
        "restore-hash",
        "resume-ref",
        "resume-request",
        "resume-hash",
    ],
)
def test_original_source_native_snapshot_restore_resume_lineage_without_reexecution(
    node_path: Path, originals: Any, fault: str
) -> None:
    raw, _, public = originals[0]
    policy = CategoryNavigationSourceRecordPolicy(raw, reference(raw), public)
    checker = CategoryNavigationSourceRecoveryChecks()
    w, commands = worker(node_path)
    try:
        first = request(raw, public)
        snapshot_result = w.execute_task(first, control=guard(60))
        schema, snapshot = policy.snapshot_bytes(first, snapshot_result)
        assert policy.snapshot_bytes(first, snapshot_result) == (schema, snapshot)
        with pytest.raises(OwnershipConflict):
            policy.snapshot_bytes(
                first.model_copy(
                    update={
                        "operation": first.operation.model_copy(
                            update={"operation_id": "foreign"}
                        )
                    }
                ),
                snapshot_result,
            )
        saved = evidence_ref(snapshot, content_schema=schema)
        prepare = request(
            raw,
            public,
            action="prepare",
            operation_id="category-prepare",
            snapshot_ref=saved,
        )
        w.execute_task(prepare, control=guard())
        restore = prepare.model_copy(
            update={
                "action": "restore",
                "operation": prepare.operation.cleanup(
                    "category-restore", now=datetime.now(timezone.utc), seconds=30
                ),
            }
        )
        restored = w.execute_task(restore, control=guard())
        resume = SiteResumeRequest(
            restore_request=restore,
            restore_result_ref=evidence_ref(
                restored.model_dump_json().encode(),
                content_schema=restored.schema_version,
            ),
            operation=restore.operation.cleanup(
                "category-resume", now=datetime.now(timezone.utc), seconds=30
            ),
        )
        resumed = w.resume_frontend(resume, control=guard())
        effects = len(commands.calls)
        current_restore, current_result, body, ref = restore, restored, snapshot, saved
        if fault == "snapshot-bytes":
            body += b" "
        elif fault == "snapshot-ref":
            ref = ref.model_copy(update={"visibility": "public"})
        elif fault == "restore-request":
            current_restore = restore.model_copy(
                update={
                    "operation": restore.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        elif fault == "restore-hash":
            current_result = restored.model_copy(update={"request_sha256": "0" * 64})
        if fault in {
            "snapshot-bytes",
            "snapshot-ref",
            "restore-request",
            "restore-hash",
        }:
            with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
                checker.restore(current_restore, current_result, ref, body, guard())
        else:
            checker.restore(restore, restored, saved, snapshot, guard())
            checker.restore(restore, restored, saved, snapshot, guard())
        if fault == "resume-ref":
            resume = resume.model_copy(
                update={
                    "restore_result_ref": resume.restore_result_ref.model_copy(
                        update={"sha256": "0" * 64}
                    )
                }
            )
        elif fault == "resume-request":
            resume = resume.model_copy(
                update={
                    "operation": resume.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        elif fault == "resume-hash":
            resumed = resumed.model_copy(update={"request_sha256": "0" * 64})
        if fault.startswith("resume-"):
            with pytest.raises(OwnershipConflict):
                checker.resume(resume, resumed, restored, guard())
        else:
            checker.resume(resume, resumed, restored, guard())
            checker.resume(resume, resumed, restored, guard())
        assert len(commands.calls) == effects
    finally:
        w.stop(guard())
