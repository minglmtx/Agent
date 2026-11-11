"""Category producer bodies through the real full-baseline consumer; no live grant."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.baseline_evidence import BaselineEvidenceReader
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.domain.baseline_read import (
    BaselineReadRequest,
    BaselineReadBodies,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from shopping_category_source_fixtures import source_unit_case
from shopping_category_owned_reads import CategoryUnitRead
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals


def test_original_category_publication_hands_complete_inputs_to_baseline_consumer_and_refuses_mismatch(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    source = source_unit_case(tmp_path, node_path, monkeypatch, originals[0], "none")
    published = source.run()
    assert published.inputs.context.task.identity == source.owner.scope.task
    assert published.inputs.baseline.scope == published.receipt.scope
    assert published.inputs.reset.scope == published.receipt.scope
    assert source.owner._sealed
    operation = published.receipt.operation.cleanup(
        "category-whole-baseline-read", now=source.site.clock.utcnow(), seconds=60
    )
    control = source.site.controls.bind(operation)
    transport = CategoryUnitRead(source, tmp_path / "evidence", operation)
    reader = SupervisedClosedSourceContexts(
        published.material, transport, source.site.controls
    )

    class NoLocalReads:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            pytest.fail(
                "Full verified baseline body unexpectedly fell back to leaf reads"
            )

    consumer = BaselineEvidenceReader(NoLocalReads(), input_reads=reader)
    assert (
        consumer.verify(published.inputs.baseline, control, operation=operation)
        == published.inputs.baseline_inputs
    )
    assert transport.calls == 1
    reply = transport.last_reply
    assert reply is not None and reply.baseline_bodies is not None
    verified = reply.baseline_bodies

    class CorruptBodies:
        def load_baseline_inputs(
            self, request: BaselineReadRequest, control: OperationControl
        ) -> BaselineReadBodies:
            assert request == verified.request
            wrong = verified.bodies[0].model_copy(update={"json_text": "{}"})
            return verified.model_copy(update={"bodies": (wrong, *verified.bodies[1:])})

    with pytest.raises(
        ValueError, match="Baseline input body changed complete original bytes"
    ):
        BaselineEvidenceReader(NoLocalReads(), input_reads=CorruptBodies()).verify(
            published.inputs.baseline, control, operation=operation
        )
    task = published.inputs.baseline.scope.task.model_copy(
        update={"task_id": "foreign", "source_task_id": "foreign"}
    )
    scope = published.inputs.baseline.scope.model_copy(update={"task": task})
    foreign = published.inputs.baseline.model_copy(update={"scope": scope})
    request = BaselineReadRequest(receipt=foreign, operation=operation)
    with pytest.raises(
        OwnershipConflict, match="Baseline read changed original source owner/task"
    ):
        reader.load_baseline_inputs(request, control)
    assert transport.calls == 2
