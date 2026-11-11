"""Original control and bound deadline both remain authoritative, including wait."""

from typing import Any
from unittest.mock import Mock
import pytest
from lab_generate_skill.adapters.processes.combined_control import CombinedControl
from lab_generate_skill.ports.lifecycle import OperationControl


def test_slow_caller_and_wait_keep_narrowest_original_bound() -> None:
    caller, bound = Mock(spec=OperationControl), Mock(spec=OperationControl)
    caller.checkpoint.return_value = 100
    bound.checkpoint.side_effect = [10, 3, 2, 1]
    control = CombinedControl(caller, bound)
    control.wait(8)
    caller.wait.assert_called_once_with(3)
    assert bound.checkpoint.call_count == 4 and caller.checkpoint.call_count == 2


@pytest.mark.parametrize("which", ["caller", "bound"])
def test_original_stop_preserved(which: str) -> None:
    caller, bound = Mock(spec=OperationControl), Mock(spec=OperationControl)
    caller.checkpoint.return_value = 10
    bound.checkpoint.return_value = 10
    error = TimeoutError("original stop")
    (caller if which == "caller" else bound).checkpoint.side_effect = error
    with pytest.raises(TimeoutError) as caught:
        CombinedControl(caller, bound).checkpoint()
    assert caught.value is error


@pytest.mark.parametrize("value", [0, -1, True, None, "1", float("nan"), float("inf")])
def test_invalid_remaining_refused(value: Any) -> None:
    caller, bound = Mock(spec=OperationControl), Mock(spec=OperationControl)
    caller.checkpoint.return_value = value
    bound.checkpoint.return_value = 10
    with pytest.raises(ValueError):
        CombinedControl(caller, bound).checkpoint()


@pytest.mark.parametrize("value", [-1, True, None, "1", float("nan"), float("inf")])
def test_invalid_wait_no_provider_calls(value: Any) -> None:
    caller, bound = Mock(spec=OperationControl), Mock(spec=OperationControl)
    with pytest.raises(ValueError):
        CombinedControl(caller, bound).wait(value)
    assert not caller.mock_calls and not bound.mock_calls
