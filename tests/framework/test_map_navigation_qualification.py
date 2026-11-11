"""Navigation8 complete current environment/reset proof, native/kernel doubles."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.sites.map.tasks.state_policy import map_initial_spec
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationResumed
from map_navigation_group_cases import SOURCES
from map_qualification_fixtures import qualified, restore
from map_registered_worker_fixtures import RegisteredMapCase
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_site_resource import inspect
from test_slurm_commands import guard


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_current_Task_preparation_environment_restore_resume_safe_reset_and_closed_read(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    original = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with qualified(original, monkeypatch) as c:
            assert c.preparation.environment.checks.status == "pass"
            selected = restore(c)
            reference = put(original.resource.evidence, selected)
            before = len(original.sql.calls)
            checks = c.qualifications.checks.reset(selected, reference, guard())
            assert (
                checks.task.status
                == checks.environment.status
                == checks.health.status
                == "pass"
            )
            assert checks.task_recovery.restore_component_id == "map-native-navigation"
            op = c.preparation.request.operation.cleanup(
                "navigation-reset", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": c.plan.environment_recovery_ref})
            facts = c.qualifications.publish_reset_facts(reference, op)
            assert (
                assemble_reset(
                    facts,
                    op.model_copy(update={"operation_id": "assemble-navigation-reset"}),
                ).status
                == "safe"
            )
            assert len(original.sql.calls) == before
            assert original.worker is not None and original.worker.references is None
            records = c.qualifications
        assert inspect(original.resource).state == "closed" and original.worker.closed
        original.observer = "controller"
        assert records.checks.reset(selected, reference, guard()) == checks
        assert len(original.sql.calls) == before
    finally:
        original.close_sockets()


@pytest.mark.parametrize(
    "fault", ["coverage", "snapshot", "scope", "private", "cancel"]
)
def test_navigation_environment_cannot_move_original_baseline_or_scope(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    original = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(original, monkeypatch) as c:
            store = original.resource.evidence
            env = c.environment
            if fault == "coverage":
                bad = map_initial_spec(
                    original.scope.task, original.private.native_contract_ref.sha256
                ).model_copy(update={"environment_checks": ("narrow",)})
                env = env.model_copy(update={"spec_ref": put(store, bad)})
            if fault == "snapshot":
                env = env.model_copy(
                    update={"snapshot_ref": put(store, c.preparation.observed)}
                )
            if fault == "scope":
                env = env.model_copy(
                    update={
                        "scope": env.scope.model_copy(update={"context_id": "foreign"})
                    }
                )
            if fault == "private":
                bad_private = original.private.model_copy(
                    update={
                        "native_contract_ref": original.private.native_contract_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
                binding = c.preparation.records.reader.load(
                    c.preparation.publication.selection,
                    c.preparation.request.operation,
                    guard(),
                ).binding
                binding = binding.model_copy(
                    update={"private_spec_ref": put(store, bad_private)}
                )
                snapshot = c.preparation.snapshot.model_copy(
                    update={
                        "request": c.preparation.snapshot.request.model_copy(
                            update={"binding_ref": put(store, binding)}
                        )
                    }
                )
                env = env.model_copy(update={"snapshot_ref": put(store, snapshot)})

            class Cancel:
                def checkpoint(self) -> float:
                    raise OperationStopped("CANCELLED", "navigation-environment")

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            original.observer = "controller"
            before = len(original.sql.calls)
            with pytest.raises(
                (ValueError, EvidenceError, OwnershipConflict, OperationStopped)
            ):
                c.qualifications.checks.environment(
                    env,
                    put(store, env),
                    c.preparation.environment.operation,
                    Cancel() if fault == "cancel" else guard(),
                )
            assert len(original.sql.calls) == before
    finally:
        original.close_sockets()


@pytest.mark.parametrize(
    "fault", ["closure", "concrete-tag", "resume-digest", "recovery", "cancel"]
)
def test_navigation_reset_requires_same_original_closed_browser_restore_and_resume(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    original = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(original, monkeypatch) as c:
            store = original.resource.evidence
            selected = restore(c)
            if fault == "closure":
                closure = ClosureReceipt.model_validate_json(
                    store.read(selected.closure_refs[0])
                )
                closure = closure.model_copy(update={"status": "quarantined"})
                selected = selected.model_copy(
                    update={"closure_refs": (put(store, closure),)}
                )
            if fault in ("concrete-tag", "resume-digest"):
                result = SiteResumeResult.model_validate_json(
                    store.read(selected.resume_result_ref)
                )
                if fault == "resume-digest":
                    result = result.model_copy(update={"request_sha256": "f" * 64})
                else:
                    native = NavigationResumed.model_validate_json(
                        result.private_result
                    )
                    native = native.model_copy(
                        update={"schema_version": "map-overlay-resumed/1"}
                    )
                    result = result.model_copy(
                        update={"private_result": native.model_dump_json()}
                    )
                selected = selected.model_copy(
                    update={"resume_result_ref": put(store, result)}
                )
            if fault == "recovery":
                plan = c.plan.model_copy(
                    update={"task_recovery_ref": c.plan.environment_recovery_ref}
                )
                selected = selected.model_copy(update={"plan_ref": put(store, plan)})

            class Cancel:
                def checkpoint(self) -> float:
                    raise OperationStopped("CANCELLED", "navigation-reset")

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            before = len(original.sql.calls)
            with pytest.raises(
                (ValueError, EvidenceError, OwnershipConflict, OperationStopped)
            ):
                c.qualifications.checks.reset(
                    selected,
                    put(store, selected),
                    Cancel() if fault == "cancel" else guard(),
                )
            assert len(original.sql.calls) == before
    finally:
        original.close_sockets()


@pytest.mark.parametrize("value", [None, "", False, {}, []])
def test_navigation_state_policy_illegal_input_never_grants_coverage(
    value: Any,
) -> None:
    with pytest.raises(ValueError):
        map_initial_spec(value)
