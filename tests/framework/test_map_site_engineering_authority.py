"""Selected live-source admission over original records; native/kernel are doubles."""

from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from map_site_engineering_authority import MapEngineeringAuthority
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import qualified
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_exact_source_recovery_snapshot_and_no_permission_from_repeated_read(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = registered_map
    with qualified(original, monkeypatch) as q:
        c, cfg = original.resource, original.configuration
        authority = MapEngineeringAuthority(c, Path(cfg.files.node_root).parent)
        authority.task_input = original.private.model_dump_json()
        request = original.request("inspect", "selected-admission")
        authority.task_intents[request.operation.operation_id] = put(
            c.evidence, request
        )
        with pytest.raises(OwnershipConflict):
            authority.verify_task(cfg, request, guard())
        authority.before_native = True  # Explicit unit-only already-acquired premise.
        before = len(original.case.commands.calls)
        authority.verify_task(cfg, request, guard())
        authority.verify_task(cfg, request, guard())
        with pytest.raises(OperationStopped):
            authority.verify_task(cfg, request, guard(-1))
        for change in (
            {"attempt_id": "other"},
            {"recovery_ref": cfg.token.recovery_ref},
            {"operation_id": "unrecorded"},
        ):
            wrong = request.model_copy(
                update={"operation": request.operation.model_copy(update=change)}
            )
            with pytest.raises(OwnershipConflict):
                authority.verify_task(cfg, wrong, guard())
        with pytest.raises(OwnershipConflict):
            authority.verify_task(
                cfg, request.model_copy(update={"private_input": "{}"}), guard()
            )
        authority.task_intents[request.operation.operation_id] = put(
            c.evidence,
            request.model_copy(update={"binding_ref": cfg.token.recovery_ref}),
        )
        with pytest.raises(OwnershipConflict):
            authority.verify_task(cfg, request, guard())
        assert len(original.case.commands.calls) == before
