"""Same-call immutable inputs avoid duplicate I/O; later calls recheck everything."""

from collections import Counter
from pathlib import Path
import json
import os
from typing import Any

import pytest

from lab_generate_skill.adapters.plans.preparation_evidence import (
    PreparationEvidenceReader,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.ports.task_bindings import TaskBindingInputLoads
from preparation_record_fixtures import fixture
from task_binding_fixtures import fixture as binding_fixture
from test_run_journal import command


def prior_reader(c: Any, control: Any) -> PreparationInputs:
    """Reference of the exact previous reader order, using current semantic ports."""
    reader = c.adapter.reader
    read = reader.reads.parse
    selection, op = c.selection, c.request.operation
    request = read(
        selection.request_ref, "site-task-request/2", SiteTaskRequest, control
    )
    result = read(selection.result_ref, "site-task-result/1", SiteTaskResult, control)
    binding = reader.bindings.load(request.binding_ref, op)
    public = read(
        binding.public_task_ref,
        "public-task/1",
        PublicTask,
        control,
        visibility="public",
    )
    spec = read(binding.baseline_ref, "initial-state-spec/1", InitialStateSpec, control)
    environment = read(
        selection.environment_ref,
        "environment-baseline/1",
        EnvironmentBaseline,
        control,
    )
    assert request.operation.recovery_ref is not None
    recovery = read(
        request.operation.recovery_ref, "recovery-plan/1", RecoveryPlan, control
    )
    inputs = PreparationInputs(
        selection=selection,
        request=request,
        result=result,
        binding=binding,
        public_task=public,
        spec=spec,
        environment=environment,
        recovery=recovery,
    )
    reader.reads.dependencies((inputs,), control)
    return inputs


def test_same_inputs_and_fewer_physical_reads_with_no_cross_call_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = fixture(tmp_path)
    original = c.store.read
    reads: Counter[EvidenceRef] = Counter()

    def counted(reference: EvidenceRef, control: Any = None) -> bytes:
        reads[reference] += 1
        return original(reference, control)

    monkeypatch.setattr(c.store, "read", counted)
    control = c.adapter.controls.bind(c.request.operation)
    prior = prior_reader(c, control)
    old = dict(reads)
    reads.clear()
    current = c.adapter.reader.load(c.selection, c.request.operation, control)
    assert current == prior
    assert sum(reads.values()) < sum(old.values())
    assert current.request.operation.recovery_ref is not None
    for reference in (
        c.selection.request_ref,
        c.selection.result_ref,
        current.request.binding_ref,
        current.binding.public_task_ref,
        current.binding.private_spec_ref,
        current.binding.baseline_ref,
        c.selection.environment_ref,
        current.request.operation.recovery_ref,
    ):
        assert reads[reference] == 1
    new = dict(reads)
    reads.clear()
    assert c.adapter.reader.load(c.selection, c.request.operation, control) == current
    assert dict(reads) == new
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "preparation-read-counts.json"
    ).write_text(
        json.dumps(
            {
                "prior_physical_reads": sum(old.values()),
                "current_physical_reads": sum(new.values()),
                "scope": "Same preparation graph and semantic checks, local software fixture; not a runtime speedup measurement.",
                "cross_call_cache": False,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize("fault", ["missing", "corrupt", "revoked"])
def test_second_call_rechecks_storage_and_permission(
    tmp_path: Path, fault: str
) -> None:
    c = fixture(tmp_path)
    control = c.adapter.controls.bind(c.request.operation)
    first = c.adapter.reader.load(c.selection, c.request.operation, control)
    if fault == "revoked":
        c.authority.denied = True
        expected: Any = PermissionError
    else:
        target = tmp_path / "evidence" / "blobs" / first.binding.private_spec_ref.sha256
        if fault == "missing":
            target.unlink()
            expected = EvidenceNotFound
        else:
            target.write_bytes(b"corrupt")
            expected = EvidenceIntegrityError
    with pytest.raises(expected):
        c.adapter.reader.load(c.selection, c.request.operation, control)


def test_binding_body_output_keeps_original_authority_and_control(
    tmp_path: Path,
) -> None:
    c = binding_fixture(tmp_path)
    ref = c.records.publish(c.binding, command())
    assert isinstance(c.records, TaskBindingInputLoads)
    assert c.records.loads_inputs_in_one_call
    before = len(c.authority.calls)
    facts = c.records.load_inputs(ref, command())
    assert facts.binding == c.binding
    assert facts.public_task.identity == c.binding.identity
    assert facts.private_spec == c.store.read(c.binding.private_spec_ref)
    assert facts.baseline == c.store.read(c.binding.baseline_ref)
    assert len(c.authority.calls) == before + 1
    c.authority.denied = True
    with pytest.raises(OwnershipConflict, match="permission"):
        c.records.load_inputs(ref, command())


def test_supervised_binding_path_keeps_its_existing_loader(tmp_path: Path) -> None:
    from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
    from lab_generate_skill.domain.task import TaskBinding
    from lab_generate_skill.domain.lifecycle import OperationContext
    from lab_generate_skill.ports.lifecycle import OperationControl

    c = fixture(tmp_path)
    bound = c.adapter.reader.bindings
    assert isinstance(bound, EvidenceTaskBindings)
    checked_bindings: EvidenceTaskBindings = bound
    calls = []

    class WholeGraph:
        def load_binding(
            self, ref: EvidenceRef, op: OperationContext, control: OperationControl
        ) -> TaskBinding:
            calls.append(ref)
            result = checked_bindings.reader.load(ref, control)
            checked_bindings._verify(result, op, control)
            return result

    bound.load_checks = WholeGraph()
    assert not bound.loads_inputs_in_one_call
    with pytest.raises(ValueError, match="graph"):
        bound.load_inputs(c.request.binding_ref, c.request.operation)
    assert not calls
    control = c.adapter.controls.bind(c.request.operation)
    result = c.adapter.reader.load(c.selection, c.request.operation, control)
    assert result.request == c.request and calls == [c.request.binding_ref]
