"""Shopping initializer handoff to current candidate gate; physical edges are unit-only.

Reuse the accepted native-produced Shopping fixture and original close. Shared
full first-dispatch and failure/cleanup semantics retain exact neutral receipts.
"""

from contextlib import ExitStack
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    RecordedTaskInitialization,
)
from lab_generate_skill.adapters.sites.task_initialization_inputs import (
    TaskInitializationInputs,
)
from lab_generate_skill.adapters.sites.task_initialized_inputs import (
    initialized_candidate_inputs,
)
from lab_generate_skill.bootstrap.shopping_category_task_initialization import (
    shopping_category_task_initialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict
import shopping_category_initialization_port_fixtures as fixtures
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "capture-denied",
        "initial-write",
        "cancel-after-capture",
        "comparison-denied",
        "final-admission-denied",
    ],
)
def test_category_task_inputs_preserve_original_gate_and_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    instances: list[RecordedTaskInitialization] = []
    with ExitStack() as scopes:

        def factory(*args: Any, **kwargs: Any) -> RecordedTaskInitialization:
            held = TaskInitializationInputs(args[0])
            scopes.enter_context(held.scope())
            initial = shopping_category_task_initialization(
                *args, **kwargs, inputs=held
            )
            instances.append(initial)
            return initial

        monkeypatch.setattr(fixtures, "shopping_category_task_initialization", factory)
        facts = fixtures.initialization_case(
            tmp_path, node_path, monkeypatch, originals[0], fault
        )
        assert facts["closed"] and facts["source_attempt"] != facts["candidate_attempt"]
        assert len(instances) == 1
        initial = instances[0]
        held = initial.inputs
        assert held is not None and held.active
        if fault == "none":
            result = facts["result"]
            assert held.initial is not None and held.equivalence is not None
            candidate = initialized_candidate_inputs(
                initial,
                result.equivalence_ref,
                initial.plan.skill_ref,
                initial.plan.operation,
                guard(),
            )
            assert candidate.baseline == initial.state.baseline
            assert candidate.observation.record == held.initial.observation.record
            assert candidate.skill == result.actor.skill
            assert facts["capture_calls"] == 1
            with pytest.raises(OwnershipConflict):
                initialized_candidate_inputs(
                    initial,
                    result.equivalence_ref.model_copy(update={"producer": "foreign"}),
                    initial.plan.skill_ref,
                    initial.plan.operation,
                    guard(),
                )
        else:
            assert facts["primary"] in (
                "PermissionError",
                "OperationStopped",
                "OSError",
            )
            assert initial.state.phase == "quarantined"
    assert held is not None and not held.active
    assert held.source is None and held.initial is None and held.equivalence is None
    with pytest.raises(OwnershipConflict):
        held.check(initial.plan.operation, guard())
