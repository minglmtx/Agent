"""Original admission facts reach complete source without unit source allowlist."""

from pathlib import Path
from datetime import datetime, timezone
from typing import cast
import pytest
from lab_generate_skill.application.teacher_source import publish_teacher_source
from lab_generate_skill.application.teacher_source_review import (
    TeacherSourceReviewDeps,
    review_teacher_source,
)
from lab_generate_skill.bootstrap.teacher_source import teacher_source_dependencies
from lab_generate_skill.domain.identity import Site
from teacher_native_source_fixtures import native_source_case
from teacher_source_admission_fixtures import admit_native_source


@pytest.mark.parametrize(
    "site", ["shopping_admin", "shopping", "gitlab", "reddit", "map"]
)
def test_original_run_claim_context_sealed_attempts_to_native_source_and_closed_read(
    tmp_path: Path, site: str
) -> None:
    c = native_source_case(tmp_path / "case", cast(Site, site))
    a = admit_native_source(c)
    # The previous source allowlist is deliberately denied, never consulted by this factory.
    c.authority.denied = True
    before = a.runs.read(c.operation)
    claims = c.data.claim_authority.create_calls
    deps = teacher_source_dependencies(
        c.data.store, c.observations, c.retrieval, a.authority
    )
    source = publish_teacher_source(
        c.progress, c.bindings, deps, control=c.controls.bind(c.operation)
    )
    assert source == c.source
    repeated = publish_teacher_source(
        c.progress, c.bindings, deps, control=c.controls.bind(c.operation)
    )
    assert repeated == source
    # Read after original run closure requires original owner/claim and parent-linked cleanup.
    current = a.runs.read(c.operation)
    for stage in ("closing", "sealed"):
        from lab_generate_skill.domain.execution import RunStage

        event = a.harness.run_entry(current, cast(RunStage, stage))
        current = a.runs.append(event, current.revision, event.event.operation)
    closed = c.operation.cleanup(
        "source-admission-closed-review", now=datetime.now(timezone.utc), seconds=60
    )
    review = TeacherSourceReviewDeps(
        c.data.store, c.observations, c.retrieval, a.recorded(closed), closed
    )
    receipt = review_teacher_source(source, review, control=c.controls.bind(closed))
    assert receipt.source == source.source and current.project()[0].stage == "sealed"
    assert current.entries[: len(before.entries)] == before.entries
    assert c.data.claim_authority.create_calls == claims
    assert c.data.journal().read(closed) == c.progress
