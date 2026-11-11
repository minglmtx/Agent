"""Owned production preparation to first Actor dispatch and original close.

The retained fixture supplies explicit synthetic process/model/storage edges;
real source, claim, run, preparation, initialization and cleanup adapters remain.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.owned_preparation_records import (
    owned_preparation_records,
)
from lab_generate_skill.adapters.sites.task_preparation_record_inputs import (
    TaskPreparationRecordInputs,
)
from lab_generate_skill.application.execute_task import TaskExecutionUnconfirmed
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.preparation_records import PreparationInputReads
from site_instance_fixtures import node_path as node_path
from task_resource_owner_fixtures import owned_task
from task_actor_input_fixtures import fixed_task_source_inputs


@pytest.mark.parametrize(
    "fault",
    ["none", "selection", "publication", "body", "storage", "cancel", "readback"],
)
def test_owned_preparation_bodies_keep_fresh_gates_and_original_cleanup(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    with owned_task(node_path, monkeypatch, input_handoff=True) as (c, r):
        fixed = fixed_task_source_inputs(c, r, monkeypatch)
        assert r.inputs is not None
        assert isinstance(c.journals.source_reader.contexts, PreparationInputReads)
        c.bundle.preparation.records = owned_preparation_records(
            c.bundle.preparation.records,
            c.journals.source_reader.contexts,
            inputs=r.inputs,
        )
        handoff = r.inputs.preparation_records
        assert isinstance(handoff, TaskPreparationRecordInputs)
        original_checks = handoff.preparation_checks
        check_calls = 0

        def checked(
            inputs: Any, checker: Any, op: Any, control: Any, check: Any
        ) -> Any:
            def physical() -> Any:
                nonlocal check_calls
                check_calls += 1
                return check()

            return original_checks(inputs, checker, op, control, physical)

        monkeypatch.setattr(handoff, "preparation_checks", checked)
        original = handoff.preparation_inputs
        publication = handoff.publication_inputs
        calls = graph_reads = publications = publication_reads = 0
        injected = False
        last: list[Any] = []

        def graph(selection: Any, op: Any, control: Any, read: Any) -> Any:
            nonlocal calls, graph_reads, injected
            calls += 1
            last[:] = [selection, op, control, read]
            if calls == 3 and fault in ("selection", "body", "storage", "cancel"):
                injected = True
                assert handoff.graph is not None
                if fault == "selection":
                    selection = selection.model_copy(
                        update={
                            "request_ref": selection.request_ref.model_copy(
                                update={"producer": "foreign-producer"}
                            )
                        }
                    )
                elif fault == "body":
                    assert handoff.graph.private_spec is not None
                    handoff.graph = replace(handoff.graph, private_spec=b"corrupt")
                elif fault == "storage":
                    fixed.denied = True
                else:
                    raise OperationStopped("CANCELLED", op.operation_id)

            def physical() -> Any:
                nonlocal graph_reads
                graph_reads += 1
                return read()

            return original(selection, op, control, physical)

        def published(selected: Any, op: Any, control: Any, read: Any) -> Any:
            nonlocal publications, publication_reads, injected
            publications += 1
            if publications == 2 and fault == "publication":
                injected = True
                selected = selected.model_copy(
                    update={
                        "prepared_ref": selected.prepared_ref.model_copy(
                            update={"producer": "foreign-producer"}
                        )
                    }
                )

            def physical() -> Any:
                nonlocal publication_reads, injected
                publication_reads += 1
                raw = read()
                if publication_reads == 1 and fault == "readback":
                    injected = True
                    return raw[0] + b" ", raw[1]
                return raw

            return publication(selected, op, control, physical)

        monkeypatch.setattr(handoff, "preparation_inputs", graph)
        monkeypatch.setattr(handoff, "publication_inputs", published)
        if fault == "none":
            result = c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert result.evaluation.status == "success"
            assert calls > 3 and publications > 2
            assert c.bundle.finalization.state.reset is not None
            assert c.bundle.finalization.state.reset.status == "safe"
        else:
            with pytest.raises(TaskExecutionUnconfirmed) as failed:
                c.bundle.task.execute(c.p.plan.intent, c.p.plan.operation)
            assert injected and failed.value.primary is not None
            chain: list[BaseException] = []
            error: BaseException | None = failed.value.primary
            while error is not None and len(chain) < 16:
                chain.append(error)
                error = getattr(error, "primary", None) or error.__cause__
            expected = (
                EvidenceIntegrityError
                if fault in ("body", "readback")
                else OperationStopped if fault == "cancel" else OwnershipConflict
            )
            assert any(isinstance(error, expected) for error in chain), chain
            # Failures keep the original restoring/close path and known facts.
            if fault == "storage":
                assert c.bundle.finalization.state.reset is None
                assert failed.value.cleanup_errors
            else:
                assert c.bundle.finalization.state.reset is not None
        assert graph_reads == 1 and publication_reads == 1
        assert check_calls == 1
        assert fixed.current_calls > calls
        assert not r.inputs.active and r.inputs.preparation_records is None
        assert (
            handoff.graph is None
            and handoff.publication is None
            and handoff.checked is None
        )
        assert r.inputs.prepared_browser is None
        with pytest.raises(OwnershipConflict):
            original(*last)
