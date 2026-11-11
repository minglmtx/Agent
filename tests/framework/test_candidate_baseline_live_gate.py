"""Actual owned constructors; transport/kernel premises remain explicit fixtures.

Count physical resource checks in one baseline call, including real first Actor
admission and the closed-browser cleanup branch. These are not timing claims.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.models.task_actor_authority import (
    OriginalTaskActorAuthority,
)
from lab_generate_skill.adapters.plans.task_context_authority import (
    OriginalTaskContextAuthority,
)
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from site_instance_fixtures import node_path as node_path
from task_actor_input_fixtures import fixed_task_source_inputs
from task_resource_owner_fixtures import owned_task


@pytest.mark.parametrize("handoff", [False, True])
def test_actual_candidate_baseline_uses_one_live_check_and_keeps_other_operations(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, handoff: bool
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=handoff) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        original = OriginalTaskContextAuthority.verify_baseline
        original_actor = OriginalTaskActorAuthority.verify
        require = r.require
        active: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        actor_depth = 0

        def resource(operation: Any, control: Any, *, live: bool) -> Any:
            if active:
                active[-1]["checks"].append((operation, live))
            return require(operation, control, live=live)

        def baseline(self: Any, inputs: Any, receipt: Any, op: Any) -> None:
            initial = self.initialization()
            if self.resources is not r or receipt.scope != initial.declaration.scope:
                return original(self, inputs, receipt, op)
            browser = r.browser()
            assert browser is not None
            entry = {
                "operation": op,
                "open": browser.phase == "open",
                "actor": actor_depth > 0,
                "checks": [],
            }
            active.append(entry)
            try:
                original(self, inputs, receipt, op)
            finally:
                assert active.pop() is entry
                checks.append(entry)

        def actor(self: Any, *args: Any) -> None:
            nonlocal actor_depth
            actor_depth += 1
            try:
                return original_actor(self, *args)
            finally:
                actor_depth -= 1

        monkeypatch.setattr(r, "require", resource)
        monkeypatch.setattr(OriginalTaskContextAuthority, "verify_baseline", baseline)
        monkeypatch.setattr(OriginalTaskActorAuthority, "verify", actor)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success"
        assert c.native.loader.session.calls == 1
        assert c.bundle.finalization.state.reset is not None
        assert c.bundle.finalization.state.reset.status == "safe"
        assert checks and any(e["actor"] for e in checks)
        assert any(e["open"] and e["operation"] != r.plan.operation for e in checks)
        for e in checks:
            expected = []
            if not e["open"] or e["operation"] != r.plan.operation:
                expected.append((e["operation"], False))
            if e["open"]:
                expected.append((r.plan.operation, True))
            assert e["checks"][: len(expected)] == expected
            # The legacy initial reader independently verifies its bounded
            # cleanup resource read. Keep and count that distinct consumer.
            for operation, live in e["checks"][len(expected) :]:
                assert not handoff and live is False
                assert operation.mode == "cleanup"
                assert operation.operation_id.startswith("task-resource-read-")
                assert operation != e["operation"]


def test_closed_candidate_baseline_keeps_original_cleanup_check(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        states = c.bundle.finalization.states
        assert isinstance(states, EvidenceStateRecords)
        publish = states.publish_reset_verified
        require = r.require
        checks: list[tuple[Any, bool]] = []
        active = False
        probes: list[Any] = []

        def resource(operation: Any, control: Any, *, live: bool) -> Any:
            if active:
                checks.append((operation, live))
            return require(operation, control, live=live)

        def reset(receipt: Any, op: Any) -> Any:
            nonlocal active
            browser = r.browser()
            assert browser is not None and browser.phase == "closed"
            initial = c.bundle.initialization.original()
            authority = initial.contexts.facts.authority
            assert isinstance(authority, OriginalTaskContextAuthority)
            assert initial.state.baseline_inputs is not None
            assert initial.state.baseline is not None
            active = True
            try:
                authority.verify_baseline(
                    initial.state.baseline_inputs,
                    initial.state.baseline,
                    r.plan.operation,
                )
            finally:
                active = False
            assert checks == [(r.plan.operation, False)]
            probes.append(op)
            return publish(receipt, op)

        monkeypatch.setattr(r, "require", resource)
        monkeypatch.setattr(states, "publish_reset_verified", reset)
        result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert result.evaluation.status == "success" and len(probes) == 1
        assert c.native.loader.session.calls == 1


@pytest.mark.parametrize("fault", ["claim", "cancel"])
def test_first_actor_baseline_keeps_fresh_claim_and_cancellation(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed_task_source_inputs(c, r, monkeypatch)
        original = OriginalTaskContextAuthority.verify_baseline
        original_actor = OriginalTaskActorAuthority.verify
        require = r.require
        actor_depth = baseline_depth = 0
        injected: list[Any] = []

        class Cancelled:
            """Explicit cancellation edge, never an authority permit."""

            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", r.plan.operation.operation_id)

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        def resource(operation: Any, control: Any, *, live: bool) -> Any:
            if actor_depth and baseline_depth and live and not injected:
                injected.append(operation)
                assert operation == r.plan.operation
                if fault == "cancel":
                    return require(operation, Cancelled(), live=live)
                monkeypatch.setattr(c.journals.claim_authority, "denied", True)
                try:
                    return require(operation, control, live=live)
                finally:
                    monkeypatch.setattr(c.journals.claim_authority, "denied", False)
            return require(operation, control, live=live)

        def baseline(self: Any, *args: Any) -> None:
            nonlocal baseline_depth
            baseline_depth += 1
            try:
                return original(self, *args)
            finally:
                baseline_depth -= 1

        def actor(self: Any, *args: Any) -> None:
            nonlocal actor_depth
            actor_depth += 1
            try:
                return original_actor(self, *args)
            finally:
                actor_depth -= 1

        monkeypatch.setattr(r, "require", resource)
        monkeypatch.setattr(OriginalTaskContextAuthority, "verify_baseline", baseline)
        monkeypatch.setattr(OriginalTaskActorAuthority, "verify", actor)
        with pytest.raises(TaskExecutionUnconfirmed) as caught:
            c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
        assert len(injected) == 1 and c.native.loader.session.calls == 0
        errors: list[BaseException] = []
        pending: list[BaseException] = [caught.value]
        while pending:
            error = pending.pop()
            if any(error is e for e in errors):
                continue
            errors.append(error)
            pending.extend(
                e
                for e in (
                    error.__cause__,
                    error.__context__,
                    getattr(error, "primary", None),
                )
                if isinstance(e, BaseException)
            )
        expected = OperationStopped if fault == "cancel" else OwnershipConflict
        assert any(isinstance(e, expected) for e in errors)
        if fault == "claim":
            assert any("unit claim caller denied" in str(e) for e in errors)
