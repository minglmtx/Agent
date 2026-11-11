"""Recompute the private browser account from original complete native CAS."""

import hashlib
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
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
from ..state_reads import GitlabStateReads
from .ssh_key_admission import same_snapshot
from .ssh_key_recovery import SshKeyObserved
from .ssh_key_state import SshKeyNativeState
from .ssh_key_rules import preserved


class SshKeyBrowserChecks(GitlabStateReads):
    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None:
        if not isinstance(initialization, GitlabSshKeyInitialization):
            raise ValueError("Explicit fixed GitLab browser semantics required")
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
        selected: GitlabSshKeyInitialization,
        configuration: SiteWorkerConfiguration,
        instance: SiteInstanceStarted,
        guard: ProcessOwnerGuard,
        control: OperationControl,
    ) -> None:
        request.check_site(configuration)
        result = self.read(result_ref, "site-task-result/1", SiteTaskResult, control)
        observed = SshKeyObserved.model_validate_json(result.private_result)
        if (
            request.action != "prepare"
            or result.request_sha256 != request.digest
            or observed.request != request
            or observed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "GitLab browser lost original preparation measurement"
            )
        same_snapshot(request, observed.snapshot, request.snapshot_ref)

        def native(
            descriptor: SitePrivateEvidenceResult, original: SiteTaskRequest
        ) -> SshKeyNativeState:
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
                raise OwnershipConflict(
                    "GitLab browser changed original native worker/site"
                )
            return self.native(descriptor, original, control)

        before = native(observed.snapshot.native_before, observed.snapshot.request)
        current = native(observed.native, request)
        if (
            not preserved(before, current)
            or before.keys != current.keys
            or selected.native_account_id != current.account.id
        ):
            raise OwnershipConflict(
                "GitLab browser account is not original prepared native account"
            )
        control.checkpoint()
