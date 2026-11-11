"""Real source/init/Actor constructors; synthetic kernel/model edges are explicit.

The underlying fixture runs preparation, first request, judgment and finalization.
These checks measure graph dispatch, never production performance or permission.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.task_actor_authority import (
    OriginalTaskActorAuthority,
)
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.adapters.plans.task_context_authority import (
    OriginalTaskContextAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_records import ClosedSourceContexts
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.bootstrap.task_candidate_inputs import (
    InitializedTaskCandidateInputs,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault", ["none", "reference", "dependency", "revoked", "cancel", "closed-scope"]
)
def test_original_task_passes_published_inputs_to_first_actor_gate(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        original_verify = OriginalTaskActorAuthority.verify
        original_baseline = BaselineEvidenceReader.verify
        original_initial = InitialObservationReader.load
        original_source = OriginalTaskContextAuthority._source_inputs
        original_context_load = ClosedSourceContexts.load_context_inputs
        actor_started = False
        candidate_started = False
        original_candidate = InitializedTaskCandidateInputs.load
        gates = []
        source_loads = []

        def source_load(self: Any, *args: Any, **kwargs: Any) -> Any:
            source_loads.append(1)
            return original_context_load(self, *args, **kwargs)

        def baseline(self: Any, *args: Any, **kwargs: Any) -> Any:
            if candidate_started and self in (
                c.bundle.initialization.original().states.baselines,
                c.bundle.initialization.original().contexts.facts.baselines,
            ):
                pytest.fail("Actor rebuilt the already published baseline graph")
            return original_baseline(self, *args, **kwargs)

        def initial(self: Any, *args: Any, **kwargs: Any) -> Any:
            authority = (
                c.bundle.initialization.original().contexts.facts.authority
                if candidate_started
                else None
            )
            if (
                candidate_started
                and isinstance(authority, OriginalTaskContextAuthority)
                and self is authority.initials
            ):
                pytest.fail("Actor rebuilt the original initial observation graph")
            return original_initial(self, *args, **kwargs)

        def source(self: Any, op: Any, control: Any) -> Any:
            before = len(source_loads)
            value = original_source(self, op, control)
            if actor_started:
                assert len(source_loads) == before
                gates.append("source-current")
            return value

        def verify(self: Any, request: Any, snapshot: Any, control: Any) -> None:
            nonlocal actor_started
            actor_started = True
            held = self.initialization().inputs
            assert held is not None and held.active and held.equivalence is not None
            reference, inputs, dependencies = held.equivalence
            if fault == "reference":
                held.equivalence = (
                    reference.model_copy(update={"producer": "foreign"}),
                    inputs,
                    dependencies,
                )
            elif fault == "dependency":
                held.equivalence = (reference, inputs, {})
            elif fault == "closed-scope":
                held.active = False
            elif fault == "revoked":

                def denied(*args: Any, **kwargs: Any) -> None:
                    raise PermissionError("Original resource authority revoked")

                monkeypatch.setattr(r, "require_browser", denied)
            elif fault == "cancel":
                raise OperationStopped("CANCELLED", request.operation.operation_id)
            original_verify(self, request, snapshot, control)

        def candidate(self: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal candidate_started
            candidate_started = True
            return original_candidate(self, *args, **kwargs)

        monkeypatch.setattr(InitializedTaskCandidateInputs, "load", candidate)
        monkeypatch.setattr(ClosedSourceContexts, "load_context_inputs", source_load)
        monkeypatch.setattr(OriginalTaskContextAuthority, "_source_inputs", source)
        monkeypatch.setattr(BaselineEvidenceReader, "verify", baseline)
        monkeypatch.setattr(InitialObservationReader, "load", initial)
        monkeypatch.setattr(OriginalTaskActorAuthority, "verify", verify)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert c.native.loader.session.calls == 1 and gates
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
            browser = r.browser()
            assert browser is not None and browser.phase == "closed"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            expected = (
                PermissionError
                if fault == "revoked"
                else OperationStopped if fault == "cancel" else OwnershipConflict
            )
            pending: list[BaseException] = [caught.value]
            errors: list[BaseException] = []
            while pending:
                error = pending.pop()
                if any(error is prior for prior in errors):
                    continue
                errors.append(error)
                for value in (
                    error.__cause__,
                    error.__context__,
                    getattr(error, "primary", None),
                ):
                    if isinstance(value, BaseException):
                        pending.append(value)
            assert any(isinstance(error, expected) for error in errors)
            assert c.native.loader.session.calls == 0
        assert actor_started
        held = c.bundle.initialization.original().inputs
        assert held is not None and not held.active
        assert held.source is None
        assert held.initial is None
        assert held.equivalence is None
        assert c.journals.source_reader._task_facts is None
        assert c.journals.source_reader._task_plan is None
        with pytest.raises(OwnershipConflict):
            held.check(
                c.p.plan.operation,
                c.p.original.resource.controls.bind(c.p.plan.operation),
            )
        with pytest.raises(OwnershipConflict):
            with held.scope():
                pass


@pytest.mark.parametrize("close_error", [False, True])
def test_partial_initialization_keeps_primary_and_cleanup_and_drops_inputs(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, close_error: bool
) -> None:
    from lab_generate_skill.adapters.storage.context_records import (
        EvidenceContextRecords,
    )

    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        primary = OSError("Original candidate equivalence publication unconfirmed")
        closing = OSError("Original task close acknowledgement unconfirmed")
        original_close = c.bundle.finalization.close
        calls = []

        def publish(*args: Any, **kwargs: Any) -> Any:
            held = c.bundle.initialization.original().inputs
            assert held is not None and held.active and held.initial is not None
            assert held.equivalence is None
            calls.append("initial")
            raise primary

        def close(*args: Any, **kwargs: Any) -> Any:
            calls.append("close")
            result = original_close(*args, **kwargs)
            if close_error:
                raise closing
            return result

        monkeypatch.setattr(
            EvidenceContextRecords, "publish_equivalence_inputs", publish
        )
        monkeypatch.setattr(c.bundle.finalization, "close", close)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        from lab_generate_skill.adapters.sites.task_initialization import (
            TaskInitializationUnconfirmed,
        )

        assert isinstance(caught.value.primary, TaskInitializationUnconfirmed)
        assert caught.value.primary.primary is primary
        assert (closing in caught.value.cleanup_errors) == close_error
        assert calls == ["initial", "close"]
        assert c.native.loader.session.calls == 0
        if close_error:
            assert c.bundle.finalization.state.reset is None
        else:
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        held = c.bundle.initialization.original().inputs
        assert held is not None and not held.active
        assert held.initial is None and held.source is None and held.equivalence is None
        assert c.journals.source_reader._task_plan is None
        assert c.journals.source_reader._task_facts is None
