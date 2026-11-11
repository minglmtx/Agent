"""Exact selected Admin inputs on the existing source-only record producer.

This binds original bytes and an acquired site's declared origin. Native/state
and record authorities remain mandatory; no claim, Actor or training grant.
"""

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
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    OperationControls,
    OperationControl,
    Clock,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
    NavigationRecoverySnapshot,
)
from .admin_navigation import (
    load_admin_navigation_inputs,
    admin_navigation_preparation_records,
)
from .source_qualification_progress import SourceQualificationProgress
from .source_qualification_records import (
    SourceQualificationRecords,
    SourceRecordDefinition,
)


class AdminNavigationSourceRecordPolicy:
    def __init__(self, raw: bytes, reference: EvidenceRef, public: PublicTask) -> None:
        selected = load_admin_navigation_inputs(raw, reference, public)
        self.raw, self.reference = raw, reference
        self.public, self.private = selected.public_task, selected.private_spec

    def definition(
        self,
        owner: OriginalSourceQualificationOwner,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
        control: OperationControl,
    ) -> SourceRecordDefinition:
        inputs = configuration.admin_navigation_inputs
        private_input = NavigationExecutionInput(spec=self.private).model_dump_json()
        if (
            configuration.schema_version != "site-worker-configuration/7"
            or inputs is None
            or inputs.scope != owner.scope
            or self.public.identity != owner.scope.task
            or inputs.native_contract_sha256 != self.reference.sha256
            or inputs.private_input_sha256
            != hashlib.sha256(private_input.encode()).hexdigest()
            or inputs.origin.endpoint != site.endpoint
            or site.files != configuration.files
        ):
            raise OwnershipConflict(
                "Admin source definition changed original scope/input/acquired origin"
            )
        raw = owner.evidence.read(self.reference, control)
        if raw != self.raw:
            raise OwnershipConflict(
                "Admin source definition changed original native bytes"
            )
        public = PublicTask.model_validate(
            self.public.model_copy(
                update={"start_url": site.endpoint + self.private.start_path}
            )
        )
        selected = load_admin_navigation_inputs(raw, self.reference, public)
        if selected.private_spec != self.private:
            raise OwnershipConflict(
                "Admin source definition changed original private branch"
            )
        return SourceRecordDefinition(
            public,
            self.private,
            private_input,
            navigation_initial_state_spec(owner.scope.task),
            "engineering-admin-navigation-page",
            "admin-navigation",
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
        return admin_navigation_preparation_records(
            store, controls, bindings, authority
        )

    def snapshot_bytes(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> tuple[str, bytes]:
        snapshot = NavigationRecoverySnapshot.model_validate_json(result.private_result)
        if snapshot.request != request:
            raise OwnershipConflict("Admin source snapshot changed original request")
        return snapshot.schema_version, result.private_result.encode()


class AdminNavigationSourceRecords(SourceQualificationRecords):
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        native: SourceQualificationNativeAuthority,
        site: SiteHandle,
        raw: bytes,
        reference: EvidenceRef,
        public: PublicTask,
        progress: SourceQualificationProgress,
        controls: OperationControls,
        clock: Clock,
        prefix: str,
        *,
        recovery_budgets: SourceRecoveryBudgets | None = None,
    ) -> None:
        policy = AdminNavigationSourceRecordPolicy(raw, reference, public)
        self.private = policy.private
        super().__init__(
            owner,
            native,
            site,
            policy,
            progress,
            controls,
            clock,
            prefix,
            recovery_budgets=recovery_budgets,
            reuse_inputs=True,
        )
