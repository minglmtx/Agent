"""Full task-backed Teacher source over original journals; no provider send."""

from pathlib import Path
import pytest
from lab_generate_skill.application.teacher_source import publish_teacher_source
from lab_generate_skill.application.teacher_source_review import (
    TeacherSourceReviewDeps,
    review_teacher_source,
)
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from task_teacher_source_fixtures import complete_task_source_case


def test_four_current_task_results_to_complete_teacher_source_and_independent_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = complete_task_source_case(tmp_path / "case", monkeypatch)
    controls = c.tasks[0].task.deps.controls
    operation = c.bindings.operation
    calls = c.native.loader.session.calls
    assert calls == 4 and all(
        t.task.deps.runs is c.tasks[0].task.deps.runs for t in c.tasks
    )
    source = publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(operation)
    )
    assert source == publish_teacher_source(
        c.progress, c.bindings, c.deps(), control=controls.bind(operation)
    )
    reviewed = review_teacher_source(
        source,
        TeacherSourceReviewDeps(
            c.data.store,
            EvidenceObservations(c.data.store, controls),
            EvidenceRetrievalRecords(
                c.data.store, controls, c.data.retrieval_authority
            ),
            c.authority(operation),
            operation,
        ),
        control=controls.bind(operation),
    )
    assert reviewed.bindings == c.bindings
    assert c.native.loader.session.calls == calls
    assert len(c.parts) == len(c.progress.project().attempts) == 4
    c.native.client.close(controls.bind(operation))
