"""Original owned constructor and return authority, with explicit synthetic native edges."""

from collections import Counter
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.actor_execution_authority import (
    ResourceLocalActorAuthority,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "revoked",
        "cancel",
        "command",
        "reply",
        "response",
        "save",
        "scope",
        "reference",
    ],
)
def test_return_uses_same_request_inputs_and_preserves_dynamic_and_new_return_checks(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, resources):
        current = fixed_task_source_inputs(c, resources, monkeypatch)
        store = c.p.original.resource.evidence
        original_read, original_put = store.read, store.put
        original_verify = ResourceLocalActorAuthority.verify_return
        inside = False
        counts: Counter[Any] = Counter()
        returns = []
        authority_counts = []
        return_gates = []
        denied = [False]
        original_guard = c.native.scope.require_original

        def guard(binding: Any, operation: Any, control: Any, *, live: bool) -> None:
            if not live:
                return_gates.append(operation)
                if denied[0]:
                    raise OwnershipConflict(
                        "Original acquired-model return authority revoked"
                    )
            original_guard(binding, operation, control, live=live)

        monkeypatch.setattr(c.native.scope, "require_original", guard)
        rejected = []

        def read(ref: Any, control: Any = None) -> bytes:
            if inside:
                counts[ref] += 1
                if ref.content_schema == {
                    "command": "actor-worker-command/1",
                    "reply": "actor-worker-reply/1",
                    "response": "actor-model-response/1",
                }.get(fault):
                    return b"corrupt-return"
            return original_read(ref, control=control)

        def put(raw: bytes, meta: Any, control: Any = None, **kwargs: Any) -> Any:
            if fault == "save" and meta.content_schema == "local-actor-execution/1":
                raise OSError("Original return publication failed")
            return original_put(raw, meta, control=control, **kwargs)

        def verify(self: Any, execution: Any, control: Any) -> None:
            nonlocal inside
            returns.append(execution)
            assert self.inputs is not None
            held = self.inputs.generation_inputs(execution.call.intent, control)
            assert execution.call.intent.input_ref in held.bodies
            before = len(return_gates)
            if fault == "revoked":
                denied[0] = True
            if fault == "cancel":
                raise OperationStopped(
                    "CANCELLED", execution.call.intent.operation.operation_id
                )
            if fault == "scope":
                intent = execution.call.intent
                changed = intent.model_copy(
                    update={
                        "scope": intent.scope.model_copy(
                            update={"attempt_id": "foreign-attempt"}
                        )
                    }
                )
                with pytest.raises((OwnershipConflict, ValueError)):
                    self.inputs.generation_inputs(changed, control)
                rejected.append(fault)
                raise OperationStopped("CANCELLED", intent.operation.operation_id)
            if fault == "reference":
                intent = execution.call.intent
                with pytest.raises((OwnershipConflict, ValueError)):
                    self.inputs.generation_inputs(
                        intent.model_copy(update={"input_ref": execution.response_ref}),
                        control,
                    )
                rejected.append(fault)
                raise OperationStopped("CANCELLED", intent.operation.operation_id)
            inside = True
            try:
                original_verify(self, execution, control)
            finally:
                inside = False
                authority_counts.append((before, len(return_gates)))

        monkeypatch.setattr(store, "read", read)
        monkeypatch.setattr(store, "put", put)
        monkeypatch.setattr(ResourceLocalActorAuthority, "verify_return", verify)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            e = returns[0]
            assert (
                counts[e.call.intent.input_ref]
                == counts[e.call.intent.parameters_ref]
                == 0
            )
            assert all(
                counts[ref] == 1 for ref in (e.command_ref, e.reply_ref, e.response_ref)
            )
            assert all(after > before for before, after in authority_counts)
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert failed.value.primary is not None
        if fault in {"scope", "reference"}:
            assert rejected == [fault]
        assert len(returns) == 1 and c.native.loader.session.calls == 1
        assert resources.inputs is not None and not resources.inputs.active


def test_actual_return_first_error_and_lost_store_keep_bounded_physical_cleanup(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lab_generate_skill.adapters.browsergym.retained_resource import (
        RetainedBrowserResource,
    )
    from lab_generate_skill.adapters.models.local_actor import LocalActorUnconfirmed

    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, resources):
        fixed_task_source_inputs(c, resources, monkeypatch)
        store = c.p.original.resource.evidence
        first = OperationStopped("DEADLINE_EXCEEDED", c.p.plan.operation.operation_id)
        storage = OSError("Original store unavailable after returned generation")
        finishes = []
        original_finish = RetainedBrowserResource._finish

        def finish(self: Any, primary: Any) -> None:
            if self.phase == "open":
                finishes.append(self)
            original_finish(self, primary)

        monkeypatch.setattr(RetainedBrowserResource, "_finish", finish)
        with monkeypatch.context() as patch:

            def unavailable(*args: Any, **kwargs: Any) -> Any:
                raise storage

            def fail(self: Any, execution: Any, control: Any) -> None:
                patch.setattr(store, "read", unavailable)
                patch.setattr(store, "put", unavailable)
                raise first

            patch.setattr(ResourceLocalActorAuthority, "verify_return", fail)
            with pytest.raises(BaseExceptionGroup) as caught:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)

            def errors(value: Any, seen: set[int]) -> list[BaseException]:
                if not isinstance(value, BaseException) or id(value) in seen:
                    return []
                seen.add(id(value))
                result = [value]
                for child in (
                    getattr(value, "primary", None),
                    value.__cause__,
                    *getattr(value, "exceptions", ()),
                    *getattr(value, "cleanup_errors", ()),
                ):
                    result.extend(errors(child, seen))
                return result

            all_errors = errors(caught.value, set())
            assert first in all_errors and storage in all_errors
            assert any(isinstance(e, TaskExecutionUnconfirmed) for e in all_errors)
            assert any(
                isinstance(e, LocalActorUnconfirmed) and e.exchange is not None
                for e in all_errors
            )
            assert len(finishes) == 1 and finishes[0] is c.handles.browser
            held = c.handles.browser
            assert held.phase == "close-unconfirmed" and held.closed is None
            op = held.operation.cleanup(
                "return-failure-recheck", now=held.clock.utcnow(), seconds=30
            )
            with pytest.raises(BaseException):
                held.close(op, held.controls.bind(op))
            assert len(finishes) == 1
        assert c.native.loader.session.calls == 1
        assert resources.inputs is not None and not resources.inputs.active


@pytest.mark.parametrize("bad", [False, "input-provider", {}, object()])
def test_return_input_provider_requires_the_scoped_supplier(bad: Any) -> None:
    edge: Any = object()
    with pytest.raises(TypeError, match="scoped generation input supplier"):
        ResourceLocalActorAuthority(edge, edge, inputs=bad)
