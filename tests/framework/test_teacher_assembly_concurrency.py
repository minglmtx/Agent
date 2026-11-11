"""Two preparations share original journal/CAS, never a second original call."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import pytest
from lab_generate_skill.application.teacher_assembly import (
    assemble_teacher_revision,
    TeacherAssemblyUnconfirmed,
)
from lab_generate_skill.domain.construction import ProgressEvent, CallPlanned
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.teacher_assembly import PublishedTeacherRevisionAssembly
from teacher_assembly_fixtures import assembly_case
from test_teacher_assembly import paid_files


def test_concurrent_same_original_assembly_registers_one_call_without_reserve_or_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = assembly_case(tmp_path / "case")
    op = c.source.operation
    barrier = Barrier(2, timeout=15)
    original_append = c.deps.journal.append

    def append_together(
        event: ProgressEvent, expected_revision: int, operation: OperationContext
    ) -> ConstructionProgress:
        barrier.wait()
        return original_append(event, expected_revision, operation)

    monkeypatch.setattr(c.deps.journal, "append", append_together)
    before = c.deps.journal.read(op)
    paid = paid_files(c)

    def invoke() -> PublishedTeacherRevisionAssembly | TeacherAssemblyUnconfirmed:
        try:
            return assemble_teacher_revision(
                c.original, c.deps, control=c.source.controls.bind(op)
            )
        except TeacherAssemblyUnconfirmed as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: invoke(), range(2)))
    successes = [r for r in results if isinstance(r, PublishedTeacherRevisionAssembly)]
    failures = [r for r in results if isinstance(r, TeacherAssemblyUnconfirmed)]
    assert successes and all(r == successes[0] for r in successes)
    # A losing writer may observe only the original registration, never a new identity.
    for error in failures:
        assert error.phase == "register_original_call" and error.event is not None
        assert error.event.call == successes[0].bound.plan.call
    current = c.deps.journal.read(op)
    assert current.events == (
        *before.events,
        CallPlanned(operation=op, call=successes[0].bound.plan.call),
    )
    assert len(current.events) == len(before.events) + 1
    assert current.project().pending_call == successes[0].bound.plan.call
    assert current.revision == before.revision + 1
    assert paid_files(c) == paid and not c.transport.calls
