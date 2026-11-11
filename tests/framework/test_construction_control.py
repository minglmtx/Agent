"""Original four-attempt prefix -> controlled Teacher -> revised Actor -> select.

No real model, site, source permission or skill quality is implied by unit ports.
"""

from pathlib import Path
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    SelectConstructionWork,
    ObserveConstructionWork,
)
from construction_control_fixtures import control_case
from test_run_journal import command


def test_original_ready_teacher_revised_actor_and_selection_use_one_control_entry(
    tmp_path: Path,
) -> None:
    c = control_case(tmp_path / "case")
    n = c.native
    teacher_step = c.teacher_step()
    revised = construct_targets(teacher_step, c.deps)
    assert revised.status == "advanced" and revised.teacher is not None
    assert revised.progress.project().next_action.kind == "execute"
    assert revised.progress.project().next_action.candidate_slot == 4
    assert len(n.transport.calls) == 1 and len(c.publications) == 1
    # Stale original command never reexecutes a model; original next action wins.
    from lab_generate_skill.domain.errors import RevisionConflict
    import pytest

    with pytest.raises(RevisionConflict):
        construct_targets(teacher_step, c.deps)
    assert len(n.transport.calls) == 1
    actor_step = c.actor_step()
    verified = construct_targets(actor_step, c.deps)
    assert verified.progress.project().next_action.kind == "select"
    assert (
        len(c.attempts.calls) == 1
        and verified.progress.project().attempts[-1].evaluation.status == "success"
    )
    selected = construct_targets(
        ConstructionStepPlan(
            run=verified.progress.plan.run,
            expected_revision=verified.progress.revision,
            operation=command("controlled-select"),
            work=SelectConstructionWork(),
        ),
        c.deps,
    )
    choice = selected.progress.project().selection
    assert (
        selected.status == "complete"
        and choice is not None
        and choice.status == "accepted"
        and choice.candidate_slot == 4
    )
    observed = construct_targets(
        ConstructionStepPlan(
            run=selected.progress.plan.run,
            expected_revision=selected.progress.revision,
            operation=command("controlled-observe"),
            work=ObserveConstructionWork(),
        ),
        c.deps,
    )
    assert observed.status == "complete" and observed.progress == selected.progress
    assert len(n.transport.calls) == 1 and len(c.attempts.calls) == 1
