"""Metadata-only scope: no plan/claim downgrade and original physical gates."""

from typing import Any
from unittest.mock import Mock
import pytest
from lab_generate_skill.adapters.storage import scope_admission as module
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.claims import SourceClaimReader
from storage_scope_fixtures import scope, operation, observation
from cgroup_fixtures import Control


def test_metadata_only_namespace_and_original_scope_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = scope()
    data = old.model_dump(exclude={"schema_version", "run", "claim"})
    current = OwnerMetadataStorageScope.model_validate(data)
    assert (
        OwnerMetadataStorageScope.model_validate_json(current.model_dump_json())
        == current
    )
    assert current.binding.namespace_key == old.binding.namespace_key
    invalid_values: tuple[Any, ...] = (None, "scope", 0, True, [], {})
    for bad in invalid_values:
        with pytest.raises((TypeError, ValueError)):
            OwnerMetadataStorageScope.model_validate(bad)
    for changes in (
        {"run": old.run.model_dump()},
        {"claim": None},
        {"workspace_root": "/"},
        {
            "binding": {
                **data["binding"],
                "scope": "source",
                "source_task_id": "foreign",
            }
        },
        {
            "binding": {
                **data["binding"],
                "owner": {**data["binding"]["owner"], "job_id": "foreign"},
            }
        },
    ):
        with pytest.raises(ValueError):
            OwnerMetadataStorageScope.model_validate({**data, **changes})
    monkeypatch.setattr(module, "current_process_identity", lambda: current.writer)
    observe = Mock(return_value=observation(old))
    monkeypatch.setattr(module, "observe_current_cgroup", observe)
    a = module.PinnedSlurmStorageAdmission(current)
    with pytest.raises(OwnershipConflict):
        a.activate(Mock(spec=SourceClaimReader), operation(old), Control())
    assert observe.call_count == 0
    with pytest.raises(InvalidTransition):
        a.activate(None, operation(old), Control())
    a = module.PinnedSlurmStorageAdmission(current)
    a.activate(None, operation(old), Control())
    op = operation(old, "metadata")
    a.authorize_storage(current.binding, current.config, op, Control())
    with pytest.raises(InvalidTransition):
        a.authorize_storage(current.binding, current.config, op, Control())
    for changes in (
        {"attempt_id": "attempt"},
        {"owner_id": "foreign"},
        {"mode": "cleanup", "parent_operation_id": "foreign"},
    ):
        with pytest.raises(OwnershipConflict):
            a.authorize_storage(
                current.binding,
                current.config,
                op.model_copy(update=changes),
                Control(),
            )
    a.stop_new_io()
    cleanup = op.cleanup("metadata-close", now=op.deadline, seconds=10)
    a.authorize_cleanup(current.binding, current.config, op, cleanup, None, Control())
    with pytest.raises(InvalidTransition):
        a.authorize_storage(
            current.binding, current.config, operation(old, "new"), Control()
        )
    # Old run/source dictionaries are always parsed as their original scope;
    # malformed permissions cannot select this explicit metadata variant.
    wrong: Any = {**data, "schema_version": "owner-metadata-storage-scope/1"}
    with pytest.raises(ValueError):
        module.PinnedSlurmStorageAdmission(wrong)
