"""Actual registered child/resource with synthetic inference; no GPU weights."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_worker_exchange import ActorWorkerExchange
from lab_generate_skill.adapters.models.actor_worker_protocol import (
    ActorWorkerCommand,
    ActorWorkerReply,
)
from lab_generate_skill.application.actor_generation import execute_actor_generation
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import (
    LocalActorParameters,
    LocalActorOutput,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_registered_fixtures import registered_call
from actor_resource_fixtures import ResourceCase
from test_actor_resource import c as c, inspect
from test_actor_protocol import turn
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


def test_registered_scope_trace_and_historical_completion(
    c: ResourceCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = c.controls.bind(c.op)
    calls: list[bytes] = []
    with registered_actor(c.spec, c.op, **c.dependencies()) as engine:
        scope = ActorExecutionScope(
            c.spec, c.journal, c.evidence, engine, c.op, control, cleanup_seconds=15
        )
        local = registered_call(
            c,
            scope,
            tmp_path / "local",
            turn(),
            LocalActorParameters(
                max_input_tokens=100,
                max_new_tokens=100,
                seed=42,
                temperature=0.7,
                top_p=0.95,
            ),
        )

        def generate(
            prompt: ActorPrompt, params: LocalActorParameters, control: OperationControl
        ) -> ActorWorkerExchange:
            command = ActorWorkerCommand(
                session_id=engine.session_id,
                sequence=3,
                operation="generate",
                remaining_seconds=control.checkpoint(),
                request=prompt,
                parameters=params,
            )
            reply = ActorWorkerReply(
                session_id=command.session_id,
                sequence=3,
                operation="generate",
                command_sha256=command.digest,
                status="ok",
                output=LocalActorOutput(
                    text='{"action":"click(2)"}',
                    finish_reason="stop",
                    prompt_tokens=3,
                    completion_tokens=2,
                ),
            )
            calls.append(command.model_dump_json().encode())
            return ActorWorkerExchange(calls[-1], reply.model_dump_json().encode())

        monkeypatch.setattr(engine, "generate_exchange", generate)
        monkeypatch.setattr(engine, "validate", lambda *args: None)
        intent = local.dispatch.intent.intent
        call_control = c.controls.bind(intent.operation)
        # Resource scope alone never substitutes for business admission.
        local.business.denied = True
        with pytest.raises(PermissionError, match="not admitted"):
            local.model.validate(intent, control=call_control)
        assert not calls and not list((tmp_path / "local/calls").iterdir())
        local.business.denied = False
        with pytest.raises(OwnershipConflict, match="phase"):
            local.model.generate(intent, control=call_control)
        assert not calls
        # Invalid owners/modes and cross-thread handles cannot grant calls.
        for update in (
            {"owner_id": "other"},
            {"allocation_id": "other"},
            {"mode": "cleanup", "parent_operation_id": "parent"},
        ):
            changed = OperationContext.model_validate(
                intent.operation.model_copy(update=update)
            )
            with pytest.raises(OwnershipConflict):
                scope.require_original(scope.binding, changed, call_control, live=True)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                scope.require_original,
                scope.binding,
                intent.operation,
                call_control,
                live=True,
            )
            with pytest.raises(OwnershipConflict):
                future.result()
        # The same canonical record is inspected under a distinct resource read
        # operation; the attempt's generation deadline/context remains unchanged.
        assert c.controls.bind(intent.operation) is call_control
        result = execute_actor_generation(
            local.dispatch, local.journal, local.model, c.controls
        )
        assert result.project().generation is not None and len(calls) == 1
        assert len(local.business.completed) == 1
        local.authority.verify_return(local.business.completed[0], call_control)
        assert len(calls) == 1
        # Live kernel identity and retained journal events are both mandatory.
        import lab_generate_skill.adapters.models.actor_execution_scope as module

        with monkeypatch.context() as patched:
            patched.setattr(
                module, "read_process_identity", lambda *args: scope.guard.controller
            )
            with pytest.raises(OwnershipConflict, match="process differs"):
                scope.require_original(
                    scope.binding, intent.operation, call_control, live=True
                )
        original_record = scope._record(intent.operation, call_control)
        with monkeypatch.context() as patched:
            changed_record = original_record.model_copy(
                update={"events": original_record.events[:-1]}
            )
            patched.setattr(scope, "_record", lambda *args: changed_record)
            with pytest.raises(EvidenceIntegrityError, match="acquisition changed"):
                scope.require_original(
                    scope.binding, intent.operation, call_control, live=False
                )
        # Configuration/scope substitution is rejected before any model effect.
        with pytest.raises(OwnershipConflict):
            scope.require_original(
                scope.binding.model_copy(update={"cleanup_seconds": 14}),
                intent.operation,
                call_control,
                live=True,
            )
    assert inspect(c).state == "closed"
    local.authority.verify_return(local.business.completed[0], call_control)
    with pytest.raises(OwnershipConflict, match="no longer acquired"):
        scope.require_original(scope.binding, intent.operation, call_control, live=True)
    with pytest.raises(OwnershipConflict, match="inside original acquired"):
        ActorExecutionScope(
            c.spec, c.journal, c.evidence, engine, c.op, control, cleanup_seconds=15
        )
    assert len(calls) == 1
