"""Actual retained metadata and original PHP projection; no live website rights."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
import pytest
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence_contents import (
    NavigationEquivalenceContents,
    NavigationEquivalenceReply,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_search_projection_program import (
    SEARCH_EQUIVALENCE_PHP,
    SEARCH_METADATA_NORMALIZATION_PHP,
)
from test_admin_search_http import command

P = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-admin-navigation-production-20261102-v1/production-4931286"
)
FIXTURE_SHA = "f68e297f2db11d9370d15429d7c6153603b1990a0f7a1ca1970c56de3ea6f2e1"
PROGRAM = SEARCH_METADATA_NORMALIZATION_PHP + SEARCH_EQUIVALENCE_PHP + r"""
try {
 $m=json_decode($argv[1],false,128,JSON_THROW_ON_ERROR);
 echo json_encode(['strict'=>normalized($m),'equivalence'=>equivalence_metadata($m)],JSON_UNESCAPED_SLASHES|JSON_PRESERVE_ZERO_FRACTION|JSON_THROW_ON_ERROR);
}catch(Throwable $e){fwrite(STDERR,$e->getMessage());exit(2);}
"""


@pytest.fixture(scope="module")
def actual() -> dict[str, Any]:
    raw = (P / "exact-original-metadata-api.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA
    value = json.loads(raw)
    assert value["all_original_measured_hashes_matched"] is True
    records = value["records"]
    assert isinstance(records, dict)
    return records


def project(value: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command(PROGRAM) + (json.dumps(value, separators=(",", ":")),),
        capture_output=True,
        timeout=20,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def test_actual_pair_reproduces_original_failure_but_preserves_strict_restore(
    actual: Any,
) -> None:
    measured = {}
    for label, sha in [
        ("source", "0d1b04ebea822b85c46a94cd6bd285598827d416cc3c2a49f52f3d4f861c3fe8"),
        (
            "candidate",
            "84398e25f7048b5e2f2e662efdbeda3f2d4cce8fcaac1cf981899539a021dc89",
        ),
    ]:
        response = project(actual[label]["api_metadata"])
        assert response.returncode == 0, response.stderr.decode()
        body = json.loads(response.stdout)
        assert digest(body["strict"]) == actual[label]["expected_original_sha256"]
        old_raw = (P / "evidence/blobs" / sha).read_bytes()
        legacy = NavigationRecoverySnapshot.model_validate_json(old_raw)
        assert legacy.model_dump_json().encode() == old_raw
        old = legacy.contents
        assert old is not None
        values = old.measured.model_dump(exclude={"schema_version"})
        values.update(
            search_operation_mode="STOPPED",
            search_equivalence_metadata_sha256=digest(body["equivalence"]),
        )
        current = NavigationEquivalenceContents(
            snapshot_sha256=old.snapshot_sha256,
            image_sha256=old.image_sha256,
            measured=NavigationEquivalenceReply.model_validate(values),
            artifacts=old.artifacts,
        )
        current.require_snapshot(legacy.state)
        measured[label] = current
    assert (
        measured["source"].equivalence_sha256
        == measured["candidate"].equivalence_sha256
    )
    assert measured["source"].content_sha256 != measured["candidate"].content_sha256


@pytest.mark.parametrize(
    "fault",
    [
        "phase",
        "action",
        "step",
        "phase_definition",
        "creation_date",
        "settings",
        "repository_generation",
        "extra_field",
    ],
)
def test_meaningful_state_is_never_projected_away(actual: Any, fault: str) -> None:
    value = deepcopy(actual["source"]["api_metadata"])
    managed = next(row for row in value["indices"].values() if "ilm" in row)
    if fault in ["phase", "action", "step", "phase_definition", "creation_date"]:
        managed["ilm"][fault] += "-changed"
    elif fault == "settings":
        managed["settings"]["index"]["number_of_shards"] = "2"
    elif fault == "repository_generation":
        value["repositories"]["lab_admin_recovery"]["generation"] += 1
        value["repositories"]["lab_admin_recovery"]["pending_generation"] += 1
    else:
        managed["ilm"]["unexpected_semantic_state"] = "retained"
    base, changed = project(actual["source"]["api_metadata"]), project(value)
    assert base.returncode == changed.returncode == 0, changed.stderr.decode()
    assert (
        json.loads(base.stdout)["equivalence"]
        != json.loads(changed.stdout)["equivalence"]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "running",
        "repository_uuid",
        "repository_location",
        "timestamp_type",
        "timestamp_missing",
        "ilm_position",
    ],
)
def test_invalid_or_unheld_metadata_is_rejected(actual: Any, fault: str) -> None:
    value = deepcopy(actual["source"]["api_metadata"])
    managed = next(row for row in value["indices"].values() if "ilm" in row)
    if fault == "running":
        value["index_lifecycle"]["operation_mode"] = "RUNNING"
    elif fault == "repository_uuid":
        value["repositories"]["lab_admin_recovery"]["uuid"] = ""
    elif fault == "repository_location":
        value["repositories"]["lab_admin_recovery"]["settings"]["location"] = "/foreign"
    elif fault == "timestamp_type":
        managed["ilm"]["step_time"] = True
    elif fault == "timestamp_missing":
        del managed["ilm"]["step_time"]
    else:
        del managed["ilm"]["step"]
    response = project(value)
    assert response.returncode == 2 and not response.stdout
    assert response.stderr
