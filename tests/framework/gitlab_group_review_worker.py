"""Finite engineering readonly subprocess; no site/model/claim or writable store."""

import json
from pathlib import Path
import sys
from lab_generate_skill.domain.evaluation import EvaluationContract, Evaluation
from lab_generate_skill.sites.gitlab.evidence_schema import GroupEvidence
from gitlab_group_actor_review import review_group_judgment
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard

if __name__ == "__main__":
    request = json.loads(Path(sys.argv[1]).read_bytes())
    assert request["schema_version"] == "engineering-group-review-input/1"
    assert set(request) == {"schema_version", "contract", "selection", "saved"}
    result = review_group_judgment(
        EvaluationContract.model_validate_json(json.dumps(request["contract"])),
        GroupEvidence.model_validate_json(json.dumps(request["selection"])),
        Evaluation.model_validate_json(json.dumps(request["saved"])),
        ReadOnlyEvidence(Path(sys.argv[2])),
        guard(),
    )
    print(json.dumps(result, sort_keys=True))
