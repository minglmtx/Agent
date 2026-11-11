"""Independent transition sequences, malformed state and exact operation replay."""

from typing import cast
from datetime import timedelta
import lab_generate_skill.domain.release_current as current_contract
import pytest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    RevisionConflict,
    JournalCapacityExceeded,
)
from lab_generate_skill.domain.release_activation import (
    ReleaseDeployment,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import (
    ReleaseCurrentSnapshot,
    switch_release,
)
from release_current_fixtures import op, switch, ref


def empty(limit: int = 3) -> ReleaseCurrentSnapshot:
    return ReleaseCurrentSnapshot(
        deployment=ReleaseDeployment(deployment_id="main", max_switches=limit),
        initialized_by=op(),
    )


def test_empty_activate_upgrade_old_replay_and_explicit_rollback() -> None:
    start = empty()
    assert start.active is None and start.revision == 0
    first, second = switch(), switch(1, "two")
    one = switch_release(start, first)
    two = switch_release(one, second)
    assert two.active == second.activation and two.revision == 2
    assert switch_release(two, first) == two
    rollback = first.model_copy(
        update={"expected_revision": 2, "operation": op("rollback")}
    )
    restored = switch_release(two, rollback)
    assert restored.active == first.activation and restored.revision == 3
    assert restored.switches[:2] == two.switches
    assert (
        ReleaseCurrentSnapshot.model_validate_json(restored.model_dump_json())
        == restored
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_revision", True),
        ("expected_revision", -1),
        ("expected_revision", 1024),
        ("operation", None),
        ("activation", {}),
        ("schema_version", "old/1"),
    ],
)
def test_switch_strict_invalid_inputs(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        ReleaseSwitch.model_validate({**switch().model_dump(), field: value})


@pytest.mark.parametrize("value", [0, -1, 1025, True, "3", None])
def test_capacity_boundaries(value: object) -> None:
    with pytest.raises(ValueError):
        ReleaseDeployment(deployment_id="main", max_switches=cast(int, value))


@pytest.mark.parametrize(
    "mutation", ["skip", "duplicate", "rebind", "cleanup", "wrong_schema", "public"]
)
def test_invalid_histories_and_activation_refs_rejected(mutation: str) -> None:
    state = empty()
    first = switch()
    second = switch(1, "two")
    if mutation == "skip":
        second = second.model_copy(update={"expected_revision": 2})
    elif mutation == "duplicate":
        second = second.model_copy(update={"operation": first.operation})
    elif mutation == "rebind":
        second = second.model_copy(
            update={
                "activation": second.activation.model_copy(
                    update={"release_id": first.activation.release_id}
                )
            }
        )
    elif mutation == "cleanup":
        second = second.model_copy(
            update={
                "operation": second.operation.model_copy(
                    update={"mode": "cleanup", "parent_operation_id": "original"}
                )
            }
        )
    else:
        reference = (
            ref("old/1")
            if mutation == "wrong_schema"
            else second.activation.manifest_ref.model_copy(
                update={"visibility": "public"}
            )
        )
        second = second.model_copy(
            update={
                "activation": second.activation.model_copy(
                    update={"manifest_ref": reference}
                )
            }
        )
    with pytest.raises((ValueError, OwnershipConflict)):
        ReleaseCurrentSnapshot(
            deployment=state.deployment,
            initialized_by=state.initialized_by,
            switches=(first, second),
        )


def test_conflict_capacity_and_operation_rebinding_preserve_prior() -> None:
    first = switch()
    state = switch_release(empty(1), first)
    with pytest.raises(RevisionConflict):
        switch_release(state, switch(0, "two"))
    with pytest.raises(JournalCapacityExceeded):
        switch_release(state, switch(1, "two"))
    with pytest.raises(OwnershipConflict):
        switch_release(state, first.model_copy(update={"expected_revision": 1}))
    with pytest.raises(OwnershipConflict):
        switch_release(
            state,
            switch(1, "two").model_copy(update={"operation": state.initialized_by}),
        )
    assert switch_release(state, first) == state and state.revision == 1


@pytest.mark.parametrize("offset", [0, -1])
def test_byte_capacity_exact_boundary_keeps_public_error(
    monkeypatch: pytest.MonkeyPatch, offset: int
) -> None:
    prior = empty()
    change = switch()
    expected = prior.model_copy(update={"switches": (change,)})
    limit = len(expected.model_dump_json().encode()) + offset
    monkeypatch.setattr(current_contract, "MAX_CURRENT_BYTES", limit)
    if offset == 0:
        assert switch_release(prior, change) == expected
    else:
        with pytest.raises(JournalCapacityExceeded, match="byte limit"):
            switch_release(prior, change)
    assert prior.revision == 0 and prior.active is None


@pytest.mark.parametrize("field", ["deadline", "owner_id", "run_id"])
def test_repeated_operation_cannot_change_context(field: str) -> None:
    first = switch()
    state = switch_release(empty(), first)
    value: object = (
        first.operation.deadline + timedelta(seconds=1)
        if field == "deadline"
        else "another-owner-or-run"
    )
    changed = first.model_copy(
        update={"operation": first.operation.model_copy(update={field: value})}
    )
    with pytest.raises(OwnershipConflict, match="operation changed"):
        switch_release(state, changed)
    assert switch_release(state, first) == state
