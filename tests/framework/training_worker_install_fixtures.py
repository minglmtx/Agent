"""Explicit unit-only install capsule; no construction/model runs in process tests."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from lab_generate_skill.domain.training import TrainingPlan
from lab_generate_skill.domain.dataset_material import LoadedDataset
from lab_generate_skill.policies.training_admission import require_training_dataset
from training_entry_fixtures import (
    TrainingCase,
    contract_data,
    training_case as training_case,
)
from training_worker_fixtures import worker_case


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_prepare_explicit_unit_installation_capsule(
    training_case: TrainingCase, tmp_path: Path
) -> None:
    c = worker_case(training_case, tmp_path / "unit-install-capsule")
    plan = c.configuration.output.training
    require_training_dataset(plan, training_case.data)
    raw = json.dumps(
        dict(
            schema_version="unit-sft-install-capsule/1",
            fixture_only=True,
            actual_source_phase_or_GPU_authority=False,
            training_plan=plan.model_dump(mode="json"),
        ),
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    root = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    path = root / "unit-sft-install-capsule.json"
    with path.open("xb") as stream:
        stream.write(raw)
    (root / "unit-sft-install-capsule-ref.json").write_text(
        json.dumps(
            dict(
                path=str(path),
                sha256=digest(raw),
                size_bytes=len(raw),
                source_fixture_sha256=digest(
                    Path(__file__).with_name("training_entry_fixtures.py").read_bytes()
                ),
                prep_job=os.environ["SLURM_JOB_ID"],
                fixture_only=True,
            ),
            indent=2,
        )
        + "\n"
    )
    path.chmod(0o444)


@dataclass(frozen=True)
class PreparedUnitSource:
    original: TrainingPlan
    data: LoadedDataset

    def plan(self, name: str) -> TrainingPlan:
        operation = self.original.dataset.operation.model_copy(
            update={
                "operation_id": "unit-install-" + name,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=240),
            }
        )
        # Fresh nonexecuting unit metadata, never a new permit for old requests.
        return TrainingPlan.model_validate(
            {
                **self.original.model_dump(),
                "training_id": "unit-sft-" + name,
                "dataset": self.original.dataset.model_copy(
                    update={"operation": operation}
                ),
            }
        )


def prepared_unit_source() -> PreparedUnitSource:
    descriptor = json.loads(
        Path(os.environ["LAB_SFT_WORKER_INSTALL_FIXTURE"]).read_text()
    )
    assert descriptor["fixture_only"] is True
    assert descriptor["source_fixture_sha256"] == digest(
        Path(__file__).with_name("training_entry_fixtures.py").read_bytes()
    )
    raw = Path(descriptor["path"]).read_bytes()
    assert (len(raw), digest(raw)) == (descriptor["size_bytes"], descriptor["sha256"])
    value = json.loads(raw)
    assert (
        value["schema_version"] == "unit-sft-install-capsule/1"
        and value["fixture_only"] is True
        and value["actual_source_phase_or_GPU_authority"] is False
    )
    plan = TrainingPlan.model_validate_json(json.dumps(value["training_plan"]))
    data = contract_data()
    require_training_dataset(plan, data)
    return PreparedUnitSource(plan, data)
