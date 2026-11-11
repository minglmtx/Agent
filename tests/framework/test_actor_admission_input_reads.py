"""Full current task/Actor composition; fixed transport edges are synthetic."""

from collections import Counter
import inspect
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.task_actor_authority import (
    OriginalTaskActorAuthority,
)
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


def test_first_actor_admission_reuses_original_measurements(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        store = c.p.original.resource.evidence
        original_read = store.read
        original_verify = OriginalTaskActorAuthority.verify
        counts: Counter[str] = Counter()
        actor = False

        def read(reference: Any, *args: Any, **kwargs: Any) -> Any:
            if actor and c.native.loader.session.calls == 0:
                frames = inspect.stack(context=0)
                labels = [
                    frame.function
                    for frame in frames
                    if frame.function
                    in (
                        "verify_baseline",
                        "verify_equivalence",
                        "require_browser",
                        "verify_plan",
                        "prepare",
                        "verify",
                        "public_turn",
                    )
                ]
                counts[reference.content_schema + ":" + "/".join(labels)] += 1
            return original_read(reference, *args, **kwargs)

        def verify(self: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal actor
            actor = True
            return original_verify(self, *args, **kwargs)

        monkeypatch.setattr(store, "read", read)
        monkeypatch.setattr(OriginalTaskActorAuthority, "verify", verify)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success"
        assert fixed.loads == 1 and fixed.current_calls > 1
        assert c.native.loader.session.calls == 1
        assert c.bundle.finalization.state.reset is not None
        assert c.bundle.finalization.state.reset.status == "safe"
        held = c.bundle.initialization.original().inputs
        assert held is not None and not held.active
        assert held.candidate_baseline is None and held.browser_acquired is None
        output = {
            "scope": "Synthetic transport read counts from first Actor authority to first model dispatch; not production timing or permission",
            "total_reads": sum(counts.values()),
            "by_schema_and_caller": dict(counts.most_common()),
        }
        if os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
            (
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
                / "first-actor-input-reads.json"
            ).write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output))
        assert not any(
            "verify_baseline" in key and value for key, value in counts.items()
        )
        assert not any(
            key.startswith("browser-worker-acquired/1:require_browser") and value
            for key, value in counts.items()
        )


@pytest.mark.parametrize(
    "fault", ["deadline", "storage", "initial-body", "baseline-body"]
)
def test_context_failure_keeps_original_trace_and_clears_owned_inputs(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from lab_generate_skill.application.actor_context_preparation import (
        ControlledActorContext,
    )
    from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
    from lab_generate_skill.domain.errors import OperationStopped

    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        original = ControlledActorContext.prepare
        injected = []

        def prepare(
            self: Any, request: Any, before: Any, *args: Any, **kwargs: Any
        ) -> Any:
            injected.append(fault)
            held = r.inputs
            assert (
                held is not None
                and held.initial is not None
                and held.candidate_baseline is not None
            )
            if fault == "deadline":
                raise OperationStopped("DEADLINE_EXCEEDED", args[0].operation_id)
            if fault == "storage":
                fixed.denied = True
            elif fault == "initial-body":
                held.initial = held.initial.model_copy(
                    update={
                        "observation": held.initial.observation.model_copy(
                            update={"text": "changed original initial text"}
                        )
                    }
                )
            else:
                inputs, receipt, reference = held.candidate_baseline
                held.candidate_baseline = (
                    inputs,
                    receipt.model_copy(update={"status": "unknown"}),
                    reference,
                )
            return original(self, request, before, *args, **kwargs)

        monkeypatch.setattr(ControlledActorContext, "prepare", prepare)
        with pytest.raises(TaskExecutionUnconfirmed) as failed:
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert injected == [fault] and c.native.loader.session.calls == 0
        assert failed.value.primary is not None
        assert r.inputs is not None and not r.inputs.active
        assert r.inputs.candidate_baseline is None and r.inputs.browser_acquired is None
        if fault == "deadline":
            read = c.p.plan.operation.cleanup(
                "inspect-original-failed-trace",
                now=c.p.original.resource.clock.utcnow(),
                seconds=30,
            )
            snapshot = c.handles.trace.read(read)
            assert snapshot.project().sealed is not None
            assert not snapshot.project().turns
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        elif fault == "storage":
            assert c.bundle.finalization.state.reset is None
