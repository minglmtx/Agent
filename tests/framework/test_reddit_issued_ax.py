"""Actual original prompt reconstruction over a synthetic loop, readonly replay."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.reddit_issued_ax import last_issued_ax
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_loop_fixtures import case
from test_slurm_commands import guard


@pytest.mark.parametrize("mode", ["two-turns", "terminal-only", "invalid", "goal-only"])
def test_last_issued_view_is_reconstructed_not_terminal_or_goal(
    tmp_path: Path, mode: str
) -> None:
    responses = (
        ('{"action":"send_msg_to_user(\'Done\')"}',)
        if mode in ("terminal-only", "goal-only")
        else (
            ("invalid",)
            if mode == "invalid"
            else (
                '{"action":"click(\'2\')"}',
                '{"action":"send_msg_to_user(\'Done\')"}',
            )
        )
    )
    c = case(tmp_path, responses)
    if mode == "goal-only":
        c.request = c.request.model_copy(
            update={
                "task": c.request.task.model_copy(update={"goal": "Saved public state"})
            }
        )
    snapshot = c.runner.run(c.request)
    trace = snapshot.project().sealed
    assert trace is not None
    last = trace.turns[-1].generation.before_observation_ref
    observed = Observation.model_validate_json(c.store.read(last))
    counts = c.model.calls, c.browser.calls

    class ReadOnly:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            return c.store.read(reference, control)

    for _ in range(2):
        result = last_issued_ax(c.request, snapshot, trace, ReadOnly(), guard())
        assert result == observed.text
    assert counts == (c.model.calls, c.browser.calls)
    if mode == "two-turns":
        assert "Saved public state" in result
    elif mode in ("terminal-only", "goal-only"):
        final = Observation.model_validate_json(
            c.store.read(trace.final_observation_ref)
        )
        assert final.text and "Saved public state" in final.text
        assert "Saved public state" not in result
        assert trace.final_observation_ref != last
        if mode == "goal-only":
            assert "Saved public state" in c.model.prompts[-1].messages[1].content
    else:
        assert trace.stop_reason == "generation_limit" and c.browser.calls == 0


@pytest.mark.parametrize(
    "fault",
    [
        "goal",
        "skill",
        "prompt",
        "response",
        "observation",
        "snapshot",
        "error",
        "uncertain",
        "cancel",
    ],
)
def test_changed_or_incomplete_actual_request_cannot_supply_issued_ax(
    tmp_path: Path, fault: str
) -> None:
    c = case(tmp_path)
    if fault in ("error", "uncertain"):
        c.model.status = "failed" if fault == "error" else "uncertain"
    snapshot = c.runner.run(c.request)
    trace = snapshot.project().sealed
    assert trace is not None
    request = c.request
    if fault == "goal":
        request = request.model_copy(
            update={"task": request.task.model_copy(update={"goal": "Injected goal"})}
        )
    if fault == "skill":
        request = request.model_copy(update={"skill": "Injected instruction"})
    if fault == "snapshot":
        snapshot = snapshot.model_copy(update={"events": snapshot.events[:-1]})
    generation = trace.turns[-1].generation
    target = {
        "prompt": generation.input_ref,
        "response": generation.response_ref,
        "observation": generation.before_observation_ref,
    }.get(fault)

    class Reader:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            if reference == target:
                return b"{}"
            return c.store.read(reference, control)

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "issued-ax")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    counts = c.model.calls, c.browser.calls
    with pytest.raises(
        OperationStopped if fault == "cancel" else (EvidenceIntegrityError, ValueError)
    ):
        last_issued_ax(
            request,
            snapshot,
            trace,
            Reader(),
            Stopped() if fault == "cancel" else guard(),
        )
    assert counts == (c.model.calls, c.browser.calls)
