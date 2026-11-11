"""Invalid input/expired control before effects and explicit local state rules."""

from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.domain.errors import InvalidTransition, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from managed_store_fixtures import assembled
from test_filesystem_evidence import metadata
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "seconds", [None, False, "60", 0, -1, float("nan"), float("inf"), 86401, 10**500]
)
def test_invalid_cleanup_budget_before_initialization(
    tmp_path: Path, seconds: object
) -> None:
    with pytest.raises((ValueError, TypeError)):
        assembled(
            tmp_path,
            Path("/trusted/python"),
            provision=False,
            cleanup_seconds=cast(float, seconds),
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("data", [None, "", bytearray(), 1, False, [], {}, b"x" * 1025])
def test_bad_payload_before_any_initialization(tmp_path: Path, data: object) -> None:
    store, admission = assembled(tmp_path, Path("/trusted/python"), provision=False)
    with pytest.raises((TypeError, ValueError)):
        store.put(cast(bytes, data), metadata(), guard(60))
    assert store.state == "new" and not admission.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", [None, {}, "text", 1])
def test_bad_metadata_and_reference_before_effects(
    tmp_path: Path, value: object
) -> None:
    store, admission = assembled(tmp_path, Path("/trusted/python"), provision=False)
    with pytest.raises(TypeError):
        store.put(b"", cast(EvidenceMetadata, value), guard(60))
    with pytest.raises(TypeError):
        store.read(cast(EvidenceRef, value), guard(60))
    assert not admission.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ["metadata", "uri", "size", "new"])
def test_invalid_model_fields_and_uninitialized_store(
    tmp_path: Path, fault: str
) -> None:
    store, admission = assembled(tmp_path, Path("/trusted/python"), provision=False)
    ref = evidence_reference(b"x", metadata())
    with pytest.raises(ValueError):
        if fault == "metadata":
            store.put(
                b"x", metadata().model_copy(update={"visibility": "bad"}), guard(60)
            )
        elif fault == "uri":
            store.read(ref.model_copy(update={"uri": "file:///etc/passwd"}), guard(60))
        elif fault == "size":
            store.read(ref.model_copy(update={"size_bytes": 1025}), guard(60))
        else:
            store.read(ref, guard(60))
    assert not admission.calls and not list(tmp_path.iterdir())


def test_expired_initialize_does_not_create_or_change_state(tmp_path: Path) -> None:
    store, admission = assembled(tmp_path, Path("/trusted/python"), provision=False)

    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        store.initialize(Stopped())
    assert store.state == "new" and not admission.calls and not list(tmp_path.iterdir())


def test_same_instance_reentrant_initialization_rejected(tmp_path: Path) -> None:
    store, admission = assembled(tmp_path, Path("/trusted/python"), provision=False)

    class Reentrant:
        def checkpoint(self) -> float:
            with pytest.raises(InvalidTransition, match="in progress"):
                store.initialize(guard(60))
            raise OperationStopped("CANCELLED", "original")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        store.initialize(Reentrant())
    assert store.state == "new" and not admission.calls
