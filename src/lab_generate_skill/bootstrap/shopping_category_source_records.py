"""Exact category native bytes on the existing source record producer."""

import hashlib
from lab_generate_skill.adapters.sites.source_qualification_records import (
    SourceQualificationRecordAuthority,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_recovery import (
    CategoryNavigationRecoverySnapshot,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from .shopping_category_navigation import load_category_navigation_inputs
from .shopping_category_records import category_preparation_records
from .source_qualification_records import SourceRecordDefinition


class CategoryNavigationSourceRecordPolicy:
    def __init__(self, raw: bytes, reference: EvidenceRef, public: PublicTask) -> None:
        selected = load_category_navigation_inputs(raw, reference, public)
        self.raw, self.reference = raw, reference
        self.public, self.private = selected.public_task, selected.private_spec

    def definition(
        self,
        owner: OriginalSourceQualificationOwner,
        configuration: SiteWorkerConfiguration,
        site: SiteInstanceStarted,
        control: OperationControl,
    ) -> SourceRecordDefinition:
        configuration = SiteWorkerConfiguration.model_validate(configuration)
        site = SiteInstanceStarted.model_validate(site)
        control.checkpoint()
        inputs = configuration.shopping_category_inputs
        private_input = CategoryNavigationExecutionInput(
            spec=self.private
        ).model_dump_json()
        if (
            configuration.site_id != "shopping"
            or configuration.schema_version != "site-worker-configuration/9"
            or inputs is None
            or inputs.scope != owner.scope
            or inputs.native_contract_sha256 != self.reference.sha256
            or inputs.private_input_sha256
            != hashlib.sha256(private_input.encode()).hexdigest()
            or inputs.origin.endpoint != site.endpoint
            or configuration.files.image.sha256 != SHOPPING_IMAGE_SHA
            or configuration.token.owner != owner.scope.owner
            or self.public.identity != owner.scope.task
            or self.private.task != owner.scope.task
            or site.files != configuration.files
            or site.endpoint != f"http://127.0.0.1:{site.ports[0]}/"
        ):
            raise OwnershipConflict(
                "Category source changed original task/owner/image/acquired root"
            )
        raw = owner.evidence.read(self.reference, control)
        if raw != self.raw:
            raise OwnershipConflict("Category source changed retained native bytes")
        public = PublicTask.model_validate(
            self.public.model_copy(
                update={
                    "start_url": site.endpoint[:-1] + self.private.original.start_path
                }
            )
        )
        selected = load_category_navigation_inputs(raw, self.reference, public)
        if selected.private_spec != self.private:
            raise OwnershipConflict("Category source changed original private branch")
        control.checkpoint()
        return SourceRecordDefinition(
            public,
            self.private,
            private_input,
            category_navigation_initial_spec(owner.scope.task),
            "engineering-shopping-category-navigation",
            "shopping-category-navigation",
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
        return category_preparation_records(store, controls, bindings, authority)

    def snapshot_bytes(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> tuple[str, bytes]:
        snapshot = CategoryNavigationRecoverySnapshot.model_validate_json(
            result.private_result
        )
        if (
            snapshot.request != request
            or result.request_sha256 != request.digest
            or snapshot.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict("Category source snapshot changed original request")
        return snapshot.schema_version, result.private_result.encode()
