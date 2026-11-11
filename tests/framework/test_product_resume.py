"""Original worker-local restore facts are required before frontend resume."""

from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import pytest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping_admin.worker_instance import AdminWorkerInstance
from lab_generate_skill.sites.shopping_admin.tasks.product_lifecycle import (
    AdminProductLifecycle,
)
from lab_generate_skill.sites.shopping_admin.frontend_recovery_contract import (
    AdminFrontendRecovered,
)
from test_frontend_recovery_instance import ready
from site_instance_fixtures import node_path as node_path
from test_product_recovery_rpc import Commands, prepare, cleanup
from test_admin_description_inputs import reference
from test_slurm_commands import guard


def completed(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    site, _, _, group = ready(root, monkeypatch)
    assert site.spec is not None and site.services is not None
    stopped = site.services.frontend.result
    assert stopped is not None
    lifecycle = AdminProductLifecycle(site.spec, Commands(), lambda control: stopped)
    prepared = prepare(lifecycle)
    restore = cleanup(prepared, prepared.snapshot_ref)
    result = lifecycle.execute_task(restore, control=guard())
    request = SiteResumeRequest(
        restore_request=restore,
        restore_result_ref=reference(
            result.model_dump_json().encode(), content_schema=result.schema_version
        ),
        operation=restore.operation.cleanup(
            "resume-original", now=datetime.now(timezone.utc), seconds=30
        ),
    )
    worker = AdminWorkerInstance(site)
    worker.tasks = lifecycle
    return worker, request, group


def test_same_worker_resumes_actual_retained_restore_once(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, request, group = completed(node_path, monkeypatch)
    result = worker.resume_frontend(request, control=guard())
    facts = AdminFrontendRecovered.model_validate_json(result.private_result)
    assert result.request_sha256 == request.digest and facts.frontend_ready
    assert worker.instance.state == "recovered" and worker.tasks.phase == "restored"
    with pytest.raises(RuntimeError):
        worker.resume_frontend(request, control=guard())
    with pytest.raises(RuntimeError):
        worker.execute_task(request.restore_request, control=guard())
    assert len(group.names) == 7
    assert len(worker.stop(guard())) == 7


@pytest.mark.parametrize(
    "fault", ["result", "original_request", "phase", "missing_result", "missing_task"]
)
def test_unconfirmed_or_foreign_original_restore_cannot_resume(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    worker, request, group = completed(node_path, monkeypatch)
    if fault == "result":
        request = request.model_copy(
            update={
                "restore_result_ref": request.restore_result_ref.model_copy(
                    update={"sha256": "f" * 64}
                )
            }
        )
    if fault == "original_request":
        request = request.model_copy(
            update={
                "restore_request": request.restore_request.model_copy(
                    update={
                        "binding_ref": request.restore_request.binding_ref.model_copy(
                            update={"sha256": "f" * 64}
                        )
                    }
                )
            }
        )
    if fault == "phase":
        worker.tasks.phase = "quarantined"
    if fault == "missing_result":
        worker.tasks.restore_result = None
    if fault == "missing_task":
        worker.tasks = None
    with pytest.raises((RuntimeError, OwnershipConflict)):
        worker.resume_frontend(request, control=guard())
    assert len(group.names) == 5
    worker.stop(guard())


def test_partial_resume_failure_retains_original_worker_and_stops_all(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker, request, group = completed(node_path, monkeypatch)
    group.fail = "nginx-restored"
    with pytest.raises(OSError):
        worker.resume_frontend(request, control=guard())
    assert worker.instance.state == "failed"
    assert worker.resumption is not None and worker.resumption.attempted
    with pytest.raises(RuntimeError):
        worker.resume_frontend(request, control=guard())
    assert len(worker.stop(guard())) == 7
