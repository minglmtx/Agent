"""No store initialization before publication/claim handshake; failure revokes."""

from typing import Any
from unittest.mock import Mock
import pytest
from lab_generate_skill.bootstrap import storage_scope as module
from lab_generate_skill.bootstrap import evidence_store as assembly
from lab_generate_skill.adapters.storage import scope_admission as admissions
from lab_generate_skill.adapters.storage.scope_admission import (
    PinnedSlurmStorageAdmission,
)
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.claims import SourceClaimRecord
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.release_current import ReleaseCurrentReader
from lab_generate_skill.ports.claims import SourceClaimReader
from lab_generate_skill.runtime.lifecycle import OperationGuards
from storage_launch_fixtures import selection
from storage_scope_fixtures import scope, observation, operation
from test_run_journal import CancelSwitch
from cgroup_fixtures import Control


def setup(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, Any, Any, Any, Any]:
    launch, snapshot = selection(scope(source=True))
    monkeypatch.setattr(
        admissions, "current_process_identity", lambda: launch.scope.writer
    )
    monkeypatch.setattr(
        assembly, "current_process_identity", lambda: launch.scope.writer
    )
    observed = Mock(return_value=observation(launch.scope))
    monkeypatch.setattr(admissions, "observe_current_cgroup", observed)
    reader = Mock(spec=ReleaseCurrentReader)
    reader.read.return_value = snapshot
    claims = Mock(spec=SourceClaimReader)
    assert launch.scope.claim is not None
    claims.read.return_value = SourceClaimRecord(
        binding=launch.scope.claim, operation=operation(launch.scope, "claim")
    )
    created: list[PinnedSlurmStorageAdmission] = []

    class RecordingAdmission(PinnedSlurmStorageAdmission):
        def __init__(self, bound: Any) -> None:
            super().__init__(bound)
            created.append(self)

    monkeypatch.setattr(module, "PinnedSlurmStorageAdmission", RecordingAdmission)
    return launch, snapshot, reader, claims, observed, created


def assemble(
    launch: Any, reader: Any, claims: Any, **kwargs: Any
) -> module.ScopedEvidenceStore:
    clock = SystemClock()
    return module.assemble_slurm_evidence_store(
        launch,
        reader,
        claims,
        operation(launch.scope),
        clock,
        OperationGuards(clock, CancelSwitch()),
        Control(),
        max_io_seconds=60,
        cleanup_seconds=kwargs.get("cleanup_seconds", 60),
    )


def test_success_keeps_frozen_selection_without_initializing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch, snapshot, reader, claims, observed, created = setup(monkeypatch)
    assembled = assemble(launch, reader, claims)
    assert assembled.publication == snapshot and assembled.launch == launch
    assert assembled.store.state == "new"
    assert assembled.admission is created[0]
    assert reader.read.call_count == 2 and claims.read.call_count == 1
    assert observed.call_count == 2


@pytest.mark.parametrize(
    "phase", ["first_read", "claim_read", "confirm_read", "changed_current"]
)
def test_failed_handshake_revokes_and_preserves_primary(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    launch, snapshot, reader, claims, observed, created = setup(monkeypatch)
    primary = OSError("publication or claim failure")
    if phase == "first_read":
        reader.read.side_effect = primary
    elif phase == "claim_read":
        claims.read.side_effect = primary
    elif phase == "confirm_read":
        reader.read.side_effect = [snapshot, primary]
    else:
        reader.read.side_effect = [
            snapshot,
            snapshot.model_copy(update={"switches": ()}),
        ]
    with pytest.raises((OSError, RuntimeError)) as caught:
        assemble(launch, reader, claims)
    if phase != "changed_current":
        assert caught.value is primary
    assert getattr(caught.value, "storage_publication") == (
        None if phase == "first_read" else snapshot
    )
    if phase == "changed_current":
        assert getattr(
            caught.value, "storage_publication_observed"
        ) == snapshot.model_copy(update={"switches": ()})
    elif phase in ("first_read", "confirm_read"):
        assert getattr(caught.value, "storage_publication_observed") is None
    with pytest.raises(InvalidTransition):
        created[0].authorize_storage(
            launch.scope.binding,
            launch.scope.config,
            operation(launch.scope, "new"),
            Control(),
        )
    with pytest.raises(InvalidTransition):
        created[0].activate(claims, operation(launch.scope), Control())


@pytest.mark.parametrize("duration", [0, -1, True, float("inf"), None])
def test_invalid_assembly_parameters_before_publication_or_claim_reads(
    monkeypatch: pytest.MonkeyPatch, duration: Any
) -> None:
    launch, snapshot, reader, claims, observed, created = setup(monkeypatch)
    with pytest.raises((ValueError, TypeError)):
        assemble(launch, reader, claims, cleanup_seconds=duration)
    assert not reader.mock_calls and not claims.mock_calls and not observed.mock_calls
