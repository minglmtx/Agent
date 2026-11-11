"""Child deadlines and independent cleanup guards cannot become infinite."""

import pytest
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.domain.errors import OperationStopped


@pytest.mark.parametrize(
    "seconds", [0, -1, True, float("nan"), float("inf"), 86401, "1"]
)
def test_invalid_deadline(seconds: object) -> None:
    with pytest.raises(ValueError):
        DeadlineControl(seconds, "test")  # type: ignore[arg-type]


def test_monotonic_bound_and_bad_wait() -> None:
    control = DeadlineControl(0.03, "bounded")
    assert 0 < control.checkpoint() <= 0.03
    with pytest.raises(ValueError):
        control.wait(float("nan"))
    with pytest.raises(OperationStopped):
        control.wait(0.1)
