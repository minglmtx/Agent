"""Physical close proof is independent of the unknown business action result."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import pytest
from browser_closure_fixtures import ClosureCase, closure_case as closure_case
from test_browser_resource_installed import EngineeringTreeAuthority
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.errors import OperationStopped
from browser_closure_fixtures import controlled_timeout_configuration


def test_controlled_timeout_configuration_validated_before_installation() -> None:
    config = controlled_timeout_configuration(
        None, "fixture-job", "http://127.0.0.1:8000/"
    )
    assert config.spec.scope.owner.job_id == "fixture-job"
    assert config.spec.task.start_url == "http://127.0.0.1:8000/"
    assert 5000 < config.spec.action_timeout_ms <= 10000


@pytest.mark.parametrize("started", [True, False])
@pytest.mark.parametrize("forced", [False, True])
def test_original_launcher_exit_requires_complete_tree_proof(
    closure_case: ClosureCase, started: bool, forced: bool
) -> None:
    c = closure_case
    termination = (
        replace(c.termination, returncode=-9, kill_requested=True)
        if forced
        else c.termination
    )
    attempt = c.attempt if started else c.attempt.model_copy(update={"started": None})
    receipt = EngineeringTreeAuthority(c.resource.evidence).verify_closed(
        c.resource.spec,
        attempt,
        termination,
        c.step,
        c.resource.op,
        c.resource.controls.bind(c.resource.op),
    )
    assert receipt.status == "closed"
    proof = json.loads(c.resource.evidence.read(receipt.evidence[0]))
    assert proof["original_step_verified"] is True
    assert proof["termination"]["returncode"] == termination.returncode
    assert proof["termination"]["kill_requested"] == forced
    # The close receipt certifies a resource domain, never a business outcome.
    assert "evaluation" not in proof and "reset" not in proof


@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "unconfirmed",
        "wrong_pid",
        "unrequested_kill",
        "other_signal",
        "nonzero",
        "cleanup_error",
    ],
)
def test_unproven_launcher_never_closes(closure_case: ClosureCase, bad: str) -> None:
    c = closure_case
    termination: ProcessTermination | None = c.termination
    if bad == "missing":
        termination = None
    elif bad == "unconfirmed":
        termination = replace(c.termination, state="unconfirmed", returncode=None)
    elif bad == "wrong_pid":
        termination = (
            replace(c.termination, process_id=c.termination.process_id + 1)
            if c.termination.process_id is not None
            else None
        )
    elif bad == "unrequested_kill":
        termination = replace(c.termination, returncode=-9, kill_requested=False)
    elif bad == "other_signal":
        termination = replace(c.termination, returncode=-15, kill_requested=True)
    elif bad == "nonzero":
        termination = replace(c.termination, returncode=1)
    elif bad == "cleanup_error":
        termination = replace(c.termination, cleanup_errors=("original stop failed",))
    with pytest.raises(AssertionError):
        EngineeringTreeAuthority(c.resource.evidence).verify_closed(
            c.resource.spec,
            c.attempt,
            termination,
            c.step,
            c.resource.op,
            c.resource.controls.bind(c.resource.op),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "started"},
        {"schema_version": "browser-step-raw/0"},
        {"target": {}},
        {"kernel": []},
        {"kernel": None},
        {"kernel": [None]},
        {"kernel": "not observations"},
        {"commands": []},
        {"commands": None},
        {"commands": "not captures"},
        {"commands": [None]},
        {"commands": [{}]},
        {"commands": [{"complete": False, "returncode": 0}]},
        {"commands": [{"complete": True, "returncode": 1}]},
        {"commands": [{"complete": True, "returncode": False}]},
        {"error": "controller query failed"},
    ],
)
def test_partial_or_foreign_step_proof_never_closes(
    closure_case: ClosureCase, changes: dict[str, object]
) -> None:
    c = closure_case
    with pytest.raises(AssertionError):
        EngineeringTreeAuthority(c.resource.evidence).verify_closed(
            c.resource.spec,
            c.attempt,
            c.termination,
            c.raw_step(**changes),
            c.resource.op,
            c.resource.controls.bind(c.resource.op),
        )


@pytest.mark.parametrize("missing", ["prepared", "prepared_ref", "target", "step"])
def test_missing_original_binding_never_closes(
    closure_case: ClosureCase, missing: str
) -> None:
    c = closure_case
    attempt = (
        c.attempt if missing == "step" else c.attempt.model_copy(update={missing: None})
    )
    with pytest.raises(AssertionError):
        EngineeringTreeAuthority(c.resource.evidence).verify_closed(
            c.resource.spec,
            attempt,
            c.termination,
            None if missing == "step" else c.step,
            c.resource.op,
            c.resource.controls.bind(c.resource.op),
        )


def test_repeat_readonly_close_audit_keeps_same_proof(
    closure_case: ClosureCase,
) -> None:
    c = closure_case
    authority = EngineeringTreeAuthority(c.resource.evidence)
    receipts = [
        authority.verify_closed(
            c.resource.spec,
            c.attempt,
            c.termination,
            c.step,
            c.resource.op,
            c.resource.controls.bind(c.resource.op),
        )
        for _ in range(2)
    ]
    assert receipts[0] == receipts[1]
    assert c.resource.channels[0].starts == 1 and c.resource.channels[0].finishes == 1


def test_expired_audit_cannot_publish_a_closed_receipt(
    closure_case: ClosureCase,
) -> None:
    c = closure_case
    operation = c.resource.op.model_copy(
        update={
            "operation_id": "expired-close-audit",
            "deadline": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
    )
    with pytest.raises(OperationStopped, match="DEADLINE_EXCEEDED"):
        EngineeringTreeAuthority(c.resource.evidence).verify_closed(
            c.resource.spec,
            c.attempt,
            c.termination,
            c.step,
            operation,
            c.resource.controls.bind(operation),
        )
