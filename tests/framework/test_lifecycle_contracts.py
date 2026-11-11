"""Lifecycle data boundaries and the complete documented resource state graph.

Expected transitions come from architecture section 6, not the implementation.
Pure contracts need no provider, database, wall-clock sleep or real resources.
"""

from datetime import datetime, timezone
from itertools import product

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ClosureReceipt,
    OperationContext,
    RecoveryPlan,
    ResourceEvent,
    ResourceOwner,
    ResourceRecord,
    ResourceState,
    require_resource_transition,
)


@pytest.fixture
def proof() -> EvidenceRef:
    return EvidenceRef(
        uri="cas://sha256/" + "a" * 64,
        sha256="a" * 64,
        size_bytes=0,
        media_type="application/json",
        content_schema="recovery-plan/1",
        visibility="private",
        producer="controller",
    )


@pytest.fixture
def owner() -> ResourceOwner:
    return ResourceOwner(
        run_id="run", owner_id="owner", job_id="job", worker_id="worker"
    )


@pytest.fixture
def token(owner: ResourceOwner, proof: EvidenceRef) -> AllocationToken:
    return AllocationToken(
        allocation_id="allocation",
        owner=owner,
        scope="attempt",
        attempt_id="attempt",
        resource_kind="site",
        expected_resource_id="instance",
        provider_id="provider",
        provider_version="1",
        recovery_ref=proof,
    )


STATES: tuple[ResourceState, ...] = (
    "registered",
    "acquiring",
    "acquired",
    "closing",
    "closed",
    "quarantined",
)
VALID_EDGES = {
    ("registered", "acquiring"),
    ("acquiring", "acquired"),
    ("acquiring", "closing"),
    ("acquiring", "quarantined"),
    ("registered", "closing"),
    ("registered", "quarantined"),
    ("acquired", "closing"),
    ("acquired", "quarantined"),
    ("closing", "closed"),
    ("closing", "quarantined"),
}


@pytest.mark.parametrize(("before", "after"), list(product(STATES, STATES)))
def test_entire_resource_transition_contract(
    before: ResourceState, after: ResourceState
) -> None:
    if (before, after) in VALID_EDGES:
        require_resource_transition(before, after)
    else:
        with pytest.raises(InvalidTransition):
            require_resource_transition(before, after)


@pytest.mark.parametrize("invalid", [None, "", " ", 0, False, [], {}, "x" * 257])
def test_owner_identity_rejects_missing_empty_wrong_type_and_oversize(
    owner: ResourceOwner,
    invalid: object,
) -> None:
    data = owner.model_dump()
    data["owner_id"] = invalid
    with pytest.raises(ValidationError):
        ResourceOwner.model_validate(data)


@pytest.mark.parametrize("identity", ["a", "a" * 256])
def test_owner_identity_accepts_length_boundaries(
    owner: ResourceOwner, identity: str
) -> None:
    data = owner.model_dump()
    data["owner_id"] = identity
    result = ResourceOwner.model_validate(data)
    assert ResourceOwner.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("data", [{}, {"schema_version": "resource-owner/99"}])
def test_owner_empty_input_is_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResourceOwner.model_validate(data)


@pytest.mark.parametrize(
    ("scope", "attempt"), [("attempt", None), ("batch", "attempt"), ("unknown", None)]
)
def test_allocation_scope_cannot_lose_or_invent_attempt(
    token: AllocationToken, scope: str, attempt: str | None
) -> None:
    data = token.model_dump()
    data.update(scope=scope, attempt_id=attempt)
    with pytest.raises(ValidationError):
        AllocationToken.model_validate(data)


@pytest.mark.parametrize(
    ("visibility", "schema"),
    [
        ("public", "recovery-plan/1"),
        ("teacher", "recovery-plan/1"),
        ("private", "baseline/1"),
    ],
)
def test_allocation_requires_private_recovery_schema(
    token: AllocationToken, proof: EvidenceRef, visibility: str, schema: str
) -> None:
    ref = proof.model_dump()
    ref.update(visibility=visibility, content_schema=schema)
    data = token.model_dump()
    data["recovery_ref"] = EvidenceRef.model_validate(ref)
    with pytest.raises(ValidationError):
        AllocationToken.model_validate(data)


@pytest.mark.parametrize("coverage", [(), ("",), (" ",), ("db", "db"), ["db"], None])
def test_recovery_coverage_rejects_empty_duplicate_and_wrong_type(
    owner: ResourceOwner, proof: EvidenceRef, coverage: object
) -> None:
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(
            dict(
                recovery_id="restore",
                owner=owner,
                baseline_ref=proof,
                restore_component_id="site.restore",
                restore_component_version="1",
                state_coverage=coverage,
            )
        )


def event(
    token: AllocationToken,
    name: str,
    state: ResourceState,
    evidence: tuple[EvidenceRef, ...] = (),
) -> ResourceEvent:
    execute = state in ("registered", "acquiring", "acquired")
    op = OperationContext(
        operation_id=name,
        run_id=token.owner.run_id,
        owner_id=token.owner.owner_id,
        attempt_id=token.attempt_id,
        allocation_id=token.allocation_id,
        recovery_ref=token.recovery_ref,
        deadline=datetime(2030, 1, 1, tzinfo=timezone.utc),
        mode="execute" if execute else "cleanup",
        parent_operation_id=None if execute else "register",
    )
    return ResourceEvent(operation=op, state=state, evidence=evidence)


def test_empty_duplicate_missing_proof_and_wrong_initial_histories(
    token: AllocationToken, proof: EvidenceRef
) -> None:
    first = event(token, "register", "registered")
    malformed = (
        (),
        (event(token, "start", "acquired", evidence=(proof,)),),
        (
            first,
            event(token, "register", "acquired", evidence=(proof,)),
        ),
        (first, event(token, "acquire", "acquired")),
        (first, event(token, "close", "closed", evidence=(proof,))),
    )
    for events in malformed:
        with pytest.raises(ValidationError):
            ResourceRecord(token=token, events=events)


def test_valid_history_round_trip_and_immutable_input(
    token: AllocationToken, proof: EvidenceRef
) -> None:
    first = event(token, "register", "registered")
    prior = ResourceRecord(token=token, events=(first,))
    closed = ResourceRecord(
        token=token,
        events=(
            first,
            event(token, "closing", "closing", evidence=(proof,)),
            event(token, "closed", "closed", evidence=(proof,)),
        ),
    )
    assert ResourceRecord.model_validate_json(closed.model_dump_json()) == closed
    assert prior.events == (first,)
    assert closed.token == token
    with pytest.raises(ValidationError):
        ResourceRecord.model_validate(
            {**closed.model_dump(), "schema_version": "resource-record/99"}
        )


@pytest.mark.parametrize("status", ["closed", "failed"])
def test_closure_cannot_claim_success_or_failure_without_evidence(
    token: AllocationToken, status: str
) -> None:
    with pytest.raises(ValidationError):
        ClosureReceipt.model_validate(
            dict(token=token, operation_id="close", status=status, evidence=())
        )


def test_cleanup_parent_must_be_present_and_distinct() -> None:
    data = dict(
        operation_id="cleanup",
        run_id="run",
        owner_id="owner",
        mode="cleanup",
        deadline=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    for parent in (None, "cleanup"):
        with pytest.raises(ValidationError):
            OperationContext.model_validate({**data, "parent_operation_id": parent})
