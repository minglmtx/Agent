"""Current Map TaskPreparation on original held resources and existing producers."""

from collections.abc import Callable
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from .deferred_state_records import DeferredPreparationRecords
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.adapters.sites.task_preparation_state import (
    TaskPreparationState,
)
from lab_generate_skill.adapters.sites.task_preparation_evidence import (
    TaskPreparationEvidence,
)
from lab_generate_skill.adapters.sites.task_preparation_authorities import (
    PreparationEnvironmentAuthority,
    PreparationPublicationAuthority,
)
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.task_preparation import TaskPreparationAuthority
from lab_generate_skill.ports.task_bindings import TaskBindings
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from .map_state_qualification import map_state_qualifications
from .map_overlay_records import map_preparation_records
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)


def map_task_preparation(
    plan: TaskExecutionPlan,
    declaration: SiteTaskPreparationPlan,
    spec: SiteResourceSpec,
    site: SiteHandle,
    resources: ResourceJournal,
    evidence: EvidenceStore,
    controls: OperationControls,
    bindings: TaskBindings,
    authority: TaskPreparationAuthority,
    *,
    on_acquired: Callable[[RegisteredSite], None] | None = None,
    state_inputs: MapStateInputsTransport | None = None,
) -> RecordedSiteTaskPreparation:
    plan = TaskExecutionPlan.model_validate(plan)
    declaration = SiteTaskPreparationPlan.model_validate(declaration)
    spec = SiteResourceSpec.model_validate(spec)
    if authority is None or bindings is None:
        raise ValueError("Original source and preparation authorities are mandatory")
    inputs = spec.configuration.map_inputs
    if (
        spec.configuration.site_id != "map"
        or inputs is None
        or inputs.scope != declaration.scope
        or declaration.snapshot_schema
        != MapTaskStateCodec(declaration.scope.task).snapshot_schema
    ):
        raise ValueError(
            "Original configured Map attempt and native snapshot codec required"
        )
    state = TaskPreparationState()
    io = TaskPreparationEvidence(evidence, state)
    qualifications = map_state_qualifications(
        evidence,
        controls,
        PreparationEnvironmentAuthority(plan, declaration, state, io, authority),
        spec,
        lambda: site.site,
        state_inputs=state_inputs,
    )
    records = DeferredPreparationRecords(
        lambda: map_preparation_records(
            evidence,
            controls,
            bindings,
            PreparationPublicationAuthority(plan, declaration, state, authority),
            spec.configuration,
            site.site.instance,
        )
    )
    return RecordedSiteTaskPreparation(
        plan,
        declaration,
        spec,
        site,
        resources,
        evidence,
        controls,
        authority,
        qualifications,
        records,
        state,
        on_acquired,
    )
