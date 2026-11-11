"""Original Map state semantics/native-file permissions over same-call CAS bodies."""

from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.adapters.operation_progress import operation_stage
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
    QualifiedResetChecks,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from .state_input_transport import MapStateInputsTransport


class MapStateGraphChecks:
    def __init__(
        self,
        inputs: MapStateInputsTransport,
        files: MapStateFileReader,
        site: SiteResourceSpec,
        started: SiteResourceStarted,
    ) -> None:
        if not isinstance(inputs, MapStateInputsTransport) or not callable(
            getattr(files, "read", None)
        ):
            raise TypeError(
                "Original Map input transport and explicit file reader required"
            )
        self.inputs, self.files = inputs, files
        self.site = SiteResourceSpec.model_validate(site)
        self.started = SiteResourceStarted.model_validate(started)
        cfg = self.site.configuration.map_inputs
        if cfg is None or cfg.scope.task != inputs.task:
            raise OwnershipConflict("Map graph inputs changed original site task")

    def environment(
        self,
        selection: EnvironmentSelection,
        reference: EvidenceRef,
        operation: OperationContext,
        control: OperationControl,
    ) -> EnvironmentBaseline:
        with self.inputs.inputs(selection, reference, control) as reader:
            with operation_stage("map.state-original-checks"):
                return OverlayStateChecks(
                    reader, self.files, self.site, self.started
                ).environment(selection, reference, operation, reader.control)

    def reset(
        self,
        selection: ResetSelection,
        reference: EvidenceRef,
        control: OperationControl,
    ) -> QualifiedResetChecks:
        with self.inputs.inputs(selection, reference, control) as reader:
            with operation_stage("map.state-original-checks"):
                return OverlayStateChecks(
                    reader, self.files, self.site, self.started
                ).reset(selection, reference, reader.control)
