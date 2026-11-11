"""Current unknown/recovery checks and unchanged historical contract rejection."""

from pathlib import Path
import json
import os
import pytest
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.preparation import (
    EnvironmentBaseline,
    PreparationReceipt,
    PreparedTask,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from initial_observation_history import read_archive, ROOT
from initial_observation_fixtures import initial_case, Case
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from pydantic import ValidationError
from test_slurm_commands import guard


def test_current_initial_view_checks_preserve_unknown_environment_and_recovery_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with initial_case(tmp_path, monkeypatch) as c:
        check_current_graph(c, tmp_path)


def check_current_graph(c: Case, tmp_path: Path) -> None:
    store, selection, records, operation = (
        c.prepared.browser.evidence,
        c.selection,
        c.records,
        c.op,
    )
    before = set((tmp_path / "site/evidence/blobs").iterdir())
    reference = records.publish(selection, operation)
    initial = records.load(selection, reference, operation)
    assert initial.checks.status == "pass"
    assert initial.observation_ref.model_dump(mode="json") == records.reader.load(
        selection, operation, guard()
    ).acquired.details.started.initial_observation_ref.model_dump(mode="json")
    inputs = records.reader.load(selection, operation, guard())
    read = records.reader.reads.parse
    prepared = read(
        selection.preparation.prepared_ref, "prepared-task/1", PreparedTask, guard()
    )
    binding = read(prepared.task_binding_ref, "task-binding/1", TaskBinding, guard())
    spec = read(prepared.spec_ref, "initial-state-spec/1", InitialStateSpec, guard())
    environment = read(
        selection.preparation.selection.environment_ref,
        "environment-baseline/1",
        EnvironmentBaseline,
        guard(),
    )
    preparation = read(
        prepared.preparation_ref, "preparation-receipt/1", PreparationReceipt, guard()
    )
    baseline_inputs = BaselineInputs(
        binding=binding,
        public_task=prepared.public_task,
        spec=spec,
        spec_ref=prepared.spec_ref,
        environment=environment,
        environment_ref=selection.preparation.selection.environment_ref,
        preparation=preparation,
        preparation_ref=prepared.preparation_ref,
        prepared=prepared,
        prepared_ref=selection.preparation.prepared_ref,
        observation=inputs.observation.record,
        observation_ref=initial.observation_ref,
        initial=initial,
        initial_ref=reference,
    )
    baseline = assemble_baseline(
        baseline_inputs,
        operation.model_copy(update={"operation_id": "historical-baseline-check"}),
    )
    assert baseline.status == "unknown"
    with pytest.raises(OwnershipConflict, match="Initial recovery"):
        BaselineEvidenceReader(store).verify(baseline, guard())
    assert set((tmp_path / "site/evidence/blobs").iterdir()) - before == {
        tmp_path / "site/evidence/blobs" / reference.sha256
    }
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    (output / "current-initial-checks.json").write_text(
        json.dumps(
            dict(
                source_job=os.environ["SLURM_JOB_ID"],
                synthetic_browser=True,
                initial_ref=reference.model_dump(mode="json"),
                initial=initial.model_dump(mode="json"),
                derived_baseline_status=baseline.status,
                original_observation_unchanged=True,
                original_environment_unchanged=True,
                incomplete_environment_recovery_rejected=True,
                actor_authorized=False,
                site_browser_actions=0,
                existing_evidence_unchanged=True,
            ),
            indent=2,
        )
        + "\n"
    )


def test_archived_initial_evidence_cannot_be_upgraded_into_current_worker(
    tmp_path: Path,
) -> None:
    report, store, record, intent = read_archive(tmp_path)
    original = store.read(intent.configuration_ref, guard())
    raw = json.loads(original)
    assert raw["schema_version"] == "browser-resource-spec/2"
    assert raw["token"]["provider_version"] == "1"
    with pytest.raises(ValidationError):
        BrowserResourceSpec.model_validate_json(original)
    with pytest.raises(ValidationError, match="browser-resource-spec/4"):
        InitialObservationSelection.model_validate_json(
            json.dumps(
                {
                    "preparation": report["prepared_browser"][
                        "preparation_publication"
                    ],
                    "browser_spec_ref": intent.configuration_ref.model_dump(
                        mode="json"
                    ),
                    "browser_acquired_ref": record.events[2]
                    .evidence[0]
                    .model_dump(mode="json"),
                }
            )
        )
    assert store.read(intent.configuration_ref, guard()) == original
    assert not list((tmp_path / "blobs").iterdir())
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "historical-initial-contract-rejection.json"
    ).write_text(
        json.dumps(
            {
                "source_job": "4772266",
                "source_root": str(ROOT),
                "original_schema": raw["schema_version"],
                "original_provider_version": raw["token"]["provider_version"],
                "current_admission_rejected": True,
                "original_evidence_read_only": True,
                "site_browser_actions": 0,
                "actor_authorized": False,
            },
            indent=2,
        )
        + "\n"
    )
