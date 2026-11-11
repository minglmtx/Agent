"""Measured current Group account on the existing late browser declaration port."""

from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.models.actor_execution_scope import ActorExecutionScope
from lab_generate_skill.adapters.sites.task_preparation import (
    RecordedSiteTaskPreparation,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.task_initialization import TaskActorInitialization
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.gitlab.tasks.group_reads import GroupStateReads
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from .gitlab_group_browser_declarations import group_browser_declaration
from .gitlab_group_capture import load_group_capture
from .task_browser_declarations import OriginalTaskBrowserDeclarations


def prepared_group_browser_initialization(
    prep: RecordedSiteTaskPreparation,
    public: PublicTask,
    prepared_ref: EvidenceRef,
    site_ref: EvidenceRef,
    control: OperationControl,
) -> GitlabGroupInitialization:
    """Consume persisted original native preparation; never initialize a browser."""
    if not isinstance(prep, RecordedSiteTaskPreparation):
        raise TypeError("Original recorded Group preparation required")
    public = PublicTask.model_validate(public)
    prepared_ref, site_ref = EvidenceRef.model_validate(
        prepared_ref
    ), EvidenceRef.model_validate(site_ref)
    control.checkpoint()
    state = prep.state
    if (
        state.phase != "prepared"
        or state.result is None
        or state.prepare_request is None
        or state.prepare_result is None
        or state.result.publication.prepared_ref != prepared_ref
        or state.original_acquired().site_started_ref != site_ref
    ):
        raise OwnershipConflict("Original completed Group preparation required")
    request, result = state.prepare_request, state.prepare_result
    observed = GroupObserved.model_validate_json(result.private_result)
    if (
        observed.request != request
        or result.request_sha256 != request.digest
        or public.identity != prep.declaration.scope.task
    ):
        raise OwnershipConflict("Group browser changed original prepared request/task")
    measured = GroupStateReads(prep.reads.store, load_group_capture).native(
        observed.native, request, control
    )
    return group_browser_declaration(
        public,
        prep.site.site.instance.endpoint,
        measured.state.user.id,
        prepared_ref,
        site_ref,
    )


class OriginalGroupTaskBrowserDeclarations(OriginalTaskBrowserDeclarations):
    def __init__(
        self,
        owner: ClaimedRunResourceOwner,
        model: ActorExecutionScope,
        reset: ResetPlan,
        template: BrowserWorkerConfiguration,
        actor: TaskActorInitialization,
    ) -> None:
        def initialization(
            prep: RecordedSiteTaskPreparation,
            prepared: EvidenceRef,
            site: EvidenceRef,
            control: OperationControl,
        ) -> GitlabGroupInitialization:
            public = owner.reads.parse(
                owner.task.public_task_ref,
                "public-task/1",
                PublicTask,
                control,
                visibility="public",
            )
            return prepared_group_browser_initialization(
                prep, public, prepared, site, control
            )

        super().__init__(
            owner,
            model,
            reset,
            template,
            actor,
            initialization=initialization,
            producer="gitlab-group-task-browser-declarations",
        )
