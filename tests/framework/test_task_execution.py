"""Original complete task use-case with actual admission/Actor loop and journals."""

from lab_generate_skill.application.construction_task_result import (
    construction_task_result,
)

from pathlib import Path
from lab_generate_skill.application.execute_task import execute_task
from lab_generate_skill.domain.task_execution_result import (
    TaskAttemptResult,
    ExecutedTaskReceipt,
)
from task_execution_fixtures import task_case
from test_run_journal import command


def test_original_task_main_lifecycle_uses_real_admission_actor_trace_and_safe_reset(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "task")
    result = construction_task_result(execute_task(c.plan, c.deps))
    assert result.intent == c.plan.intent and result.evaluation.status == "failure"
    assert result.generations == result.interactions == 1
    assert c.phases.calls == [
        "preflight",
        "acquire",
        "prepare",
        "start",
        "bind_actor",
        "model",
        "browser",
        "capture",
        "evaluate",
        "close",
        "verify_closed",
        "restore",
    ]
    assert c.model.calls == c.browser.calls == c.actor.calls == 1
    run, attempts = c.deps.runs.read(command()).project()
    assert (
        run.stage == "running" and len(attempts) == 1 and attempts[0].stage == "sealed"
    )
    assert tuple(e.stage for e in attempts[0].events) == (
        "planned",
        "acquiring",
        "preparing",
        "starting",
        "baseline_verified",
        "executing",
        "captured",
        "evaluated",
        "closing",
        "restoring",
        "sealed",
    )
    raw = TaskAttemptResult.model_validate_json(
        c.admission.data.store.read(result.attempt_ref)
    )
    full = ExecutedTaskReceipt.model_validate_json(
        c.admission.data.store.read(raw.execution_ref)
    )
    assert (
        full.intent == result.intent
        and full.reset_ref.content_schema == "reset-receipt/1"
    )
    assert full.generations == full.interactions == 1
