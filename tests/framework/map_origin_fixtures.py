"""Full synthetic historical CAS graph; permission/physical facts are unit premises."""

from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from map_task_execution_current_fixtures import CurrentMapExecutionCase
from lab_generate_skill.application.construction_task_phase_source import (
    ConstructionTaskOriginSource,
)
from test_slurm_commands import guard


def source_origin(
    case: CurrentMapExecutionCase,
) -> tuple[SiteResourceSpec, OriginalMapOriginAuthority]:
    c, j = case.p.original.resource, case.journals
    public = PublicConstructionContext.model_validate_json(
        c.evidence.read(j.source.public_context_ref, guard())
    )
    origin = MapOriginPolicy(
        mode="frozen_context",
        source_context_receipt_ref=j.source_ref,
        source_context_ref=j.source.public_context_ref,
        source_start_url=public.task.start_url,
    )
    data = c.spec.model_dump()
    data["configuration"]["map_inputs"]["origin"] = origin.model_dump()
    spec = SiteResourceSpec.model_validate(data)
    contexts = EvidenceContextRecords(c.evidence, c.controls, j.context)
    return spec, OriginalMapOriginAuthority(
        contexts=contexts,
        evidence=c.evidence,
        source=ConstructionTaskOriginSource(j.construction),
        read_operation=case.p.plan.read_operation,
    )
