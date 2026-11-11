"""An explicit versioned read request cannot reinterpret frozen v1 packets."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage.claim_protocol import (
    ClaimReadCommand,
    StageValidationClaimReadCommand,
    encode_claim_command,
    decode_claim_command,
)
from claim_worker_fixtures import inputs
from stage_claim_reader_fixtures import declaration


def test_v1_bytes_remain_exact_and_v2_requires_explicit_descriptor(
    tmp_path: Path,
) -> None:
    _, current, original = inputs(tmp_path)
    raw = original.model_dump_json().encode()
    assert encode_claim_command(original) == raw
    assert decode_claim_command(raw) == original
    stage = declaration(current, original)
    packet = encode_claim_command(stage)
    assert decode_claim_command(packet) == stage
    with pytest.raises(ValueError):
        ClaimReadCommand.model_validate_json(packet)
    assert isinstance(decode_claim_command(packet), StageValidationClaimReadCommand)


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "absent-basis",
        "v1-with-basis",
        "scope",
        "task",
        "target-release",
        "old-owner",
    ],
)
def test_v2_refuses_missing_or_mismatched_validation(tmp_path: Path, case: str) -> None:
    _, current, original = inputs(tmp_path)
    stage = declaration(current, original)
    data = stage.model_dump(mode="json")
    if case == "version":
        data["schema_version"] = "claim-read-command/3"
    elif case == "absent-basis":
        del data["validation"]
    elif case == "v1-with-basis":
        data["schema_version"] = "claim-read-command/1"
    elif case == "scope":
        data["scope"]["claim"]["scope_id"] = "other"
    elif case == "task":
        data["scope"]["claim"]["task"]["registration_id"] = "other"
    elif case == "target-release":
        data["validation"]["target_release_ref"]["producer"] = "other"
    else:
        data["scope"]["claim"]["run"]["owner"][
            "job_id"
        ] = stage.validation.parent.record.binding.run.owner.job_id
    with pytest.raises((ValueError, RuntimeError)):
        decode_claim_command(json.dumps(data).encode())
