"""Run an independent closed readonly review over finite fixture references."""

import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.sites.gitlab.evidence_schema import GroupEvidence


def closed_group_review(
    root: Path,
    evidence: Path,
    contract: EvaluationContract,
    selected: GroupEvidence,
    saved: Evaluation,
) -> dict[str, Any]:
    request = root / "group-review-input.json"
    with request.open("x") as stream:
        json.dump(
            dict(
                schema_version="engineering-group-review-input/1",
                contract=contract.model_dump(mode="json"),
                selection=selected.model_dump(mode="json"),
                saved=saved.model_dump(mode="json"),
            ),
            stream,
        )
    command = (
        sys.executable,
        "-B",
        str(Path(__file__).with_name("gitlab_group_review_worker.py")),
        str(request),
        str(evidence),
    )
    completed = subprocess.run(command, capture_output=True, timeout=40, check=False)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    result = dict(json.loads(completed.stdout))
    (root / "group-review-result.json").write_bytes(completed.stdout)
    return result
