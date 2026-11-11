"""Original owned constructors across preflight, dispatch, send and cleanup.

The site/kernel/model premises are synthetic; original trace, claim, once gates,
production assembly and exact evidence parsing remain in use.
"""

from collections import Counter
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast
import pytest
from lab_generate_skill.adapters.models.local_actor import RecordedLocalActorModel
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "prompt",
        "parameters",
        "observation",
        "storage",
        "cancel",
        "intent",
        "thread",
        "before-send",
    ],
)
def test_owned_dispatch_reuses_exact_inputs_and_rechecks_current_gates(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        store = c.p.original.resource.evidence
        read = store.read
        inputs = RecordedLocalActorModel._inputs
        exchange = SupervisedActorEngine.generate_exchange
        physical: Counter[Any] = Counter()
        dispatch_reads: Counter[Any] = Counter()
        in_dispatch = False
        calls: list[Any] = []
        holders: list[RecordedActorContextInputs] = []
        monitoring = injected = False
        current_counts: list[int] = []

        def counted(reference: Any, control: Any = None) -> bytes:
            if monitoring:
                physical[reference] += 1
                if in_dispatch:
                    dispatch_reads[reference] += 1
                elif reference.content_schema in (
                    "actor-model-input/1",
                    "model-parameters/1",
                    "observation/1",
                ):
                    assert any(
                        frame.name in ("plan", "event")
                        and frame.filename.endswith(
                            "/adapters/plans/trace_journal_evidence.py"
                        )
                        for frame in traceback.extract_stack()
                    )
            return read(reference, control=control)

        def dispatch(self: Any, intent: Any, phase: Any, control: Any) -> Any:
            nonlocal monitoring, injected, in_dispatch
            monitoring = True
            calls.append((self, intent, control))
            held = self._inputs_read
            assert isinstance(held, RecordedActorContextInputs)
            if held not in holders:
                holders.append(held)
            inject_at = 3 if fault == "before-send" else 2
            if len(calls) == inject_at and fault != "none":
                injected = True
                assert held._inputs is not None and held._inputs.bodies
                if fault in ("prompt", "parameters", "observation"):
                    schema = {
                        "prompt": "actor-model-input/1",
                        "parameters": "model-parameters/1",
                        "observation": "observation/1",
                    }[fault]
                    reference = next(
                        ref
                        for ref in held._inputs.bodies
                        if ref.content_schema == schema
                    )
                    cast(Any, held._inputs.bodies)[reference] += b" "
                elif fault in ("storage", "before-send"):
                    fixed.denied = True
                elif fault == "cancel":
                    raise OperationStopped("CANCELLED", intent.operation.operation_id)
                elif fault == "intent":
                    intent = intent.model_copy(update={"request_id": "foreign-request"})
                else:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(held.generation_inputs, intent, control).result()
            in_dispatch = True
            try:
                result = inputs(self, intent, phase, control)
            finally:
                in_dispatch = False
            current_counts.append(fixed.current_calls)
            return result

        def sent(self: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal monitoring
            monitoring = False
            return exchange(self, *args, **kwargs)

        monkeypatch.setattr(store, "read", counted)
        monkeypatch.setattr(RecordedLocalActorModel, "_inputs", dispatch)
        monkeypatch.setattr(SupervisedActorEngine, "generate_exchange", sent)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.native.loader.session.calls == 1 and len(calls) == 3
            assert len(current_counts) == 3
            assert all(b > a for a, b in zip(current_counts, current_counts[1:]))
            intent = calls[0][1]
            for reference in (
                intent.input_ref,
                intent.parameters_ref,
                intent.before_observation_ref,
            ):
                expected_reads = 1 if reference == intent.parameters_ref else 0
                assert dispatch_reads[reference] == expected_reads, (
                    reference.content_schema,
                    dispatch_reads[reference],
                )
            # Both original plan and event gates read and parse observations.
            # Exact journal dependency + observation parsing reads stay
            # outside the shared model/authority inputs, and their caller is
            # checked above. This is a separate count, not a widened upper bound.
            assert physical[intent.input_ref] == 1
            assert physical[intent.parameters_ref] == 2
            assert physical[intent.before_observation_ref] == 4
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert injected and c.native.loader.session.calls == 0
            error: Any = failed.value
            chain = []
            while error is not None and error not in chain:
                chain.append(error)
                error = getattr(error, "primary", None) or error.__cause__
            expected = (
                TypeError
                if fault in ("prompt", "parameters", "observation")
                else OperationStopped if fault == "cancel" else OwnershipConflict
            )
            assert any(isinstance(error, expected) for error in chain), chain
            assert len(calls) == (3 if fault == "before-send" else 2)
            if fault in ("storage", "before-send"):
                assert c.bundle.finalization.state.reset is None
        assert holders and all(
            value._inputs is None and value._input_key is None for value in holders
        )
        assert r.inputs is not None and not r.inputs.active
        _, intent, control = calls[0]
        with pytest.raises(OwnershipConflict, match="lifetime"):
            holders[0].generation_inputs(intent, control)
