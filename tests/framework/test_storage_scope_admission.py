"""State/race/failure checks; fake observations never count as real admission."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock
import pytest
from lab_generate_skill.adapters.storage import scope_admission as module
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.claims import SourceClaimReader
from lab_generate_skill.domain.lifecycle import OperationContext
from storage_scope_fixtures import scope, operation, observation
from cgroup_fixtures import Control


def prepared(
    monkeypatch: pytest.MonkeyPatch, *, source: bool = False
) -> tuple[Any, Any, Any, Any]:
    bound = scope(source=source)
    observed = observation(bound)
    monkeypatch.setattr(module, "current_process_identity", lambda: bound.writer)
    observe = Mock(return_value=observed)
    monkeypatch.setattr(module, "observe_current_cgroup", observe)
    claims = None
    if bound.claim is not None:
        claims = Mock(spec=SourceClaimReader)
        claims.read.return_value = SourceClaimRecord(
            binding=bound.claim, operation=operation(bound, "claim")
        )
    admission = module.PinnedSlurmStorageAdmission(bound)
    return bound, admission, claims, observe


def cleanup(op: OperationContext) -> OperationContext:
    return op.cleanup(
        "cleanup-" + op.operation_id, now=datetime.now(timezone.utc), seconds=10
    )


@pytest.mark.parametrize("source", [False, True])
def test_activation_reads_once_no_recursive_claim_io(
    monkeypatch: pytest.MonkeyPatch, source: bool
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch, source=source)
    original_control = Control()
    admission.activate(claims, operation(bound), original_control)
    op = operation(bound, "io")
    admission.authorize_storage(bound.binding, bound.config, op, Control())
    admission.stop_new_io()
    admission.stop_new_io()
    before = observe.call_count
    admission.authorize_cleanup(
        bound.binding, bound.config, op, cleanup(op), None, Control()
    )
    assert observe.call_count == before == 3
    if claims is not None:
        claims.read.assert_called_once_with(
            bound.claim.key,
            operation_arg := claims.read.call_args.args[1],
            control=original_control,
        )
        assert operation_arg.operation_id == "activate"
        assert admission.source_record == claims.read.return_value
        assert len(claims.mock_calls) == 1
    with pytest.raises(InvalidTransition):
        admission.authorize_storage(
            bound.binding, bound.config, operation(bound, "new"), Control()
        )
    with pytest.raises(InvalidTransition):
        admission.activate(claims, operation(bound), Control())


@pytest.mark.parametrize(
    "failure",
    ["missing_claims", "wrong_claim", "claim_error", "observer_error", "moved", "stop"],
)
def test_activation_failure_is_terminal(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch, source=True)
    if failure == "missing_claims":
        claims = None
    elif failure == "wrong_claim":
        claims.read.return_value = claims.read.return_value.model_copy(
            update={"binding": bound.claim.model_copy(update={"scope_id": "other"})}
        )
    elif failure == "claim_error":
        claims.read.side_effect = OSError("claim unavailable")
    elif failure == "observer_error":
        observe.side_effect = OSError("kernel unavailable")
    elif failure == "moved":
        before = observation(bound)
        observe.side_effect = [
            before,
            replace(
                before,
                membership=before.membership.model_copy(update={"user_inode": 999}),
            ),
        ]
    else:
        claims.read.side_effect = lambda *_, **__: (
            admission.stop_new_io(),
            claims.read.return_value,
        )[1]
    with pytest.raises((ValueError, RuntimeError, OSError)):
        admission.activate(claims, operation(bound), Control())
    assert admission.source_record is None
    with pytest.raises(InvalidTransition):
        admission.activate(claims, operation(bound), Control())
    with pytest.raises(InvalidTransition):
        admission.authorize_storage(
            bound.binding, bound.config, operation(bound, "new"), Control()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", "attempt"),
        ("allocation_id", "allocation"),
        ("owner_id", "other"),
        ("run_id", "other"),
        ("parent_operation_id", "parent"),
    ],
)
def test_wrong_operation_no_observation(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch)
    admission.activate(claims, operation(bound), Control())
    op = operation(bound, "io").model_copy(update={field: value})
    with pytest.raises(OwnershipConflict):
        admission.authorize_storage(bound.binding, bound.config, op, Control())
    assert observe.call_count == 2


def test_duplicate_admission_race_and_no_thread_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch)
    admission.activate(claims, operation(bound), Control())
    op = operation(bound, "io")

    def run() -> bool:
        try:
            admission.authorize_storage(bound.binding, bound.config, op, Control())
            return True
        except InvalidTransition:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(), range(2))) == [False, True]
    admission.authorize_cleanup(
        bound.binding, bound.config, op, cleanup(op), None, Control()
    )


@pytest.mark.parametrize("failure", ["writer", "membership", "stop", "cancel"])
def test_per_io_denial_does_not_authorize_cleanup(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch)
    admission.activate(claims, operation(bound), Control())
    if failure == "writer":
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: bound.writer.model_copy(update={"start_ticks": 999}),
        )
    elif failure == "membership":
        before = observation(bound)
        observe.return_value = replace(
            before, membership=before.membership.model_copy(update={"task_inode": 999})
        )
    elif failure == "stop":
        observe.side_effect = lambda *_: (admission.stop_new_io(), observation(bound))[
            1
        ]
    else:
        observe.side_effect = TimeoutError("cancelled at observation")
    op = operation(bound, "io")
    with pytest.raises((RuntimeError, ValueError, TimeoutError)):
        admission.authorize_storage(bound.binding, bound.config, op, Control())
    monkeypatch.setattr(module, "current_process_identity", lambda: bound.writer)
    with pytest.raises(OwnershipConflict):
        admission.authorize_cleanup(
            bound.binding, bound.config, op, cleanup(op), None, Control()
        )


@pytest.mark.parametrize(
    "failure", ["config", "binding", "unknown", "changed_original", "parent", "writer"]
)
def test_cleanup_rejects_wrong_scope(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    bound, admission, claims, observe = prepared(monkeypatch)
    admission.activate(claims, operation(bound), Control())
    op = operation(bound, "io")
    admission.authorize_storage(bound.binding, bound.config, op, Control())
    clean = cleanup(op)
    binding, config = bound.binding, bound.config
    if failure == "config":
        config = config.model_copy(update={"max_object_bytes": 100})
    elif failure == "binding":
        binding = binding.model_copy(update={"session_id": "other"})
    elif failure == "unknown":
        op = operation(bound, "unknown")
        clean = cleanup(op)
    elif failure == "changed_original":
        op = op.model_copy(update={"deadline": clean.deadline})
    elif failure == "parent":
        clean = clean.model_copy(update={"parent_operation_id": "other"})
    else:
        monkeypatch.setattr(
            module,
            "current_process_identity",
            lambda: bound.writer.model_copy(update={"start_ticks": 999}),
        )
    with pytest.raises((ValueError, RuntimeError)):
        admission.authorize_cleanup(binding, config, op, clean, None, Control())


@pytest.mark.parametrize("case", ["unactivated", "run_with_claims", "pre_stopped"])
def test_unavailable_admission_has_no_kernel_or_claim_io(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    bound, admission, _, observe = prepared(monkeypatch)
    claims = Mock(spec=SourceClaimReader)
    if case == "unactivated":
        with pytest.raises(InvalidTransition):
            admission.authorize_storage(
                bound.binding, bound.config, operation(bound, "io"), Control()
            )
    else:
        if case == "pre_stopped":
            admission.stop_new_io()
        with pytest.raises((InvalidTransition, OwnershipConflict)):
            admission.activate(claims, operation(bound), Control())
    assert observe.call_count == 0 and not claims.mock_calls


@pytest.mark.parametrize(
    "case", ["wrong_controller", "invalid_ending", "cancelled_cleanup"]
)
def test_cleanup_ending_and_cancellation_rejected(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from lab_generate_skill.domain.lifecycle import CancellationRef
    from lab_generate_skill.domain.storage_termination import StorageProcessEnd

    bound, admission, claims, observe = prepared(monkeypatch)
    admission.activate(claims, operation(bound), Control())
    op = operation(bound, "io")
    admission.authorize_storage(bound.binding, bound.config, op, Control())
    clean = cleanup(op)
    ending: Any = None
    if case == "cancelled_cleanup":
        clean = clean.model_copy(
            update={
                "cancellation_ref": CancellationRef(
                    channel_id="cancel", run_id=op.run_id, owner_id=op.owner_id
                )
            }
        )
    elif case == "invalid_ending":
        ending = {}
    else:
        ending = StorageProcessEnd(
            controller=bound.writer.model_copy(update={"start_ticks": 999}),
            request_sha256="0" * 64,
            process_id=124,
            returncode=0,
            observed_at=datetime.now(timezone.utc),
            capture_sha256="1" * 64,
            kill_requested=False,
        )
    with pytest.raises((ValueError, RuntimeError)):
        admission.authorize_cleanup(
            bound.binding, bound.config, op, clean, ending, Control()
        )
    assert observe.call_count == 3


def test_full_private_task_claim_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_run_plan import reference

    bound, admission, claims, observe = prepared(monkeypatch, source=True)
    task = bound.claim.task.model_copy(
        update={"private_spec_ref": reference("different/1")}
    )
    claims.read.return_value = claims.read.return_value.model_copy(
        update={"binding": bound.claim.model_copy(update={"task": task})}
    )
    with pytest.raises(OwnershipConflict):
        admission.activate(claims, operation(bound), Control())
    assert observe.call_count == 1
