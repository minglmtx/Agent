"""Reuse retained real resource closures; synthetic state is separately labelled."""

import json
import os
import subprocess
import sys
from typing import Any
from pathlib import Path
import pytest
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from source_review_records import ReadOnlyEvidence, review_resource, review_state
from state_storage_fixtures import fixture
from retrieval_fixtures import reference
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")


@pytest.mark.parametrize("role", ["actor", "browser", "site"])
@pytest.mark.parametrize("change", ["none", "wrong_owner", "not_closed"])
def test_original_accepted_resource_closure_and_wrong_binding(
    role: str, change: str
) -> None:
    if role == "actor":
        root = (
            W
            / "experiments/framework-core-contracts-v1/check-4776077/actor-resource-native"
        )
        facts = json.loads((root / "facts.json").read_text())
        raw = facts["resource_record"]
        store = ReadOnlyEvidence(root / "resource/evidence")
    else:
        root = W / "experiments/framework-core-contracts-v1/check-4777054"
        facts = json.loads((root / "registered-site-captured_source.json").read_text())
        raw = (
            facts["record"]
            if role == "site"
            else facts["prepared_browser"]["browser_record"]
        )
        store = ReadOnlyEvidence(
            root
            / "tmp/pytest-of-r102bf10/pytest-0/test_registered_actual_site_an0/evidence"
        )
    record = ResourceRecord.model_validate_json(json.dumps(raw))
    token = record.token
    if change == "wrong_owner":
        token = token.model_copy(
            update={"owner": token.owner.model_copy(update={"owner_id": "foreign"})}
        )
    elif change == "not_closed":
        raw["events"][-1]["state"] = "quarantined"
    if change == "none":
        result = review_resource(raw, token, store, guard(15))
        assert result["target"]["worker"]["job_id"] == token.owner.job_id
    else:
        with pytest.raises(EvidenceIntegrityError):
            review_resource(raw, token, store, guard(15))


@pytest.mark.parametrize("change", ["none", "baseline", "reset", "initial"])
def test_state_recomputation_and_reference_binding(tmp_path: Path, change: str) -> None:
    unit = fixture(tmp_path)
    store = ReadOnlyEvidence(tmp_path)

    def put(value: object, schema: str) -> dict[str, Any]:
        return reference(value, schema, store=unit.store).model_dump(mode="json")

    site = dict(
        prepared_browser=dict(
            baseline_inputs_ref=put(unit.baseline_inputs, "baseline-inputs/1"),
            initial_observation_ref=unit.baseline_inputs.observation_ref.model_dump(
                mode="json"
            ),
        ),
        qualified_source=dict(
            baseline_ref=put(unit.baseline, "baseline-receipt/1"),
            reset_inputs_ref=put(unit.reset_inputs, "reset-inputs/1"),
            reset_ref=put(unit.reset, "reset-receipt/1"),
        ),
    )
    if change == "baseline":
        site["qualified_source"]["baseline_ref"] = put(
            unit.baseline.model_copy(update={"status": "unknown"}), "baseline-receipt/1"
        )
    elif change == "reset":
        site["qualified_source"]["reset_ref"] = put(
            unit.reset.model_copy(update={"status": "quarantined"}), "reset-receipt/1"
        )
    elif change == "initial":
        site["prepared_browser"]["initial_observation_ref"] = (
            unit.baseline_inputs.observation_ref.model_copy(
                update={"sha256": "f" * 64}
            ).model_dump(mode="json")
        )
    if change == "none":
        initial, reset = review_state(site, store, guard(15))
        assert initial == unit.baseline_inputs and reset == unit.reset_inputs
    else:
        with pytest.raises(EvidenceIntegrityError):
            review_state(site, store, guard(15))


def test_native_entries_collect_without_initializing_models_or_sites() -> None:
    project = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env.pop("LAB_ACTOR_SOFTWARE_RECEIPT", None)
    env.pop("LAB_ADMIN_ACTOR_ATTEMPT_ROOT", None)
    env.pop("LAB_MAP_ACTOR_ATTEMPT_ROOT", None)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/framework/admin_actor_live.py",
            "tests/framework/admin_actor_review_live.py",
            "tests/framework/map_actor_live.py",
            "tests/framework/map_actor_review_live.py",
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 tests collected" in result.stdout
