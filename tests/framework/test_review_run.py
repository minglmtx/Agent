"""Selected complete Task/Teacher construction is reviewed after native close."""

from pathlib import Path
import pytest
from lab_generate_skill.application.review_run import review_run
from construction_review_fixtures import construction_review_case, UnitReplayEvaluator


def test_sealed_original_construction_recomputes_all_judgments_and_target_after_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = construction_review_case(tmp_path / "case", monkeypatch)
    plan = c.plan()
    deps = c.deps(plan)
    source = c.control.source
    before = source.data.journal().read(plan.operation)
    phases = tuple(c.fifth.task.phases.calls)
    native_calls = source.native.loader.session.calls
    teacher_calls = len(c.control.wire.transport.calls)

    def no_put(*args: object, **kwargs: object) -> None:
        raise AssertionError("Independent review cannot write source CAS")

    with monkeypatch.context() as patch:
        patch.setattr(source.data.store, "put", no_put)
        receipt = review_run(plan, deps)
        assert review_run(plan, deps) == receipt
    assert (
        receipt.status == "verified" and receipt.training_admission == "not_evaluated"
    )
    assert len(receipt.findings) == 5 and all(
        f.matches_recorded for f in receipt.findings
    )
    assert receipt.selected_skill_ref == c.fifth.task.plan.skill_ref
    assert (
        receipt.plan.selected_evaluation_ref
        == c.sealed.project().attempts[-1].evaluation_ref
    )
    assert all(
        isinstance(e.evaluator, UnitReplayEvaluator) and e.evaluator.reads == 2
        for e in deps.evaluators
    )
    assert source.data.journal().read(plan.operation) == before
    # These are required readonly closure proofs, not close/restore replay.
    assert tuple(c.fifth.task.phases.calls) == (
        *phases,
        "verify_closed",
        "verify_closed",
    )
    assert source.native.loader.session.calls == native_calls == 5
    assert len(c.control.wire.transport.calls) == teacher_calls == 1
