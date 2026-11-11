"""Closed subprocess and repeat/cancel/mismatch readonly original Group review."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from gitlab_group_evaluator_fixtures import evaluation_case
from gitlab_group_actor_review import review_group_judgment
from gitlab_group_review_process import closed_group_review
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "failure",
        "protected-success",
        "protected-failure",
        "missing",
        "different",
        "cancel",
    ],
)
def test_independent_closed_original_group_oracle_preserves_guard_unknown_and_no_writes(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    with evaluation_case(
        tmp_path,
        node_path,
        monkeypatch,
        saved=case not in ("failure", "protected-failure"),
        projects_changed=case.startswith("protected"),
    ) as c:
        p = c.source.preparation
        selected = (
            c.selected.model_copy(update={"after": None})
            if case == "missing"
            else c.selected
        )
        reader = ReadOnlyEvidence(node_path / "private-evidence")
        saved = gitlab_group_evaluator(selected).evaluate(c.contract, reader, guard())
        before = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        calls = len(p.native.sql.calls)
        if case == "different":
            with pytest.raises(EvidenceIntegrityError, match="evaluation differs"):
                review_group_judgment(
                    c.contract,
                    selected,
                    saved.model_copy(update={"reason_code": "FOREIGN"}),
                    reader,
                    guard(),
                )
        elif case == "cancel":
            with pytest.raises(OperationStopped):
                review_group_judgment(c.contract, selected, saved, reader, guard(-1))
        else:
            result = closed_group_review(
                tmp_path, node_path / "private-evidence", c.contract, selected, saved
            )
            assert result == review_group_judgment(
                c.contract, selected, saved, reader, guard()
            )
            assert result == review_group_judgment(
                c.contract, selected, saved, reader, guard()
            )
            assert result["business_accepted"] == (
                case not in ("missing", "protected-success")
            )
            assert result["original_oracle"] == (
                "not_run"
                if case == "missing"
                else "all_original_conditions_and_guard_equal"
            )
        assert len(p.native.sql.calls) == calls
        assert tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == before
