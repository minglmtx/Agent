"""Original production constructors through dispatch and owned failure cleanup."""

from collections import Counter
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.application.actor_context_review import (
    RecordedActorContextInputs,
)
from lab_generate_skill.application.actor_context_review_inputs import (
    ActorContextReviewInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import OperationStopped
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize("fault", ["none", "body", "storage", "cancel"])
def test_original_context_graph_reused_but_dispatch_gates_stay_current(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        original = RecordedActorContextInputs.verify
        read = ActorContextReviewInputs.read_verified
        reviews = []
        input_objects = []
        underlying_reads: Counter[Any] = Counter()

        def tracked(self: Any, reference: Any, control: Any) -> Any:
            original_read = self.original.read

            def measured(ref: Any, *args: Any, **kwargs: Any) -> Any:
                underlying_reads[ref] += 1
                return original_read(ref, *args, **kwargs)

            # History hits are outside the primary bodies view. Count the
            # actual original port, retaining the same once-only invariant.
            with monkeypatch.context() as reading:
                reading.setattr(self.original, "read", measured)
                return read(self, reference, control)

        def verify(self: Any, *args: Any, **kwargs: Any) -> Any:
            reviews.append(self)
            if len(reviews) == 2:
                assert self._inputs is not None and self._inputs.bodies
                if fault == "body":
                    ref = next(
                        ref
                        for ref in self._inputs.bodies
                        if ref.content_schema == "context-preparation/2"
                    )
                    self._inputs.bodies[ref] += b" "
                elif fault == "storage":
                    fixed.denied = True
                elif fault == "cancel":
                    raise OperationStopped("CANCELLED", "original-dispatch")
            value = original(self, *args, **kwargs)
            if self._inputs is not None and self._inputs not in input_objects:
                input_objects.append(self._inputs)
            return value

        monkeypatch.setattr(ActorContextReviewInputs, "read_verified", tracked)
        monkeypatch.setattr(RecordedActorContextInputs, "verify", verify)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.native.loader.session.calls == 1
            assert (
                len(reviews) >= 4
            )  # preflight, dispatch, before send, original return
            assert max(underlying_reads.values()) == 1
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert failed.value.primary is not None
            assert c.native.loader.session.calls == 0
            assert len(reviews) == 2
            if fault == "storage":
                assert c.bundle.finalization.state.reset is None
        assert input_objects and all(not value.bodies for value in input_objects)
        assert all(
            value._inputs is None and value._input_key is None for value in reviews
        )
        assert r.inputs is not None and not r.inputs.active
