"""Original seven-check review on real CAS, with synthetic site/Actor effects."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_evaluation import gitlab_ssh_evaluator
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from gitlab_evaluator_fixtures import evaluation_case
from gitlab_actor_review import review_gitlab_judgment
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "case", ["success", "failure", "missing", "different", "cancel"]
)
def test_independent_native_oracle_readonly_repeat_unknown_and_rejection(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    with evaluation_case(
        tmp_path, node_path, monkeypatch, saved=case != "failure"
    ) as c:
        selected = (
            c.selected.model_copy(update={"after": None})
            if case == "missing"
            else c.selected
        )
        store = ReadOnlyEvidence(node_path / "private-evidence")
        saved = gitlab_ssh_evaluator(selected).evaluate(c.contract, store, guard())
        before = tuple(sorted((node_path / "private-evidence/blobs").iterdir()))
        calls = c.source.preparation.native.reader.calls
        if case == "different":
            with pytest.raises(EvidenceIntegrityError, match="evaluation differs"):
                review_gitlab_judgment(
                    c.contract,
                    selected,
                    saved.model_copy(update={"reason_code": "FOREIGN"}),
                    store,
                    guard(),
                )
        elif case == "cancel":
            with pytest.raises(OperationStopped):
                review_gitlab_judgment(c.contract, selected, saved, store, guard(0))
        else:
            first = review_gitlab_judgment(c.contract, selected, saved, store, guard())
            assert first == review_gitlab_judgment(
                c.contract, selected, saved, store, guard()
            )
            assert first["original_oracle"] == (
                "not_run" if case == "missing" else "all_seven_equal"
            )
            assert first["business_accepted"] == (case != "missing")
        assert c.source.preparation.native.reader.calls == calls
        assert tuple(sorted((node_path / "private-evidence/blobs").iterdir())) == before
