"""Group binding of the existing source-only lifecycle and ports.

An actual original owner and controlled installed reader are mandatory. The
source attempt closes and restores before publication; no Actor/claim/model or
training permission is supplied, and unknown native operations are not replayed.
"""

import hashlib
from pydantic import TypeAdapter
from .source_publication_window import publication_parent, closed_publication_operation
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from .gitlab_group_source_authority import (
    GroupSourceSiteAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_state import (
    SourceQualificationStateAuthority,
)
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.lifecycle import Clock, OperationControls, ResourceJournal
from lab_generate_skill.sites.gitlab.tasks.group_native_request import (
    GroupNativeRequestChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_spec import (
    GroupSpec,
)
from lab_generate_skill.sites.gitlab.tasks.group_source_recovery import (
    GroupSourceRecoveryChecks,
)
from .gitlab_group_records import group_state_qualifications
from lab_generate_skill.ports.state_qualification import StateQualificationChecks
from .gitlab_group_source_records import (
    GroupSourceRecords,
    GroupSourceRecordPolicy,
)
from .gitlab_group_source_measurement import measure_group_source
from .gitlab_group_source_publication import (
    ClosedGroupFacts,
    PublishedGroupSource,
    publish_group_source,
)
from .gitlab_group_source import GroupSourceSelection
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from .source_browser_assets import SourceBrowserAssets
from .source_qualification_environment import prepare_source
from .source_qualification_progress import SourceQualificationProgress
from .source_qualification_recovery import close_source_browser, restore_source


class GroupSourceUnconfirmed(RuntimeError):
    reason_code = "SOURCE_QUALIFICATION_UNCONFIRMED"

    def __init__(
        self,
        progress: SourceQualificationProgress,
        primary: BaseException | None,
        errors: tuple[BaseException, ...],
    ) -> None:
        self.progress, self.primary, self.cleanup_errors = progress, primary, errors
        self.references = tuple(dict.fromkeys(progress.references))
        self.actual_actor_dispatched = False
        super().__init__(
            "Original Group source unconfirmed; retain original scope/records and do not repeat effects"
        )


def qualify_group_source(
    owner: OriginalSourceQualificationOwner,
    spec: SiteResourceSpec,
    acquisition: OperationContext,
    selection: GroupSourceSelection,
    native_ref: EvidenceRef,
    assets: SourceBrowserAssets,
    *,
    journal: ResourceJournal,
    controls: OperationControls,
    clock: Clock,
    prefix: str,
    metadata_seconds: int,
    source_reads: ClosedSourceReadTransport,
    recovery_budgets: SourceRecoveryBudgets | None = None,
    publication_root: OperationContext | None = None,
    state_checks: StateQualificationChecks | None = None,
) -> PublishedGroupSource:
    recovery_budgets = (
        None
        if recovery_budgets is None
        else SourceRecoveryBudgets.model_validate(recovery_budgets)
    )
    if (
        not isinstance(owner, OriginalSourceQualificationOwner)
        or not isinstance(assets, SourceBrowserAssets)
        or not isinstance(source_reads, ClosedSourceReadTransport)
        or not isinstance(selection, GroupSourceSelection)
    ):
        raise TypeError(
            "Actual source owner/original bytes/assets and installed reader required"
        )
    prefix = TypeAdapter(Identifier).validate_python(prefix, strict=True)
    if (
        len(prefix) > 100
        or type(metadata_seconds) is not int
        or not 1 <= metadata_seconds <= 3600
    ):
        raise ValueError(
            "Explicit bounded original source namespace and metadata budget required"
        )
    spec, acquisition = SiteResourceSpec.model_validate(
        spec
    ), OperationContext.model_validate(acquisition)
    spec.check_operation(acquisition, "execute")
    publication = publication_parent(acquisition, publication_root, controls)
    policy = GroupSourceRecordPolicy(selection, native_ref)
    cfg = spec.configuration
    declared = cfg.gitlab_group_inputs
    if declared is not None and (
        declared.scope != owner.scope
        or declared.native_contract_sha256 != native_ref.sha256
        or declared.private_input_sha256
        != hashlib.sha256(policy.private.model_dump_json().encode()).hexdigest()
        or not selection.public_template.start_url.startswith(declared.origin.endpoint)
    ):
        raise OwnershipConflict(
            "Group source changed original declared scope/input/origin"
        )
    if (
        cfg.site_id != "gitlab"
        or cfg.private_evidence is None
        or cfg.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
        or policy.private.task != owner.scope.task
        or selection.public_template.identity != owner.scope.task
        or source_reads.store is not owner.evidence
    ):
        raise OwnershipConflict(
            "Group source changed original native selection/task/store"
        )
    control = controls.bind(acquisition)
    owner.require(acquisition, control, new_work=True)
    if owner.evidence.read(native_ref, control) != selection.native:
        raise OwnershipConflict("Group source changed original retained native bytes")
    p = SourceQualificationProgress()
    rights = GroupSourceSiteAuthority(owner, spec, acquisition)
    physical = ObservedSiteResourceAuthority(
        spec, acquisition, source=rights, evidence=owner.evidence
    )
    site_authority = TaskSiteAuthority(spec, acquisition, physical, origin=None)
    site = RetainedSiteResource(
        spec,
        acquisition,
        journal=journal,
        evidence=owner.evidence,
        controls=controls,
        clock=clock,
        authority=site_authority,
        cleanup_seconds=recovery_seconds(
            recovery_budgets, "site_close_seconds", metadata_seconds
        ),
    )
    native = SourceQualificationNativeAuthority(
        owner,
        spec,
        acquisition,
        journal,
        lambda: p.pending_native,
        GroupNativeRequestChecks(),
    )
    records = GroupSourceRecords(
        owner,
        native,
        site,
        selection,
        native_ref,
        p,
        controls,
        clock,
        prefix,
        recovery_budgets=recovery_budgets,
    )
    qualifications = group_state_qualifications(
        owner.evidence,
        controls,
        SourceQualificationStateAuthority(native, lambda: p.selections),
        checks=state_checks,
    )
    primary: BaseException | None = None
    errors: list[BaseException] = []
    try:
        with physical:
            try:
                p.phase = "acquiring-source"
                site.open(control)
                site_authority.bind_native(native, site.site)
                browser = records.define(
                    acquisition.model_copy(
                        update={"operation_id": prefix + ".definition"}
                    )
                )
                prepare_source(records, qualifications)
                measure_group_source(
                    records, browser, assets, operation_seconds=metadata_seconds
                )
            except BaseException as error:
                primary = error
            finally:
                try:
                    close_source_browser(records, primary)
                except BaseException as error:
                    errors.append(error)
                if (
                    p.prepare_request is not None
                    and p.prepare_result is not None
                    and p.browser_closure_ref is not None
                    and not p.restore_attempted
                ):
                    try:
                        restore_source(
                            records, qualifications, GroupSourceRecoveryChecks()
                        )
                    except BaseException as error:
                        errors.append(error)
                if site.phase != "new":
                    try:
                        cleanup = acquisition.cleanup(
                            prefix + ".site-close",
                            now=clock.utcnow(),
                            seconds=recovery_seconds(
                                recovery_budgets, "site_close_seconds", metadata_seconds
                            ),
                        )
                        site.close(cleanup, controls.bind(cleanup), primary=primary)
                    except BaseException as error:
                        errors.append(error)
    except BaseException as error:
        errors.append(error)
    if primary is not None or errors:
        raise GroupSourceUnconfirmed(p, primary, tuple(errors)) from primary
    if (
        p.initial is None
        or p.capture_intent_ref is None
        or p.capture_result_ref is None
        or p.baseline_inputs is None
        or p.baseline is None
        or p.reset_inputs is None
        or p.reset is None
        or p.selections is None
        or p.selections.restoration_ref is None
        or p.browser is None
        or p.browser.closed is None
        or site.closed is None
    ):
        raise GroupSourceUnconfirmed(
            p,
            OwnershipConflict(
                "Original Group source facts or complete closure are missing"
            ),
            (),
        )
    p.phase = "publishing-closed-source"
    try:
        freeze = closed_publication_operation(
            publication, prefix + ".public-context", metadata_seconds, controls, clock
        )
        result = publish_group_source(
            owner,
            ClosedGroupFacts(
                p.selections.environment_ref,
                p.selections.restoration_ref,
                p.initial,
                p.capture_intent_ref,
                p.capture_result_ref,
                spec,
                p.browser.spec,
                site.closed,
                p.browser.closed,
                p.baseline_inputs,
                p.baseline,
                p.reset_inputs,
                p.reset,
            ),
            freeze,
            controls,
            source_reads=source_reads,
        )
    except BaseException as error:
        raise GroupSourceUnconfirmed(p, error, ()) from error
    p.phase = "qualified-closed-source"
    return result
