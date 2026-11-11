"""Task-specific leaf on actual linked CAS descriptors; no dispatch permission.

The original source/task authority retains its independent pending-intent,
caller, physical resource, single-dispatch and closed-browser checks.
"""

from pathlib import Path
from typing import Any
from datetime import datetime, timezone
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.sites.shopping_admin.tasks.navigation_native_request import (
    NavigationNativeRequestChecks,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from admin_navigation_state_fixtures import qualified
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


@pytest.mark.parametrize("action", ["snapshot", "prepare", "restore"])
def test_current_native_checks_bind_original_navigation_and_full_recovery(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    action: str,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as q:
        snapshot, store = q["snapshot"], q["store"]
        original = snapshot.request
        config = q["c"].spec.configuration
        binding = TaskBinding.model_validate_json(store.read(original.binding_ref))
        recovery = RecoveryPlan.model_validate_json(
            store.read(original.operation.recovery_ref)
        )
        environment = RecoveryPlan.model_validate_json(
            store.read(config.token.recovery_ref)
        )
        req = original
        if action != "snapshot":
            req = original.model_copy(
                update={
                    "action": action,
                    "snapshot_ref": put(store, snapshot),
                    "operation": (
                        original.operation.model_copy(
                            update={"operation_id": "prepare-original"}
                        )
                        if action == "prepare"
                        else original.operation.cleanup(
                            "restore-original",
                            now=datetime.now(timezone.utc),
                            seconds=30,
                        )
                    ),
                }
            )
        NavigationNativeRequestChecks().verify_inputs(
            config,
            req,
            binding,
            recovery,
            environment,
            None if action == "snapshot" else snapshot.model_dump_json().encode(),
            None if action == "snapshot" else original,
            guard(),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "binding",
        "recovery",
        "coverage",
        "environment",
        "private",
        "snapshot_request",
        "snapshot_bytes",
        "legacy_no_contents",
        "site_image",
        "supplied_snapshot_on_first",
    ],
)
def test_mixed_scope_pin_or_incomplete_original_snapshot_refused(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    with qualified(tmp_path, node_path, monkeypatch, contracts) as q:
        saved, store = q["snapshot"], q["store"]
        original, config = saved.request, q["c"].spec.configuration
        binding = TaskBinding.model_validate_json(store.read(original.binding_ref))
        recovery = RecoveryPlan.model_validate_json(
            store.read(original.operation.recovery_ref)
        )
        environment = RecoveryPlan.model_validate_json(
            store.read(config.token.recovery_ref)
        )
        req = original.model_copy(
            update={
                "action": "prepare",
                "snapshot_ref": put(store, saved),
                "operation": original.operation.model_copy(
                    update={"operation_id": "prepare-original"}
                ),
            }
        )
        raw, first = saved.model_dump_json().encode(), original
        if fault == "binding":
            binding = binding.model_copy(
                update={
                    "private_spec_ref": binding.private_spec_ref.model_copy(
                        update={"sha256": "0" * 64}
                    )
                }
            )
        elif fault in ("recovery", "coverage"):
            recovery = recovery.model_copy(
                update=(
                    {"restore_component_id": "admin-product"}
                    if fault == "recovery"
                    else {"state_coverage": ("admin.database.restored",)}
                )
            )
        elif fault == "environment":
            environment = environment.model_copy(update={"attempt_id": "attempt"})
        elif fault == "private":
            inputs = NavigationExecutionInput.model_validate_json(req.private_input)
            req = req.model_copy(
                update={
                    "private_input": inputs.model_copy(
                        update={
                            "spec": inputs.spec.model_copy(update={"label": "changed"})
                        }
                    ).model_dump_json()
                }
            )
        elif fault == "snapshot_request":
            first = first.model_copy(
                update={
                    "operation": first.operation.model_copy(
                        update={"operation_id": "other"}
                    )
                }
            )
        elif fault == "snapshot_bytes":
            raw = b"{}"
        elif fault == "legacy_no_contents":
            saved = saved.model_copy(update={"contents": None})
            raw = saved.model_dump_json().encode()
            req = req.model_copy(update={"snapshot_ref": put(store, saved)})
        elif fault == "site_image":
            config = config.model_copy(
                update={
                    "files": config.files.model_copy(
                        update={
                            "image": config.files.image.model_copy(
                                update={"sha256": "f" * 64}
                            )
                        }
                    )
                }
            )
        else:
            req = original
        with pytest.raises((OwnershipConflict, ValueError)):
            NavigationNativeRequestChecks().verify_inputs(
                config, req, binding, recovery, environment, raw, first, guard()
            )
