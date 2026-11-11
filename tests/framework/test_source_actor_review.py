"""Independent readback of a synthetic two-turn exchange, with real CAS/trace."""

from lab_generate_skill.actor.prompting import prepare_actor

from dataclasses import replace
from pathlib import Path
import json
import re
import pytest
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.actor_engine import (
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from source_actor_review import review_actor
from source_actor_trace import SourceTraceAuthority
from lab_generate_skill.domain.trace_events import GenerationObserved
from lab_generate_skill.domain.errors import OwnershipConflict
from source_review_records import ReadOnlyEvidence
from local_actor_fixtures import case
from retrieval_fixtures import reference
from test_run_journal import command


@pytest.mark.parametrize(
    "change", ["address", "line", "node", "type", "corrupt_failure"]
)
def test_readonly_review_reproduces_invalid_ast_without_rewriting_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    import lab_generate_skill.adapters.plans.actor_closed_review as reviewer
    from lab_generate_skill.actor.response import parse_actor_action as parse
    from lab_generate_skill.domain.task import PublicTask

    c = case(tmp_path)
    loop = c.loop
    loop.request = loop.request.model_copy(
        update={
            "model_allocation": c.binding.resource,
            "parameters_refs": (c.intent.parameters_ref,)
            * len(loop.request.parameters_refs),
        }
    )
    c.loader.session.output = c.loader.session.output.model_copy(
        update={
            "text": json.dumps(
                {"action": "send_msg_to_user({'estimated_delivery_date': null})"}
            )
        }
    )
    snapshot = RecordedActorRunner(replace(loop.runner.deps, model=c.model)).run(
        loop.request
    )
    trace = snapshot.project().sealed
    assert trace is not None and trace.stop_reason == "generation_limit"
    assert trace.interactions == 0 and loop.browser.calls == 0
    failure_refs = []
    for turn in trace.turns:
        assert turn.decision is not None and turn.decision.outcome == "invalid"
        assert turn.decision.failure_ref is not None
        failure_refs.append(turn.decision.failure_ref)
    original = {
        ref.sha256: (tmp_path / "evidence/blobs" / ref.sha256).read_bytes()
        for ref in failure_refs
    }

    def reproduce(
        text: str, finish_reason: str, task: PublicTask, action_id: str
    ) -> BrowserAction:
        try:
            return parse(text, finish_reason, task, action_id)
        except ValueError as error:
            assert "<ast.Name object at 0x" in str(error)
            message = re.sub(r"0x[0-9a-f]+>", "0xabcdef>", str(error))
            if change == "line":
                message = message.replace("line 1", "line 2")
            elif change == "node":
                message = message.replace("ast.Name", "ast.Call")
            if change == "type":
                raise TypeError(message) from error
            raise ValueError(message) from error

    monkeypatch.setattr(reviewer, "parse_actor_action", reproduce)
    if change == "corrupt_failure":
        (tmp_path / "evidence/blobs" / failure_refs[0].sha256).write_bytes(b"corrupted")
    before = {p.name for p in (tmp_path / "evidence/blobs").iterdir()}
    op = command(
        "independent-invalid-review", attempt="attempt", cleanup_parent="original-run"
    )

    def review() -> dict[str, int | str]:
        return review_actor(
            loop.request,
            snapshot,
            tuple(c.authority.completed),
            ReadOnlyEvidence(tmp_path / "evidence"),
            loop.journal.controls,
            op,
            project=prepare_actor,
        )

    if change == "address":
        expected = dict(
            generations=trace.generations,
            interactions=0,
            stop_reason="generation_limit",
        )
        assert review() == expected
        assert review() == expected
    else:
        with pytest.raises(EvidenceIntegrityError):
            review()
    assert {p.name for p in (tmp_path / "evidence/blobs").iterdir()} == before
    for name, raw in original.items():
        expected_raw = (
            b"corrupted"
            if change == "corrupt_failure" and name == failure_refs[0].sha256
            else raw
        )
        assert (tmp_path / "evidence/blobs" / name).read_bytes() == expected_raw


@pytest.mark.parametrize(
    "change",
    ["none", "missing", "duplicate", "public_task", "parameters", "corrupt_return"],
)
def test_readonly_review_checks_original_prompt_exchange_action_and_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    c = case(tmp_path)
    loop = c.loop
    loop.request = loop.request.model_copy(
        update={
            "model_allocation": c.binding.resource,
            "parameters_refs": (c.intent.parameters_ref,)
            * len(loop.request.parameters_refs),
        }
    )
    original_infer = c.loader.session.infer

    def infer(
        tokens: tuple[int, ...],
        parameters: LocalActorParameters,
        control: OperationControl,
    ) -> LocalActorOutput:
        if c.loader.session.calls:
            c.loader.session.output = c.loader.session.output.model_copy(
                update={"text": '{"action":"send_msg_to_user(\'Done\')"}'}
            )
        return original_infer(tokens, parameters, control)

    monkeypatch.setattr(c.loader.session, "infer", infer)
    original_step = loop.browser.step

    def step(
        action: BrowserAction, operation: OperationContext, *, control: OperationControl
    ) -> StepResult:
        result = original_step(action, operation, control=control)
        obs = Observation.model_validate_json(loop.store.read(result.observation_ref))
        raw = BrowserReadout(
            scope=loop.request.scope,
            operation=operation,
            action=action,
            observation=obs,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=result.terminal,
        )
        return result.model_copy(
            update={
                "return_ref": reference(raw, "browser-step-return/1", store=loop.store)
            }
        )

    monkeypatch.setattr(loop.browser, "step", step)
    runner = RecordedActorRunner(replace(loop.runner.deps, model=c.model))
    snapshot = runner.run(loop.request)
    request, executions = loop.request, tuple(c.authority.completed)
    assert len(executions) == 2
    if change == "missing":
        executions = executions[:-1]
    elif change == "duplicate":
        executions = (executions[0], executions[0])
    elif change == "public_task":
        request = request.model_copy(
            update={
                "task": request.task.model_copy(update={"goal": "invented instruction"})
            }
        )
    elif change == "parameters":
        request = request.model_copy(
            update={"parameters_refs": tuple(reversed(request.parameters_refs[:-1]))}
        )
    elif change == "corrupt_return":
        trace = snapshot.project().sealed
        assert (
            trace is not None
            and trace.turns[-1].interaction is not None
            and trace.turns[-1].interaction.result is not None
        )
        (
            tmp_path
            / "evidence/blobs"
            / trace.turns[-1].interaction.result.return_ref.sha256
        ).write_bytes(b"corrupted")
    store = ReadOnlyEvidence(tmp_path / "evidence")
    before = {p.name for p in (tmp_path / "evidence/blobs").iterdir()}
    operation = command(
        "independent-review", attempt="attempt", cleanup_parent="original-run"
    )
    if change == "none":
        result = review_actor(
            request,
            snapshot,
            executions,
            store,
            loop.journal.controls,
            operation,
            project=prepare_actor,
        )
        assert result == dict(generations=2, interactions=2, stop_reason="finished")
        gate = SourceTraceAuthority(
            snapshot.plan, store, loop.journal.controls, list(executions)
        )
        gate.verify_plan(snapshot.plan, operation)
        for event in snapshot.events:
            gate.verify_event(snapshot, event, operation)
        missing = SourceTraceAuthority(snapshot.plan, store, loop.journal.controls, [])
        observed = next(e for e in snapshot.events if isinstance(e, GenerationObserved))
        with pytest.raises(OwnershipConflict, match="no verified"):
            missing.verify_event(snapshot, observed, operation)

    else:
        with pytest.raises((EvidenceIntegrityError, ValueError)):
            review_actor(
                request,
                snapshot,
                executions,
                store,
                loop.journal.controls,
                operation,
                project=prepare_actor,
            )
    assert {p.name for p in (tmp_path / "evidence/blobs").iterdir()} == before
    with pytest.raises(PermissionError, match="no write"):
        store.put(
            b"no",
            EvidenceMetadata(
                media_type="application/json",
                content_schema="engineering/1",
                visibility="private",
                producer="unit",
            ),
            loop.journal.controls.bind(operation),
        )
