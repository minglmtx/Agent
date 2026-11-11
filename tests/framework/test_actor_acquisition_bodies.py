"""Real Actor scope, synthetic body port; original ledger/kernel remain live."""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.models.actor_resource import registered_actor
from lab_generate_skill.domain.actor_acquisition_inputs import (
    ActorAcquisitionInputs,
    ActorAcquisitionBodies,
    ACTOR_ACQUISITION_BODY_LIMIT,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_resource_fixtures import ResourceCase
from test_actor_resource import c as c
from installed_source_fixtures import installed_sources as installed_sources
from worker_install_fixtures import installed_worker as installed_worker


class BodyPort:
    def __init__(self, c: ResourceCase) -> None:
        self.c = c
        self.calls = 0
        self.error: BaseException | None = None
        self.missing = False

    def read_original(
        self,
        selection: ActorAcquisitionInputs,
        operation: OperationContext,
        control: OperationControl,
    ) -> ActorAcquisitionBodies | None:
        self.calls += 1
        control.checkpoint()
        if self.error is not None:
            raise self.error
        if self.missing:
            return None
        return ActorAcquisitionBodies(
            selection=selection,
            intent_json=self.c.evidence.read(
                selection.intent_ref, control=control
            ).decode(),
            spec_json=self.c.evidence.read(
                selection.binding.spec_ref, control=control
            ).decode(),
            acquired_json=self.c.evidence.read(
                selection.binding.acquired_ref, control=control
            ).decode(),
        )


def test_scope_uses_one_fresh_proof_per_call_without_three_parent_leaf_reads(
    c: ResourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = c.controls.bind(c.op)
    reads = BodyPort(c)
    with registered_actor(c.spec, c.op, **c.dependencies()) as engine:
        scope = ActorExecutionScope(
            c.spec,
            c.journal,
            c.evidence,
            engine,
            c.op,
            control,
            cleanup_seconds=15,
            acquisition_reads=reads,
        )
        assert reads.calls == 1
        raw = scope.evidence.raw
        leaves: list[Any] = []
        record = scope._record
        records: list[Any] = []

        def counted(*args: Any, **kwargs: Any) -> bytes:
            leaves.append(args[0])
            return raw(*args, **kwargs)

        def fresh_record(*args: Any, **kwargs: Any) -> Any:
            records.append(args[0])
            return record(*args, **kwargs)

        monkeypatch.setattr(scope.evidence, "raw", counted)
        monkeypatch.setattr(scope, "_record", fresh_record)
        for _ in range(2):
            scope.require_original(scope.binding, c.op, control, live=True)
        assert reads.calls == 3 and len(records) == 2 and not leaves
        # Errors and cancellation cannot trigger legacy rereads or grant use.
        for error in (
            PermissionError("fresh permission denied"),
            OperationStopped("CANCELLED", c.op.operation_id),
            OSError("partial body proof"),
        ):
            reads.error = error
            with pytest.raises(type(error)):
                scope.require_original(scope.binding, c.op, control, live=True)
        reads.error = None
        reads.missing = True
        with pytest.raises(OwnershipConflict, match="not returned"):
            scope.require_original(scope.binding, c.op, control, live=True)
        reads.missing = False
        assert not leaves
        # Current journal and live kernel are still consulted, never cached.
        current = record(c.op, control)
        with monkeypatch.context() as p:
            p.setattr(
                scope,
                "_record",
                lambda *args: current.model_copy(
                    update={"events": current.events[:-1]}
                ),
            )
            with pytest.raises(EvidenceIntegrityError, match="acquisition changed"):
                scope.require_original(scope.binding, c.op, control, live=True)
        import lab_generate_skill.adapters.models.actor_execution_scope as module

        with monkeypatch.context() as p:
            p.setattr(
                module, "read_process_identity", lambda *args: scope.guard.controller
            )
            with pytest.raises(OwnershipConflict, match="process differs"):
                scope.require_original(scope.binding, c.op, control, live=True)
        # Legacy callers keep the exact original three bounded leaf reads.
        scope.acquisition_reads = None
        scope.require_original(scope.binding, c.op, control, live=True)
        assert len(leaves) == 3


def test_complete_body_fields_ref_bounds_and_scope_reject_changes(
    c: ResourceCase,
) -> None:
    control = c.controls.bind(c.op)
    reads = BodyPort(c)
    with registered_actor(c.spec, c.op, **c.dependencies()) as engine:
        scope = ActorExecutionScope(
            c.spec, c.journal, c.evidence, engine, c.op, control, cleanup_seconds=15
        )
        selection = ActorAcquisitionInputs(
            binding=scope.binding, intent_ref=scope._intent.evidence[0]
        )
        bodies = reads.read_original(selection, c.op, control)
        assert bodies is not None
        for field in ("intent_json", "spec_json", "acquired_json"):
            for damage in ("empty", "missing", "type", "bytes"):
                values = bodies.model_dump()
                if damage == "empty":
                    values[field] = ""
                elif damage == "missing":
                    del values[field]
                elif damage == "type":
                    values[field] = []
                else:
                    values[field] += " "
                with pytest.raises(ValidationError):
                    ActorAcquisitionBodies.model_validate(values)
        wrong = scope.binding.model_copy(
            update={
                "release_ref": scope.binding.release_ref.model_copy(
                    update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
                )
            }
        )
        with pytest.raises(ValidationError):
            ActorAcquisitionBodies.model_validate(
                {
                    **bodies.model_dump(),
                    "selection": {"binding": wrong, "intent_ref": selection.intent_ref},
                }
            )
        ref = selection.intent_ref.model_copy(
            update={"size_bytes": ACTOR_ACQUISITION_BODY_LIMIT + 1}
        )
        assert not ActorAcquisitionInputs(
            binding=scope.binding, intent_ref=ref
        ).supported()
        invalid_values: tuple[Any, ...] = (
            {},
            [],
            None,
            {"binding": scope.binding, "intent_ref": "wrong"},
        )
        for value in invalid_values:
            with pytest.raises(ValidationError):
                ActorAcquisitionInputs.model_validate(value)
