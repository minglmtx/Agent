"""Original Map source declaration on the shared physical source lifecycle."""

from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from .source_site_lifecycle import SourceSiteLifecycleAuthority


class SourceQualificationSiteAuthority(SourceSiteLifecycleAuthority):
    def verify_source_declaration(self) -> None:
        inputs = self.spec.configuration.map_inputs
        if (
            not isinstance(inputs, MapNavigationWorkerInputs)
            or inputs.scope != self.owner.scope
        ):
            raise OwnershipConflict(
                "Original current Map task/site/controller required"
            )
        if inputs.origin.mode != "dynamic":
            raise OwnershipConflict(
                "Source-only site requires its original independent dynamic attempt"
            )
