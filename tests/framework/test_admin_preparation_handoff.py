"""Actual preparation producer/consumer reads; native/service grants are explicit doubles."""

from pathlib import Path
from typing import Any
import collections
import json
import os
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation_record import (
    PreparationInputs,
    PreparationRecordFailure,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from admin_navigation_preparation_fixtures import fixture
from test_admin_navigation_input import contracts as contracts


def test_actual_admin_preparation_reuses_bodies_and_each_call_rechecks_authority(
    tmp_path: Path, contracts: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = fixture(tmp_path, contracts)
    bounded = c.adapter.controls.bind(c.request.operation)
    current = NavigationPreparationChecks(c.store)

    class LegacyChecks:
        def check(
            self, inputs: PreparationInputs, control: OperationControl
        ) -> StateChecks:
            return current.check(inputs, control)

    refs: list[EvidenceRef] = []
    read = c.store.read

    def observe(
        reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        refs.append(reference)
        return read(reference, control=control)

    monkeypatch.setattr(c.store, "read", observe)
    c.adapter.checks = LegacyChecks()
    before = c.adapter._verify(c.selection, c.request.operation, bounded)
    old = collections.Counter(refs)
    refs.clear()
    c.adapter.checks = current
    after = c.adapter._verify(c.selection, c.request.operation, bounded)
    new = collections.Counter(refs)
    assert before == after and c.authority.calls == 2
    assert c.request.snapshot_ref is not None
    private = after[0].binding.private_spec_ref
    assert old[private] == old[c.request.snapshot_ref] == 2
    assert new[private] == new[c.request.snapshot_ref] == 1
    assert sum(old.values()) - sum(new.values()) == 2
    refs.clear()
    c.adapter._verify(c.selection, c.request.operation, bounded)
    assert collections.Counter(refs) == new and c.authority.calls == 3
    c.authority.denied = True
    with pytest.raises(PermissionError):
        c.adapter._verify(c.selection, c.request.operation, bounded)
    if output := os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
        (Path(output) / "admin-preparation-read-counts.json").write_text(
            json.dumps(
                {
                    "fixture_only": True,
                    "original_reads": sum(old.values()),
                    "current_reads": sum(new.values()),
                    "private_reads": [old[private], new[private]],
                    "snapshot_reads": [
                        old[c.request.snapshot_ref],
                        new[c.request.snapshot_ref],
                    ],
                    "authority_fresh_each_call": True,
                    "whole_task_speedup_claim": False,
                },
                indent=2,
            )
            + "\n"
        )


@pytest.mark.parametrize(
    "fault", ["private", "snapshot", "empty", "wrong_type", "missing", "cancel"]
)
def test_admin_preparation_handoff_keeps_complete_bytes_and_original_fallback(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    c = fixture(tmp_path, contracts)
    control = c.adapter.controls.bind(c.request.operation)
    loaded = c.adapter.reader.load_with_bodies(
        c.selection, c.request.operation, control
    )
    private: Any = loaded.private_spec
    snapshot: Any = loaded.snapshot
    assert private is not None and snapshot is not None
    expected: type[Exception] = EvidenceIntegrityError
    if fault == "private":
        private += b" "
    elif fault == "snapshot":
        snapshot += b" "
    elif fault == "empty":
        private = b""
    elif fault == "wrong_type":
        snapshot = snapshot.decode()
    elif fault == "missing":
        checks = NavigationPreparationChecks(c.store)
        assert checks.check_with_bodies(
            loaded.inputs, None, None, control
        ) == checks.check(loaded.inputs, control)
        return
    else:

        class Cancelled:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", c.request.operation.operation_id)

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        control = Cancelled()
        expected = OperationStopped
    with pytest.raises(expected):
        NavigationPreparationChecks(c.store).check_with_bodies(
            loaded.inputs, private, snapshot, control
        )
