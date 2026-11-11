"""Require the original complete prepared Group account before any browser use."""

import hashlib
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceResult
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .group_reads import GroupStateReads
from .group_recovery import GroupObserved
from .group_capture import GroupCapturedFacts, same_group_state
from .native_snapshot import same_native_snapshot


class GroupBrowserChecks(GroupStateReads):
    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None:
        if not isinstance(initialization, GitlabGroupInitialization):
            raise ValueError("Explicit fixed Group browser semantics required")
        self.check_native_account(
            publication.selection.result_ref,
            request,
            initialization,
            site_spec.configuration,
            site.instance,
            site.ready.worker.owner_guard,
            control,
        )

    def check_native_account(
        self,
        result_ref: EvidenceRef,
        request: SiteTaskRequest,
        selected: GitlabGroupInitialization,
        configuration: SiteWorkerConfiguration,
        instance: SiteInstanceStarted,
        guard: ProcessOwnerGuard,
        control: OperationControl,
    ) -> None:
        request.check_site(configuration)
        if (
            configuration.private_evidence is None
            or configuration.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
        ):
            raise OwnershipConflict("Group browser changed original declared profile")
        result = self.read(result_ref, "site-task-result/1", SiteTaskResult, control)
        observed = GroupObserved.model_validate_json(result.private_result)
        if (
            request.action != "prepare"
            or result.request_sha256 != request.digest
            or observed.request != request
            or observed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Group browser lost original preparation measurement"
            )
        same_native_snapshot(
            request,
            observed.snapshot.request,
            observed.snapshot.model_dump_json().encode(),
            observed.snapshot.schema_version,
            request.snapshot_ref,
            "Group",
        )

        def native(
            descriptor: SitePrivateEvidenceResult, original: SiteTaskRequest
        ) -> GroupCapturedFacts:
            context = descriptor.context
            if (
                context.configuration_sha256,
                context.token,
                context.instance,
                context.owner_guard,
            ) != (
                hashlib.sha256(configuration.model_dump_json().encode()).hexdigest(),
                configuration.token,
                instance,
                guard,
            ):
                raise OwnershipConflict("Group browser changed original worker/site")
            return self.native(descriptor, original, control)

        before = native(observed.snapshot.native_before, observed.snapshot.request)
        current = native(observed.native, request)
        if (
            not same_group_state(before, current)
            or selected.native_account_id != current.state.user.id
        ):
            raise OwnershipConflict(
                "Group browser account is not original prepared native account"
            )
        control.checkpoint()
