"""Original Group definition and full snapshot on the shared source records."""

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
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import (
    Clock,
    OperationControls,
    OperationControl,
)
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.gitlab.tasks.group_spec import GroupSpec
from lab_generate_skill.sites.gitlab.tasks.group_policy import group_initial_spec
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupRecoverySnapshot
from .gitlab_group_records import group_preparation_records
from .gitlab_group_source import GroupSourceSelection
from .source_qualification_records import (
    SourceQualificationRecords,
    SourceRecordDefinition,
)
from .source_qualification_progress import SourceQualificationProgress


class GroupSourceRecordPolicy:
    def __init__(
        self, selection: GroupSourceSelection, native_ref: EvidenceRef
    ) -> None:
        if not isinstance(selection, GroupSourceSelection):
            raise TypeError("Exact original Group selection required")
        self.selection, self.native_ref = selection, EvidenceRef.model_validate(
            native_ref
        )
        self.private = selection.load(self.native_ref, selection.public_template)

    def definition(
        self,
        owner: OriginalSourceQualificationOwner,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
        control: OperationControl,
    ) -> SourceRecordDefinition:
        declared = configuration.gitlab_group_inputs
        if declared is not None and (
            declared.scope != owner.scope or declared.origin.endpoint != site.endpoint
        ):
            raise OwnershipConflict(
                "Group source records changed declared scope/origin"
            )
        public = self.selection.public_at(site.endpoint, None)
        if (
            configuration.site_id != "gitlab"
            or configuration.private_evidence is None
            or configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or configuration.token.owner != owner.scope.owner
            or public.identity != owner.scope.task
            or self.private.task != owner.scope.task
            or site.files != configuration.files
        ):
            raise OwnershipConflict(
                "Group source changed original site/profile/owner/task"
            )
        if (
            owner.evidence.read(self.native_ref, control) != self.selection.native
            or self.selection.load(self.native_ref, public) != self.private
        ):
            raise OwnershipConflict(
                "Group source changed original immutable native bytes/meaning"
            )
        return SourceRecordDefinition(
            public,
            self.private,
            self.private.model_dump_json(),
            group_initial_spec(owner.scope.task),
            "engineering-gitlab-group-creation",
            "gitlab-group-creation",
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
        return group_preparation_records(store, controls, bindings, authority)

    def snapshot_bytes(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> tuple[str, bytes]:
        original = GroupRecoverySnapshot.model_validate_json(result.private_result)
        if (
            result.request_sha256 != request.digest
            or original.request != request
            or original.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Group source snapshot changed original request/canonical bytes"
            )
        return original.schema_version, result.private_result.encode()


class GroupSourceRecords(SourceQualificationRecords):
    def __init__(
        self,
        owner: OriginalSourceQualificationOwner,
        native: SourceQualificationNativeAuthority,
        site: SiteHandle,
        selection: GroupSourceSelection,
        native_ref: EvidenceRef,
        progress: SourceQualificationProgress,
        controls: OperationControls,
        clock: Clock,
        prefix: str,
        *,
        recovery_budgets: SourceRecoveryBudgets | None = None,
    ) -> None:
        policy = GroupSourceRecordPolicy(selection, native_ref)
        self.private: GroupSpec = policy.private
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
        )
