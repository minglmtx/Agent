"""Independent-process reopen and contention with actual files, unit engine."""

import multiprocessing
import os
from pathlib import Path
import time
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorOutput,
    LocalGeneratorParameters,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from local_generator_fixtures import UnitEngine, case
from lab_generate_skill.domain.lifecycle import OperationContext


class CountingEngine(UnitEngine):
    def __init__(self, root: Path, crash: bool = False) -> None:
        super().__init__()
        self.root, self.crash = root, crash

    def generate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> LocalGeneratorOutput:
        with (self.root / "engine-calls").open("a") as stream:
            stream.write("called\n")
            stream.flush()
            os.fsync(stream.fileno())
        if self.crash:
            os._exit(23)
        time.sleep(0.1)
        return super().generate(request, parameters, control)


def generate_child(
    root: Path, operation: str, result: Path, crash: bool = False
) -> None:
    c = case(root)
    c.operation = OperationContext.model_validate_json(operation)
    c.engine = CountingEngine(c.root.parent, crash)
    ref = c.adapter().generate(c.request, c.operation)
    result.write_text(ref.model_dump_json())


def reconcile_child(
    root: Path, operation: str, fact: EvidenceRef, result: Path
) -> None:
    c = case(root)
    c.operation = OperationContext.model_validate_json(operation)
    c.authority.denied = ""
    c.engine = CountingEngine(c.root.parent)
    result.write_text(
        c.adapter().reconcile(c.request, fact, c.cleanup).model_dump_json()
    )


def test_two_processes_invoke_once_then_reuse_saved_result(tmp_path: Path) -> None:
    c = case(tmp_path)
    ctx = multiprocessing.get_context("spawn")
    children = [
        ctx.Process(
            target=generate_child,
            args=(tmp_path, c.operation.model_dump_json(), tmp_path / f"result-{i}"),
        )
        for i in range(2)
    ]
    for child in children:
        child.start()
    try:
        for child in children:
            child.join(20)
            assert child.exitcode == 0
    finally:
        for child in children:
            if child.is_alive():
                child.kill()
            child.join(5)
    assert (tmp_path / "engine-calls").read_text() == "called\n"
    assert (tmp_path / "result-0").read_bytes() == (tmp_path / "result-1").read_bytes()
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is not None


def test_dead_writer_pending_intent_blocks_new_process_generation(
    tmp_path: Path,
) -> None:
    c = case(tmp_path)
    child = multiprocessing.get_context("spawn").Process(
        target=generate_child,
        args=(tmp_path, c.operation.model_dump_json(), tmp_path / "absent", True),
    )
    child.start()
    try:
        child.join(20)
        assert child.exitcode == 23
    finally:
        if child.is_alive():
            child.kill()
        child.join(5)
    assert not (tmp_path / "absent").exists()
    with pytest.raises(DispatchAlreadyCommitted):
        c.adapter().generate(c.request, c.operation)
    assert c.engine.calls == 0
    assert c.adapter().inspect(c.request, c.cleanup).fact_ref is None
    assert (tmp_path / "engine-calls").read_text() == "called\n"


def test_new_process_can_only_reconcile_known_original_fact(tmp_path: Path) -> None:
    c = case(tmp_path)
    c.authority.denied = "completion"
    with pytest.raises(OwnershipConflict) as caught:
        c.adapter().generate(c.request, c.operation)
    fact = getattr(caught.value, "generator_execution").fact_ref
    result = tmp_path / "reconciled"
    child = multiprocessing.get_context("spawn").Process(
        target=reconcile_child,
        args=(tmp_path, c.operation.model_dump_json(), fact, result),
    )
    child.start()
    try:
        child.join(20)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.kill()
        child.join(5)
    assert not (tmp_path / "engine-calls").exists()
    response = c.adapter().inspect(c.request, c.cleanup).response_ref
    assert response is not None and result.read_text() == response.model_dump_json()
