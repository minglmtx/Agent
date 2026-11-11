"""Join original native preparation/account and declared photo plan before spawn."""

import hashlib
from typing import Protocol
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.preparation import PreparedTask
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceStarted,
)
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from lab_generate_skill.domain.browser_task_files import BrowserTaskFilesPlan
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from ..state_reads import RedditStateReads
from .image_recovery import ImageObserved


class ImageFilePlan(Protocol):
    def __call__(
        self, scope: StateScope, staging_root: str
    ) -> BrowserTaskFilesPlan: ...


class ImageBrowserChecks(RedditStateReads):
    def __init__(self, store: EvidenceReader, file_plan: ImageFilePlan) -> None:
        super().__init__(store)
        self.file_plan = file_plan

    def check(
        self,
        publication: PreparedPublication,
        site_spec: SiteResourceSpec,
        site: SiteResourceStarted,
        request: SiteTaskRequest,
        initialization: BrowserInitialization,
        control: OperationControl,
    ) -> None:
        if not isinstance(initialization, RedditNativeImageInitialization):
            raise ValueError("Explicit fixed Reddit browser semantics required")
        selected = RedditNativeImageInitialization.model_validate(initialization)
        prepared = self.read(
            publication.prepared_ref, "prepared-task/1", PreparedTask, control
        )
        selected.check_task(prepared.public_task)
        if (
            selected.prepared_ref != publication.prepared_ref
            or selected.task_files.scope != prepared.scope
        ):
            raise OwnershipConflict(
                "Reddit files changed original prepared task/attempt/context"
            )
        self.check_native_account(
            publication.selection.result_ref,
            request,
            selected,
            site_spec.configuration,
            site.instance,
            site.ready.worker.owner_guard,
            control,
        )

    def check_native_account(
        self,
        result_ref: EvidenceRef,
        request: SiteTaskRequest,
        selected: RedditNativeImageInitialization,
        configuration: SiteWorkerConfiguration,
        instance: SiteInstanceStarted,
        guard: ProcessOwnerGuard,
        control: OperationControl,
    ) -> None:
        selected = RedditNativeImageInitialization.model_validate(selected)
        request = SiteTaskRequest.model_validate(request)
        request.check_site(configuration)
        scope = selected.task_files.scope
        expected = self.file_plan(
            scope, configuration.files.node_root + "/browser-uploads"
        )
        if (
            configuration.site_id != "reddit"
            or selected.endpoint != instance.endpoint
            or instance.files != configuration.files
            or selected.task_files != expected
            or scope.owner != configuration.token.owner
            or (scope.task, scope.attempt_id)
            != (request.task, request.operation.attempt_id)
            or selected.task_files.workspace_root != configuration.files.workspace_root
        ):
            raise OwnershipConflict(
                "Reddit browser changed original site, task or declared photo delivery"
            )
        result = self.read(result_ref, "site-task-result/1", SiteTaskResult, control)
        observed = ImageObserved.model_validate_json(result.private_result)
        if (
            request.action != "prepare"
            or result.request_sha256 != request.digest
            or observed.request != request
            or observed.model_dump_json() != result.private_result
        ):
            raise OwnershipConflict(
                "Reddit browser lost original preparation measurement"
            )
        observed.snapshot.check_request(request)
        for descriptor in (observed.snapshot.native_before, observed.native):
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
                    "Reddit browser changed original native worker/site"
                )
        before = self.reference(
            observed.snapshot.native_before, observed.snapshot.request, control
        )
        current = self.capture(observed.native, request, control)
        if before.capture != current or (
            selected.native_account_id,
            selected.native_account_username,
        ) != (before.account.id, before.account.username):
            raise OwnershipConflict(
                "Reddit browser account/state differs from original native preparation"
            )
        control.checkpoint()
