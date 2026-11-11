"""All category bindings through real native lifecycle with synthetic effects."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance
from lab_generate_skill.sites.shopping.tasks.navigation_lifecycle import (
    CategoryNavigationLifecycle,
)
from lab_generate_skill.sites.shopping.tasks.navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
    CategoryNavigationRestored,
    CategoryNavigationResumed,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationState,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_programs import RECORDED_ETA
from lab_generate_skill.sites.shopping.tasks.order_eta_lifecycle import (
    OrderEtaLifecycle,
)
from shopping_category_native_fixtures import worker, request
from shopping_task_fixtures import case, request as eta_request
from test_shopping_category_navigation_input import originals as originals
from test_shopping_order_eta_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def snapshot(
    w: ShoppingWorkerInstance, raw: bytes, public: Any
) -> tuple[SiteTaskRequest, EvidenceRef]:
    first = request(raw, public)
    result = w.execute_task(first, control=guard(60))
    saved = CategoryNavigationRecoverySnapshot.model_validate_json(
        result.private_result
    )
    assert saved.request == first
    return first, reference(
        result.private_result.encode(), content_schema=saved.schema_version
    )


def prepare(w: ShoppingWorkerInstance, raw: bytes, public: Any) -> SiteTaskRequest:
    _, ref = snapshot(w, raw, public)
    first = request(
        raw, public, action="prepare", operation_id="category-prepare", snapshot_ref=ref
    )
    observed = CategoryNavigationState.model_validate_json(
        w.execute_task(first, control=guard()).private_result
    )
    assert observed.task == first.task
    assert isinstance(w.tasks, CategoryNavigationLifecycle) and w.tasks.snapshot
    assert observed.protected == w.tasks.snapshot.protected
    return first


def restoration(first: SiteTaskRequest) -> SiteTaskRequest:
    return first.model_copy(
        update={
            "action": "restore",
            "operation": first.operation.cleanup(
                "category-restore", now=datetime.now(timezone.utc), seconds=30
            ),
        }
    )


def resume_request(
    restored: SiteTaskRequest, result: SiteTaskResult
) -> SiteResumeRequest:
    return SiteResumeRequest(
        restore_request=restored,
        restore_result_ref=reference(
            result.model_dump_json().encode(), content_schema=result.schema_version
        ),
        operation=restored.operation.cleanup(
            "category-resume", now=datetime.now(timezone.utc), seconds=30
        ),
    )


def test_all18_parameters_original_worker_snapshot_capture_restore_resume(
    node_path: Path, originals: Any
) -> None:
    for raw, _, public in originals:
        root = node_path / public.identity.source_task_id
        w, commands = worker(root)
        first = prepare(w, raw, public)
        assert isinstance(w.tasks, CategoryNavigationLifecycle)
        inspection = first.model_copy(
            update={
                "action": "inspect",
                "operation": first.operation.model_copy(
                    update={"operation_id": "category-capture"}
                ),
            }
        )
        capture = SiteCaptureRequest(
            inspection=inspection,
            collector_id="shopping-category-navigation",
            collector_version="1",
        )
        actual = w.capture_task(capture, control=guard())
        assert actual.request_sha256 == capture.digest
        assert (
            CategoryNavigationState.model_validate_json(actual.private_result).task
            == public.identity
        )
        close = restoration(first)
        result = w.execute_task(close, control=guard())
        restored = CategoryNavigationRestored.model_validate_json(result.private_result)
        assert restored.inventory == restored.snapshot.state.inventory
        observed = CategoryNavigationResumed.model_validate_json(
            w.resume_frontend(
                resume_request(close, result), control=guard()
            ).private_result
        )
        assert observed.protected == restored.snapshot.protected
        assert w.instance.state == "resumed" and not commands.initialized
        assert not any(RECORDED_ETA in call for call in commands.calls)
        calls = len(commands.calls)
        for repeat in (first, close, inspection):
            with pytest.raises(InvalidTransition):
                w.execute_task(repeat, control=guard())
        with pytest.raises(RuntimeError):
            w.resume_frontend(resume_request(close, result), control=guard())
        assert len(commands.calls) == calls
        w.stop(guard())


@pytest.mark.parametrize(
    "change",
    ["binding", "snapshot", "private", "owner", "allocation", "attempt", "recovery"],
)
def test_changed_scope_refused_before_native_call(
    node_path: Path, originals: Any, change: str
) -> None:
    raw, _, public = originals[0]
    w, commands = worker(node_path)
    _, ref = snapshot(w, raw, public)
    first = request(
        raw, public, action="prepare", operation_id="category-prepare", snapshot_ref=ref
    )
    if change == "binding":
        first = first.model_copy(
            update={
                "binding_ref": first.binding_ref.model_copy(
                    update={"producer": "other"}
                )
            }
        )
    elif change == "snapshot":
        first = first.model_copy(
            update={"snapshot_ref": ref.model_copy(update={"sha256": "0" * 64})}
        )
    elif change == "private":
        first = first.model_copy(
            update={
                "private_input": first.private_input.replace(
                    '"heading_regex":', '"wrong_heading":'
                )
            }
        )
    else:
        key = {
            "owner": "owner_id",
            "allocation": "allocation_id",
            "attempt": "attempt_id",
            "recovery": "recovery_ref",
        }[change]
        assert first.operation.recovery_ref is not None
        value = (
            first.operation.recovery_ref.model_copy(update={"producer": "other"})
            if change == "recovery"
            else "other"
        )
        first = first.model_copy(
            update={"operation": first.operation.model_copy(update={key: value})}
        )
    count = len(commands.calls)
    with pytest.raises((OwnershipConflict, ValueError)):
        w.execute_task(first, control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "change", ["core", "sales_order", "customer_entity", "quote", "review"]
)
def test_preparation_refuses_protected_changes(
    node_path: Path, originals: Any, change: str
) -> None:
    raw, _, public = originals[0]
    w, commands = worker(node_path)
    _, ref = snapshot(w, raw, public)
    if change == "core":
        commands.changed_core = True
    else:
        commands.changed_table = change
    first = request(
        raw, public, action="prepare", operation_id="category-prepare", snapshot_ref=ref
    )
    with pytest.raises(OwnershipConflict):
        w.execute_task(first, control=guard())
    assert w.tasks and w.tasks.phase == "quarantined"
    count = len(commands.calls)
    with pytest.raises(InvalidTransition):
        w.execute_task(first, control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize(
    "moment", ["before_measure", "after_measure", "after_restore", "resume_measure"]
)
def test_partial_failure_never_replays_native_operation(
    node_path: Path, originals: Any, monkeypatch: pytest.MonkeyPatch, moment: str
) -> None:
    raw, _, public = originals[0]
    w, commands = worker(node_path)
    _, ref = snapshot(w, raw, public)
    assert isinstance(w.tasks, CategoryNavigationLifecycle)
    first = request(
        raw, public, action="prepare", operation_id="category-prepare", snapshot_ref=ref
    )
    protected = w.tasks.native.protected

    def broken(control: Any) -> Any:
        if moment != "before_measure":
            protected(control)
        raise TimeoutError("original native reply unconfirmed")

    if moment in ("before_measure", "after_measure"):
        monkeypatch.setattr(w.tasks.native, "protected", broken)
        with pytest.raises(TimeoutError):
            w.execute_task(first, control=guard())
        assert (
            w.tasks.native.initialization_attempted and w.tasks.phase == "quarantined"
        )
        count = len(commands.calls)
        with pytest.raises(InvalidTransition):
            w.execute_task(first, control=guard())
    else:
        w.execute_task(first, control=guard())
        close = restoration(first)
        if moment == "after_restore":
            restore = w.instance.restore

            def broken_restore(snapshot: Any, control: Any) -> Any:
                restore(snapshot, control)
                raise TimeoutError("original restore reply unconfirmed")

            monkeypatch.setattr(w.instance, "restore", broken_restore)
            with pytest.raises(TimeoutError):
                w.execute_task(close, control=guard())
            assert w.tasks.phase == "quarantined" and w.tasks.restore_result is None
            count = len(commands.calls)
            with pytest.raises(InvalidTransition):
                w.execute_task(close, control=guard())
        else:
            restored = w.execute_task(close, control=guard())
            monkeypatch.setattr(w.tasks.native, "protected", broken)
            resume = resume_request(close, restored)
            with pytest.raises(TimeoutError):
                w.resume_frontend(resume, control=guard())
            assert w.resumption is not None and w.resumption.attempted
            count = len(commands.calls)
            with pytest.raises(RuntimeError):
                w.resume_frontend(resume, control=guard())
    assert len(commands.calls) == count


@pytest.mark.parametrize("when", ["before", "after_measure"])
def test_cancel_boundaries_retain_once_and_snapshot(
    node_path: Path, originals: Any, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    raw, _, public = originals[0]
    w, commands = worker(node_path)
    _, ref = snapshot(w, raw, public)
    assert isinstance(w.tasks, CategoryNavigationLifecycle)
    first = request(
        raw, public, action="prepare", operation_id="category-prepare", snapshot_ref=ref
    )
    from types import SimpleNamespace

    stopped = when == "before"

    def checkpoint() -> None:
        if stopped:
            raise OSError("cancelled")

    protected = w.tasks.native.protected

    def measured(control: Any) -> Any:
        nonlocal stopped
        result = protected(control)
        stopped = True
        return result

    monkeypatch.setattr(w.tasks.native, "protected", measured)
    from typing import cast

    with pytest.raises(OSError):
        w.execute_task(first, control=cast(Any, SimpleNamespace(checkpoint=checkpoint)))
    assert w.tasks.snapshot is not None
    assert w.tasks.native.initialization_attempted == (when == "after_measure")
    assert w.tasks.phase == (
        "quarantined" if when == "after_measure" else "snapshotted"
    )


@pytest.mark.parametrize("family", ["unknown", "recorded_order_eta"])
def test_actual_selector_rejects_unknown_and_preserves_eta(
    node_path: Path, family: str
) -> None:
    original, commands, _ = case(node_path)
    w = ShoppingWorkerInstance(
        original.instance, lambda control: "unit@example.invalid"
    )
    first = eta_request()
    if family == "unknown":
        first = first.model_copy(
            update={"task": first.task.model_copy(update={"family": "unknown"})}
        )
        count = len(commands.calls)
        with pytest.raises(ValueError):
            w.execute_task(first, control=guard())
        assert w.tasks is None and len(commands.calls) == count
    else:
        w.execute_task(first, control=guard())
        assert isinstance(w.tasks, OrderEtaLifecycle)
