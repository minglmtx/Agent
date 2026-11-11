"""Durable original inputs, never permission to retry or infer termination."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.storage_recovery_input import StorageRecoveryInput
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceOperationIntent,
    EvidenceSessionEntry,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.errors import EvidenceNotFound, OwnershipConflict
from evidence_session_fixtures import intent
from registered_storage_fixtures import request


def original(root: Path, reading: bool = False) -> StorageRecoveryInput:
    cmd = request(root)
    value = intent(kind="read" if reading else "put")
    value = value.model_copy(
        update={
            "command": value.command.model_copy(
                update={
                    "root": cmd.config.evidence_root,
                    "max_object_bytes": cmd.config.max_object_bytes,
                }
            )
        }
    )
    snapshot = EvidenceSessionSnapshot(
        binding=cmd.binding,
        capacity=cmd.config.capacity,
        entries=(EvidenceSessionEntry(intent=value),),
    )
    return StorageRecoveryInput(
        snapshot=snapshot, config=cmd.config, exchange_id=value.exchange_id
    )


@pytest.mark.parametrize("reading", [False, True])
def test_original_descriptor_roundtrip_and_no_payload(
    tmp_path: Path, reading: bool
) -> None:
    value = original(tmp_path, reading)
    recovered = StorageRecoveryInput.model_validate_json(value.model_dump_json())
    assert recovered == value and recovered.command == value.intent.command
    assert recovered.intent.controller == value.intent.controller
    assert not hasattr(recovered, "payload") and not hasattr(recovered, "execute")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "case",
    [
        "missing_controller",
        "missing_command",
        "old_intent",
        "exchange",
        "kind",
        "reference",
        "controller_pid",
        "controller_node",
        "controller_boot",
        "metadata",
        "empty_controller",
        "wrong_command_type",
    ],
)
def test_invalid_original_intent_rejected(case: str) -> None:
    value = intent()
    data = value.model_dump(mode="json")
    if case.startswith("missing_"):
        del data[case.removeprefix("missing_")]
    elif case == "old_intent":
        data["schema_version"] = "evidence-operation-intent/1"
    elif case == "exchange":
        data["command"]["exchange_id"] = "other"
    elif case == "kind":
        data["kind"] = "read"
    elif case == "reference":
        data["command"]["reference"]["size_bytes"] += 1
    elif case == "controller_pid":
        data["controller"]["process_id"] = value.worker.process_id
    elif case == "controller_node":
        data["controller"]["node_id"] = "other"
    elif case == "controller_boot":
        data["controller"]["boot_id"] = "other"
    elif case == "metadata":
        data["command"]["metadata"]["producer"] = "other"
    elif case == "empty_controller":
        data["controller"] = {}
    else:
        data["command"] = True
    with pytest.raises(ValueError):
        EvidenceOperationIntent.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "storage",
        "config",
        "capacity",
        "release",
        "root",
        "limit",
        "missing_exchange",
        "missing_snapshot",
        "old_snapshot",
    ],
)
def test_recovery_requires_original_frozen_scope(tmp_path: Path, case: str) -> None:
    value = original(tmp_path)
    data = value.model_dump(mode="json")
    if case == "version":
        data["schema_version"] = "storage-recovery-input/0"
    elif case == "storage":
        data["snapshot"]["binding"]["storage_id"] = "other"
    elif case == "config":
        data["snapshot"]["binding"]["storage_config_sha256"] = "f" * 64
    elif case == "capacity":
        data["snapshot"]["capacity"]["max_exchanges"] += 1
    elif case == "release":
        data["snapshot"]["binding"]["release_id"] = "other"
    elif case == "root":
        data["snapshot"]["entries"][0]["intent"]["command"]["root"] = str(
            tmp_path / "different"
        )
    elif case == "limit":
        data["snapshot"]["entries"][0]["intent"]["command"]["max_object_bytes"] += 1
    elif case == "missing_exchange":
        data["exchange_id"] = "absent"
    elif case == "missing_snapshot":
        data["snapshot"] = {}
    else:
        data["snapshot"]["schema_version"] = "evidence-session-snapshot/2"
    with pytest.raises((ValueError, EvidenceNotFound, OwnershipConflict)):
        StorageRecoveryInput.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("bad", [None, True, {}, [], "", 0])
def test_invalid_input_types(bad: Any) -> None:
    with pytest.raises(ValueError):
        StorageRecoveryInput.model_validate(bad)
