"""Publish original single-task source from frozen RunPlan/owned claim, no dispatch.

The caller must supply real source/context/task/claim authority ports. The fixed
reader revalidates those permissions before and after append-only publication.
There is no fallback to legacy engineering claim JSON, new IDs or fake plans.
"""

from dataclasses import dataclass
from lab_generate_skill.adapters.plans.execution_task_source import (
    OriginalExecutionTaskSource,
)
from lab_generate_skill.application.context_evidence import publish_raw
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.execution_task_source import (
    ExecutionTaskSource,
    ExecutionSourceFacts,
)
from lab_generate_skill.domain.frozen_execution_origin import FrozenExecutionOrigin
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import RevisionConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls


@dataclass(frozen=True)
class PublishedExecutionTaskSource:
    source: ExecutionTaskSource
    source_ref: EvidenceRef


class ExecutionSourcePublicationUnconfirmed(RuntimeError):
    def __init__(
        self,
        source: ExecutionTaskSource,
        candidates: tuple[EvidenceRef, ...],
        primary: BaseException,
    ) -> None:
        self.source, self.candidates, self.primary = source, candidates, primary
        super().__init__(
            "Original source publication unconfirmed; inspect retained references/claim, never dispatch or create a replacement"
        )


def publish_execution_task_source(
    run: RunBinding,
    claim_ref: EvidenceRef,
    operation: OperationContext,
    *,
    reader: OriginalExecutionTaskSource,
    evidence: EvidenceStore,
    controls: OperationControls,
    frozen_origin: FrozenExecutionOrigin | None = None,
) -> PublishedExecutionTaskSource:
    if any(v is None for v in (reader, evidence, controls)):
        raise ValueError(
            "Original source authority readers/evidence/controls mandatory"
        )
    operation = OperationContext.model_validate(operation)
    control = controls.bind(operation)
    control.checkpoint()

    def bind() -> ExecutionSourceFacts:
        if frozen_origin is None:
            return reader.bind_source(run, claim_ref, operation, control)
        return reader.bind_source(
            run, claim_ref, operation, control, frozen_origin=frozen_origin
        )

    facts = bind()
    retained: list[EvidenceRef] = []
    try:
        raw = facts.source.model_dump_json().encode()
        ref = publish_raw(
            evidence,
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=facts.source.schema_version,
                visibility="private",
                producer="execution-task-source-v1",
            ),
            retained,
            control,
        )
        after = bind()
        if after != facts:
            raise RevisionConflict("Original single source changed during publication")
        control.checkpoint()
        return PublishedExecutionTaskSource(facts.source, ref)
    except BaseException as error:
        raise ExecutionSourcePublicationUnconfirmed(
            facts.source, tuple(retained), error
        ) from error
