"""Read-only gate: failures, ABA/history changes and original control propagation."""

from pathlib import Path
from unittest.mock import Mock
import pytest
from lab_generate_skill.application.storage_launch import StorageLaunchGate
from lab_generate_skill.domain.errors import OwnershipConflict, RevisionConflict
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.domain.release_activation import ReleaseSwitch
from lab_generate_skill.ports.release_current import ReleaseCurrentReader
from storage_launch_fixtures import selection
from storage_scope_fixtures import operation
from release_current_fixtures import store, op
from cgroup_fixtures import Control
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.adapters.releases.current import FileReleaseCurrent


def test_gate_only_reads_original_selection_twice() -> None:
    launch, snapshot = selection()
    reader = Mock(spec=ReleaseCurrentReader)
    reader.read.return_value = snapshot
    gate = StorageLaunchGate(launch, reader)
    operation_ = operation(launch.scope)
    control = Control()
    before = gate.observe(operation_, control)
    assert before == snapshot
    gate.confirm(before, operation_, control)
    assert reader.read.call_count == 2 and len(reader.mock_calls) == 2
    assert all(
        c.args == (operation_,) and c.kwargs == {"control": control}
        for c in reader.read.call_args_list
    )


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "deployment",
        "revision",
        "activation",
        "acceptance",
        "malformed",
        "read_error",
    ],
)
def test_bad_publication_rejected(case: str) -> None:
    launch, snapshot = selection()
    reader = Mock(spec=ReleaseCurrentReader)
    wrong = snapshot
    if case == "empty":
        wrong = snapshot.model_copy(update={"switches": ()})
    elif case == "deployment":
        wrong = snapshot.model_copy(
            update={
                "deployment": snapshot.deployment.model_copy(
                    update={"deployment_id": "other"}
                )
            }
        )
    elif case == "revision":
        wrong = snapshot.model_copy(
            update={
                "switches": snapshot.switches
                + (
                    ReleaseSwitch(
                        expected_revision=1,
                        activation=launch.activation,
                        operation=op("new"),
                    ),
                )
            }
        )
    elif case in ("activation", "acceptance"):
        active = (
            launch.activation.model_copy(update={"release_id": "other"})
            if case == "activation"
            else launch.activation.model_copy(
                update={
                    "acceptance_ref": launch.activation.acceptance_ref.model_copy(
                        update={"producer": "other"}
                    )
                }
            )
        )
        wrong = snapshot.model_copy(
            update={
                "switches": (
                    snapshot.switches[0].model_copy(update={"activation": active}),
                )
            }
        )
    reader.read.return_value = {} if case == "malformed" else wrong
    if case == "read_error":
        reader.read.side_effect = OSError("original read failed")
    with pytest.raises((ValueError, RuntimeError, OSError)) as caught:
        StorageLaunchGate(launch, reader).observe(operation(launch.scope), Control())
    assert len(reader.mock_calls) == 1
    assert getattr(caught.value, "storage_publication_observed") == (
        None if case in ("malformed", "read_error") else wrong
    )


@pytest.mark.parametrize("case", ["aba", "birth", "switch_operation"])
def test_confirm_rejects_changed_full_history(case: str) -> None:
    launch, snapshot = selection()
    reader = Mock(spec=ReleaseCurrentReader)
    reader.read.return_value = snapshot
    gate = StorageLaunchGate(launch, reader)
    operation_ = operation(launch.scope)
    before = gate.observe(operation_, Control())
    if case == "aba":
        changed = snapshot.model_copy(
            update={
                "switches": snapshot.switches
                + (
                    ReleaseSwitch(
                        expected_revision=1,
                        activation=launch.activation,
                        operation=op("again"),
                    ),
                )
            }
        )
    elif case == "birth":
        changed = snapshot.model_copy(update={"initialized_by": op("other-birth")})
    else:
        changed = snapshot.model_copy(
            update={
                "switches": (
                    snapshot.switches[0].model_copy(
                        update={"operation": op("other-publisher")}
                    ),
                )
            }
        )
    reader.read.return_value = changed
    with pytest.raises(RevisionConflict) as caught:
        gate.confirm(before, operation_, Control())
    assert getattr(caught.value, "storage_publication_observed") == changed


@pytest.mark.parametrize("case", ["wrong_owner", "stopped"])
def test_denied_before_read(case: str) -> None:
    launch, _ = selection()
    reader = Mock(spec=ReleaseCurrentReader)
    operation_ = operation(launch.scope)
    control = Mock(spec=Control)
    if case == "wrong_owner":
        operation_ = operation_.model_copy(update={"owner_id": "other"})
    else:
        control.checkpoint.side_effect = TimeoutError("cancelled")
    with pytest.raises((OwnershipConflict, TimeoutError)):
        StorageLaunchGate(launch, reader).observe(operation_, control)
    assert not reader.mock_calls


def test_actual_current_read_missing_corrupt_and_exact(tmp_path: Path) -> None:
    launch, snapshot = selection()
    current = store(tmp_path)
    gate = StorageLaunchGate(launch, LocalCurrentFixture(current))
    operation_ = operation(launch.scope)
    with pytest.raises((OSError, RuntimeError)):
        gate.observe(operation_, Control())
    assert not (tmp_path / "system-current.json").exists()
    current.initialize(snapshot.initialized_by)
    current.activate(snapshot.switches[0])
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert gate.observe(operation_, Control()) == snapshot
    assert all(p.read_bytes() == data for p, data in before.items())
    path = tmp_path / "system-current.json"
    path.write_bytes(b"{broken")
    with pytest.raises(RuntimeError):
        gate.observe(operation_, Control())
    assert path.read_bytes() == b"{broken"


def test_cancel_after_read_retains_actual_snapshot() -> None:
    launch, snapshot = selection()
    reader = Mock(spec=ReleaseCurrentReader)
    reader.read.return_value = snapshot
    control = Mock(spec=Control)
    primary = TimeoutError("stopped after completed read")
    control.checkpoint.side_effect = [10.0, primary]
    with pytest.raises(TimeoutError) as caught:
        StorageLaunchGate(launch, reader).observe(operation(launch.scope), control)
    assert caught.value is primary
    assert getattr(caught.value, "storage_publication_observed") == snapshot


class LocalCurrentFixture:
    """Only for this gate unit test; installed integration uses the fixed worker."""

    def __init__(self, current: FileReleaseCurrent) -> None:
        self.current = current

    def read(
        self, operation: OperationContext, *, control: OperationControl
    ) -> ReleaseCurrentSnapshot:
        control.checkpoint()
        result = self.current.read(operation)
        control.checkpoint()
        return result
