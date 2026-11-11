"""Publication cannot restart onsite work, escape the root, or ignore a stop."""

from datetime import timedelta
from typing import Any

import pytest

from lab_generate_skill.bootstrap.source_publication_window import (
    publication_parent,
    closed_publication_operation,
)
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_lifecycle import ManualClock, CancelSwitch, operation
from test_bounded_lifecycle import case as bounded_case


def test_expired_acquisition_keeps_original_descriptor_but_publication_has_own_budget() -> (
    None
):
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    acquisition = operation(clock)
    original = acquisition.model_dump_json()
    root = acquisition.model_copy(
        update={
            "operation_id": "root",
            "deadline": acquisition.deadline + timedelta(seconds=100),
        }
    )
    assert publication_parent(acquisition, root, controls) == root
    controls.bind(acquisition)
    clock.sleep(11)
    with pytest.raises(OperationStopped):
        controls.bind(acquisition).checkpoint()
    published = closed_publication_operation(root, "publish", 30, controls, clock)
    assert controls.bind(published).checkpoint() == 30
    assert published.cancellation_ref == acquisition.cancellation_ref
    assert published.mode == "execute" and acquisition.model_dump_json() == original
    assert controls.bind(published) is controls.bind(published)
    cancel.cancelled = True
    with pytest.raises(OperationStopped, match="CANCELLED"):
        closed_publication_operation(root, "after-stop", 30, controls, clock)


def test_legacy_parent_still_expires_and_new_root_cannot_escape_global_cutoff() -> None:
    clock, _, controls, root = bounded_case()
    acquisition = root.model_copy(
        update={
            "operation_id": "site",
            "deadline": clock.utcnow() + timedelta(seconds=2),
        }
    )
    assert publication_parent(acquisition, None, controls) == acquisition
    assert publication_parent(acquisition, root, controls) == root
    clock.sleep(3)
    with pytest.raises(OperationStopped):
        closed_publication_operation(acquisition, "legacy-publish", 30, controls, clock)
    pub = closed_publication_operation(root, "publish", 30, controls, clock)
    assert controls.bind(pub).checkpoint() == 7
    clock.sleep(7)
    with pytest.raises(OperationStopped):
        closed_publication_operation(root, "after-root-window", 30, controls, clock)
    cleanup = acquisition.cleanup("original-close", now=clock.utcnow(), seconds=100)
    assert controls.bind(cleanup).checkpoint() == 8


@pytest.mark.parametrize(
    "change",
    [
        {"operation_id": "prepare"},
        {"owner_id": "other", "cancellation_ref": None},
        {"run_id": "other", "cancellation_ref": None},
        {"cancellation_ref": None},
        {"attempt_id": "other"},
        {"allocation_id": "another-instance"},
        {"mode": "cleanup", "parent_operation_id": "before"},
        {"parent_operation_id": "another-root"},
        {"deadline": ManualClock().utcnow()},
    ],
)
def test_changed_root_rejected_before_source_effects(change: dict[str, Any]) -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    controls = OperationGuards(clock, cancel)
    acquisition = operation(clock)
    root = acquisition.model_copy(update={"operation_id": "root", **change})
    with pytest.raises(OwnershipConflict):
        publication_parent(acquisition, root, controls)


@pytest.mark.parametrize("seconds", [None, True, 0, -1, 3601, "30", 1.5])
def test_bad_publication_budget_rejected(seconds: Any) -> None:
    clock, cancel = ManualClock(), CancelSwitch()
    with pytest.raises(ValueError):
        closed_publication_operation(
            operation(clock), "publish", seconds, OperationGuards(clock, cancel), clock
        )
