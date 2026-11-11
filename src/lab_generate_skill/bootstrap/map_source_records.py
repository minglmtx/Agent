"""Original Map declaration and codecs on the shared source record producer."""

import hashlib
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_records import (
    SourceQualificationRecordAuthority,
)
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.navigation_policy import navigation_initial_spec
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationSnapshot
from .map_navigation_source import MapNavigationSourceSelection
from .map_overlay_records import map_preparation_records
from .map_source_progress import MapSourceProgress
from .source_qualification_records import (
    SourceQualificationRecords,
    SourceRecordDefinition,
)


class MapSourceRecordPolicy:
    def __init__(
        self, selection: MapNavigationSourceSelection, private: NavigationSpec
    ) -> None:
        self.selection, self.private = selection, private

    def definition(
        self,
        owner: OriginalSourceQualificationOwner,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
        control: OperationControl,
    ) -> SourceRecordDefinition:
        public = self.selection.public_at(site.endpoint, None)
        if (
            self.selection.load(self.private.native_contract_ref, public)
            != self.private
        ):
            raise OwnershipConflict(
                "Actual source public origin changed original native binding"
            )
        inputs = configuration.map_inputs
        if (
            inputs is None
            or inputs.scope != owner.scope
            or hashlib.sha256(self.private.model_dump_json().encode()).hexdigest()
            != inputs.private_input_sha256
        ):
            raise OwnershipConflict(
                "Source definition changed actual configured input/scope"
            )
        return SourceRecordDefinition(
            public,
            self.private,
            self.private.model_dump_json(),
            navigation_initial_spec(
                owner.scope.task, self.private.native_contract_ref.sha256
            ),
            "engineering-map-navigation-page",
            "map-native-navigation",
        )

    def preparations(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        bindings: EvidenceTaskBindings,
        authority: SourceQualificationRecordAuthority,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
    ) -> EvidencePreparationRecords:
        return map_preparation_records(
            store, controls, bindings, authority, configuration, site
        )

    def snapshot_bytes(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> tuple[str, bytes]:
        snapshot = NavigationSnapshot.model_validate_json(result.private_result)
        if snapshot.request != request:
            raise OwnershipConflict(
                "Source native snapshot changed its original request"
            )
        return snapshot.schema_version, result.private_result.encode()


class MapSourceRecords(SourceQualificationRecords):
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        native: SourceQualificationNativeAuthority,
        site: SiteHandle,
        selection: MapNavigationSourceSelection,
        private: NavigationSpec,
        progress: MapSourceProgress,
        controls: OperationControls,
        clock: Clock,
        prefix: str,
        *,
        recovery_budgets: SourceRecoveryBudgets | None = None,
    ) -> None:
        self.selection, self.private = selection, private
        self.progress: MapSourceProgress = progress
        super().__init__(
            owner,
            native,
            site,
            MapSourceRecordPolicy(selection, private),
            progress,
            controls,
            clock,
            prefix,
            recovery_budgets=recovery_budgets,
            reuse_inputs=True,
        )
