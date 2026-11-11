"""Same-proof body handoff, exact bytes and fresh checks; synthetic authority."""

from collections import Counter
import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    ClosedSourceBindingBodies,
)
from lab_generate_skill.adapters.plans.preparation_evidence import (
    PreparationEvidenceReader,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.task_publication import TaskBindingInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from preparation_record_fixtures import fixture
from task_binding_fixtures import fixture as binding_fixture


def bodies(c: Any) -> ClosedSourceBindingBodies:
    return ClosedSourceBindingBodies(
        binding=c.binding,
        public_task_json=c.store.read(c.binding.public_task_ref).decode(),
        private_spec_json=c.store.read(c.binding.private_spec_ref).decode(),
        baseline_json=c.store.read(c.binding.baseline_ref).decode(),
    )


def test_exact_noncanonical_public_bytes_are_preserved(tmp_path: Path) -> None:
    c = binding_fixture(tmp_path)
    prior = bodies(c)
    raw = json.dumps(json.loads(prior.public_task_json), indent=2).encode()
    ref = c.put(raw, "public-task/1", "public")
    values = prior.model_dump()
    values.update(
        binding=c.binding.model_copy(update={"public_task_ref": ref}),
        public_task_json=raw.decode(),
    )
    result = ClosedSourceBindingBodies.model_validate(values)
    assert result.public_task_json.encode() == raw
    assert result.inputs().public_task == prior.inputs().public_task
    assert result.inputs().private_spec == prior.inputs().private_spec
    assert result.inputs().baseline == prior.inputs().baseline


@pytest.mark.parametrize(
    "field", ("public_task_json", "private_spec_json", "baseline_json")
)
@pytest.mark.parametrize("damage", ("bytes", "empty", "missing", "wrong_type"))
def test_body_integrity_empty_missing_and_wrong_types_refuse(
    tmp_path: Path, field: str, damage: str
) -> None:
    c = binding_fixture(tmp_path)
    values = bodies(c).model_dump()
    if damage == "bytes":
        values[field] += " "
    elif damage == "empty":
        values[field] = ""
    elif damage == "missing":
        del values[field]
    else:
        values[field] = []
    with pytest.raises((EvidenceIntegrityError, ValidationError)):
        ClosedSourceBindingBodies.model_validate(values)


def delegated(c: Any, *, body_capability: bool) -> tuple[Any, list[str]]:
    original: EvidenceTaskBindings = c.adapter.reader.bindings
    assert isinstance(original, EvidenceTaskBindings)
    calls: list[str] = []

    class Legacy:
        def load_binding(
            self,
            reference: EvidenceRef,
            op: OperationContext,
            control: OperationControl,
        ) -> TaskBinding:
            calls.append("binding")
            return original.load(reference, op)

    class Current(Legacy):
        def load_binding_inputs(
            self,
            reference: EvidenceRef,
            op: OperationContext,
            control: OperationControl,
        ) -> TaskBindingInputs:
            calls.append("bodies")
            # Explicit synthetic fixed-worker boundary. The original binding
            # reader/authority still executes on every call, without caching.
            return original.load_inputs(reference, op)

    checks = Current() if body_capability else Legacy()
    selected = EvidenceTaskBindings(
        c.store, c.adapter.controls, original.authority, load_checks=checks
    )
    return PreparationEvidenceReader(c.store, selected), calls


def test_actual_preparation_consumer_reuses_delegated_bodies_and_records_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = fixture(tmp_path)
    old, old_calls = delegated(c, body_capability=False)
    current, calls = delegated(c, body_capability=True)
    read = c.store.read
    counts: Counter[EvidenceRef] = Counter()

    def counted(reference: EvidenceRef, control: Any = None) -> bytes:
        counts[reference] += 1
        return read(reference, control)

    monkeypatch.setattr(c.store, "read", counted)
    control = c.adapter.controls.bind(c.request.operation)
    previous = old.load(c.selection, c.request.operation, control)
    before = dict(counts)
    counts.clear()
    result = current.load(c.selection, c.request.operation, control)
    assert result == previous
    after = dict(counts)
    assert sum(after.values()) <= sum(before.values()) - 3
    for ref in (
        result.binding.public_task_ref,
        result.binding.private_spec_ref,
        result.binding.baseline_ref,
    ):
        assert after[ref] == 1
    counts.clear()
    assert current.load(c.selection, c.request.operation, control) == result
    assert dict(counts) == after
    assert old_calls == ["binding"] and calls == ["bodies", "bodies"]
    c.authority.denied = True
    with pytest.raises(PermissionError):
        current.load(c.selection, c.request.operation, control)
    assert calls == ["bodies", "bodies", "bodies"]
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "supervised-body-parent-read-counts.json"
    ).write_text(
        json.dumps(
            {
                "legacy_reads": sum(before.values()),
                "current_reads": sum(after.values()),
                "same_facts": True,
                "fresh_proofs": 3,
                "scope": "software fixture with explicit synthetic worker boundary; not production speedup",
                "permission_cached": False,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("damage", ("missing", "corrupt"))
def test_later_delegated_load_reads_original_storage_again(
    tmp_path: Path, damage: str
) -> None:
    c = fixture(tmp_path)
    reader, calls = delegated(c, body_capability=True)
    control = c.adapter.controls.bind(c.request.operation)
    result = reader.load(c.selection, c.request.operation, control)
    path = tmp_path / "evidence/blobs" / result.binding.private_spec_ref.sha256
    expected: type[Exception]
    if damage == "missing":
        path.unlink()
        expected = EvidenceNotFound
    else:
        path.write_bytes(b"corrupt")
        expected = EvidenceIntegrityError
    with pytest.raises(expected):
        reader.load(c.selection, c.request.operation, control)
    assert calls == ["bodies", "bodies"]


def test_delegated_output_stop_and_wrong_type_are_not_usable_inputs(
    tmp_path: Path,
) -> None:
    c = binding_fixture(tmp_path)
    facts = bodies(c).inputs()
    calls: list[str] = []

    class Checks:
        mode = "wrong"

        def load_binding(
            self,
            reference: EvidenceRef,
            op: OperationContext,
            control: OperationControl,
        ) -> TaskBinding:
            raise AssertionError("Body-capable reader must not invoke another proof")

        def load_binding_inputs(
            self,
            reference: EvidenceRef,
            op: OperationContext,
            control: OperationControl,
        ) -> Any:
            calls.append(self.mode)
            if self.mode == "stop":
                c.controls.control.stopped = True
                return facts
            return None

    checks = Checks()
    selected = EvidenceTaskBindings(
        c.store, c.controls, c.authority, load_checks=checks
    )
    from test_run_journal import command

    ref = c.records.publish(c.binding, command())
    with pytest.raises(TypeError, match="typed bodies"):
        selected.load_inputs(ref, command())
    checks.mode = "stop"
    with pytest.raises(OperationStopped):
        selected.load_inputs(ref, command())
    assert calls == ["wrong", "stop"]
