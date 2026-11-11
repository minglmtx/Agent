"""Current native supplier input/phase gates; original file claims and fake effects."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.task_preparation_admission import (
    TaskPreparationAuthority as CurrentPreparationAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    require_navigation_native_request,
    NavigationNativeRequestChecks,
)
from map_task_execution_current_fixtures import (
    current_map_execution_case,
    UnitCurrentMapExecutionAuthority,
)
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskPhaseResources,
)
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "which",
    ["normal", "binding", "recovery", "environment", "input", "task", "private-hash"],
)
def test_original_navigation_native_input_and_full_recovery_proof(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as x:
        p, cfg = x.p, x.p.original.resource.spec.configuration
        native = p.source.native
        request = SiteTaskRequest(
            task=p.declaration.scope.task,
            binding_ref=p.declaration.task_binding_ref,
            operation=p.declaration.snapshot_operation,
            action="snapshot",
            private_input=native.private_input_json(),
        )
        binding = native.binding
        recovery = RecoveryPlan.model_validate_json(
            p.original.resource.evidence.read(native.recovery_ref)
        )
        environment = RecoveryPlan.model_validate_json(
            p.original.resource.evidence.read(cfg.token.recovery_ref)
        )
        if which == "binding":
            binding = binding.model_copy(
                update={
                    "identity": binding.identity.model_copy(
                        update={"source_task_id": "other"}
                    )
                }
            )
        elif which == "recovery":
            recovery = recovery.model_copy(update={"restore_component_id": "other"})
        elif which == "environment":
            environment = environment.model_copy(
                update={
                    "owner": environment.owner.model_copy(update={"worker_id": "other"})
                }
            )
        elif which == "input":
            request = request.model_copy(update={"private_input": "{}"})
        elif which == "task":
            request = request.model_copy(
                update={
                    "task": request.task.model_copy(update={"source_task_id": "other"})
                }
            )
        elif which == "private-hash":
            assert cfg.map_inputs is not None
            cfg = cfg.model_copy(
                update={
                    "map_inputs": cfg.map_inputs.model_copy(
                        update={"private_input_sha256": "0" * 64}
                    )
                }
            )
        if which == "normal":
            require_navigation_native_request(
                cfg, request, binding, recovery, environment, None
            )
        else:
            with pytest.raises((OwnershipConflict, ValueError)):
                require_navigation_native_request(
                    cfg, request, binding, recovery, environment, None
                )
        assert p.requests == [] and x.native.loader.session.calls == 0


@pytest.mark.parametrize("bad", [None, {}, [], True, "", 0])
def test_wrong_native_request_type_before_any_fixed_dispatch(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, bad: Any
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as x:
        with pytest.raises((ValueError, OwnershipConflict)):
            x.bundle.native_authority.verify_task(
                x.p.original.resource.spec.configuration, bad, guard()
            )
        assert x.p.requests == [] and x.native.loader.session.calls == 0


@pytest.mark.parametrize(
    "fault", ["intent-producer", "request-mismatch", "source-denied"]
)
def test_current_fixed_client_refuses_before_native_snapshot_and_preserves_original_partial_error(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as x:
        authority = x.bundle.native_authority
        original = authority.verify_task
        calls = []

        def injected(
            configuration: Any, request: SiteTaskRequest, control: Any
        ) -> None:
            calls.append(request.action)
            s = x.bundle.preparation.state
            if fault == "intent-producer":
                assert s.snapshot_request_ref is not None
                s.snapshot_request_ref = s.snapshot_request_ref.model_copy(
                    update={"producer": "unrelated"}
                )
            elif fault == "request-mismatch":
                request = request.model_copy(
                    update={
                        "operation": request.operation.model_copy(
                            update={"operation_id": "new-id"}
                        )
                    }
                )
            else:
                preparation_authority = x.bundle.preparation.authority
                assert isinstance(preparation_authority, CurrentPreparationAuthority)
                rights = preparation_authority.authority
                assert isinstance(rights, ConstructionTaskPhaseResources)
                assert isinstance(rights.authority, UnitCurrentMapExecutionAuthority)
                rights.authority.denied = True
            original(configuration, request, control)

        monkeypatch.setattr(authority, "verify_task", injected)
        with pytest.raises(TaskExecutionUnconfirmed):
            x.bundle.task.execute(x.p.plan.intent, x.p.plan.operation)
        assert calls == ["snapshot"] and x.native.loader.session.calls == 0
        assert x.p.original.worker is not None and x.p.original.worker.tasks is not None
        assert x.p.original.worker.tasks.snapshot is None
        assert x.bundle.preparation.state.snapshot_result is None


@pytest.mark.parametrize("body", [None, b"", b"[]", b"{}", b"null"])
def test_site_input_port_requires_complete_original_snapshot_before_prepare(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes | None
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as x:
        p, cfg = x.p, x.p.original.resource.spec.configuration
        native = p.source.native
        snapshot_request = SiteTaskRequest(
            task=p.declaration.scope.task,
            binding_ref=p.declaration.task_binding_ref,
            operation=p.declaration.snapshot_operation,
            action="snapshot",
            private_input=native.private_input_json(),
        )
        request = snapshot_request.model_copy(
            update={
                "action": "prepare",
                "operation": p.declaration.prepare_operation,
                "snapshot_ref": p.plan.reset_plan_ref.model_copy(
                    update={"content_schema": "map-navigation-snapshot/1"}
                ),
            }
        )
        recovery = RecoveryPlan.model_validate_json(
            p.original.resource.evidence.read(native.recovery_ref)
        )
        environment = RecoveryPlan.model_validate_json(
            p.original.resource.evidence.read(cfg.token.recovery_ref)
        )
        with pytest.raises((OwnershipConflict, ValueError)):
            NavigationNativeRequestChecks().verify_inputs(
                cfg,
                request,
                native.binding,
                recovery,
                environment,
                body,
                snapshot_request,
                guard(),
            )
        assert p.requests == [] and x.native.loader.session.calls == 0
