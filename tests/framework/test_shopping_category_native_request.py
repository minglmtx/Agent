"""Original18 bindings and native snapshot/recovery codec; no live dispatch grant."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.sites.shopping.tasks.navigation_native_request import (
    CategoryNavigationNativeRequestChecks,
)
from lab_generate_skill.sites.shopping.tasks.navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
)
from shopping_category_request_fixtures import request_case, saved
from test_shopping_category_navigation_input import originals as originals
from test_shopping_order_eta_inputs import reference
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_all18_pending_first_snapshot_then_exact_original_prepare_restore_and_repeat(
    node_path: Path, originals: Any
) -> None:
    checker = CategoryNavigationNativeRequestChecks()
    for raw, _, public in originals:
        c = request_case(node_path / public.identity.source_task_id, raw, public)
        try:
            before = len(c.commands.calls)
            checker.verify_inputs(
                c.configuration,
                c.first,
                c.binding,
                c.recovery,
                c.environment,
                None,
                None,
                guard(),
            )
            assert len(c.commands.calls) == before
            prepare, body = saved(c)
            restore = prepare.model_copy(
                update={
                    "action": "restore",
                    "operation": prepare.operation.cleanup(
                        "category-restore", now=datetime.now(timezone.utc), seconds=30
                    ),
                }
            )
            before = len(c.commands.calls)
            for action in (prepare, restore, prepare):
                checker.verify_inputs(
                    c.configuration,
                    action,
                    c.binding,
                    c.recovery,
                    c.environment,
                    body,
                    c.first,
                    guard(),
                )
            assert len(c.commands.calls) == before
        finally:
            c.worker.stop(guard())


@pytest.mark.parametrize(
    "fault",
    [
        "private_hash",
        "private_size",
        "private_schema",
        "private_visibility",
        "private_media",
        "private_whitespace",
        "owner",
        "attempt",
        "site",
        "image",
        "family",
        "task_component",
        "coverage",
        "environment_scope",
        "environment_component",
        "baseline",
        "snapshot_corrupt",
        "snapshot_input",
        "snapshot_files",
        "snapshot_noncanonical",
        "snapshot_missing",
        "prior_on_first",
        "cancel",
        "inspect",
    ],
)
def test_changed_binding_snapshot_full_recovery_or_cancel_refused_without_effects(
    node_path: Path, originals: Any, fault: str
) -> None:
    raw, _, public = originals[0]
    c = request_case(node_path, raw, public)
    try:
        request, body = saved(c)
        config, binding, recovery, environment = (
            c.configuration,
            c.binding,
            c.recovery,
            c.environment,
        )
        prior = c.first
        if fault.startswith("private_") and fault != "private_whitespace":
            key, value = {
                "private_hash": ("sha256", "0" * 64),
                "private_size": ("size_bytes", 1),
                "private_schema": ("content_schema", "other/1"),
                "private_visibility": ("visibility", "public"),
                "private_media": ("media_type", "text/plain"),
            }[fault]
            binding = binding.model_copy(
                update={
                    "private_spec_ref": binding.private_spec_ref.model_copy(
                        update={key: value}
                    )
                }
            )
        if fault == "private_whitespace":
            request = request.model_copy(
                update={"private_input": request.private_input + " "}
            )
        if fault in ("owner", "attempt"):
            request = request.model_copy(
                update={
                    "operation": request.operation.model_copy(
                        update={
                            "owner_id" if fault == "owner" else "attempt_id": "foreign"
                        }
                    )
                }
            )
        if fault == "site":
            config = config.model_copy(update={"site_id": "shopping_admin"})
        if fault == "image":
            config = config.model_copy(
                update={
                    "files": config.files.model_copy(
                        update={
                            "image": config.files.image.model_copy(
                                update={"sha256": "0" * 64}
                            )
                        }
                    )
                }
            )
        if fault == "family":
            request = request.model_copy(
                update={
                    "task": request.task.model_copy(
                        update={"family": "recorded_order_eta"}
                    )
                }
            )
        if fault == "task_component":
            recovery = recovery.model_copy(
                update={"restore_component_id": "shopping-order-eta"}
            )
        if fault == "coverage":
            recovery = recovery.model_copy(update={"state_coverage": ("partial",)})
        if fault == "environment_scope":
            environment = environment.model_copy(update={"attempt_id": "attempt"})
        if fault == "environment_component":
            environment = environment.model_copy(
                update={"restore_component_id": "other"}
            )
        if fault == "baseline":
            binding = binding.model_copy(
                update={
                    "baseline_ref": binding.baseline_ref.model_copy(
                        update={"producer": "other"}
                    )
                }
            )
        if fault == "snapshot_corrupt":
            body = b"{}"
        if fault == "snapshot_noncanonical":
            body += b" "
        if fault in ("snapshot_files", "snapshot_input"):
            snapshot = CategoryNavigationRecoverySnapshot.model_validate_json(body)
            if fault == "snapshot_files":
                snapshot = snapshot.model_copy(
                    update={
                        "state": snapshot.state.model_copy(
                            update={
                                "service": snapshot.state.service.model_copy(
                                    update={
                                        "files": snapshot.state.service.files.model_copy(
                                            update={"instance_id": "other"}
                                        )
                                    }
                                )
                            }
                        )
                    }
                )
            else:
                snapshot = snapshot.model_copy(
                    update={
                        "request": snapshot.request.model_copy(
                            update={
                                "binding_ref": snapshot.request.binding_ref.model_copy(
                                    update={"producer": "other"}
                                )
                            }
                        )
                    }
                )
            body = snapshot.model_dump_json().encode()
            request = request.model_copy(
                update={
                    "snapshot_ref": reference(
                        body, content_schema=snapshot.schema_version
                    )
                }
            )
        if fault == "prior_on_first":
            request = c.first
        if fault == "inspect":
            request = request.model_copy(update={"action": "inspect"})

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "category-native-input")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        before = len(c.commands.calls)
        with pytest.raises((ValueError, OwnershipConflict, OperationStopped)):
            CategoryNavigationNativeRequestChecks().verify_inputs(
                config,
                request,
                binding,
                recovery,
                environment,
                None if fault == "snapshot_missing" else body,
                prior,
                Cancel() if fault == "cancel" else guard(),
            )
        assert len(c.commands.calls) == before
    finally:
        c.worker.stop(guard())


@pytest.mark.parametrize("invalid", [None, {}, [], "", False])
def test_wrong_configuration_type_refused_before_control_or_native(
    invalid: Any,
) -> None:
    class NoControl:
        def checkpoint(self) -> float:
            raise AssertionError("Invalid input reached control")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    bad: Any = None
    with pytest.raises((ValueError, TypeError)):
        CategoryNavigationNativeRequestChecks().verify_inputs(
            invalid, bad, bad, bad, bad, bad, bad, NoControl()
        )
