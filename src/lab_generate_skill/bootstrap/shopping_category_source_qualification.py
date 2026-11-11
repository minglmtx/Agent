"""Shopping category navigation binding of the existing source-only lifecycle and ports.

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
from lab_generate_skill.adapters.sites.shopping_category_source_authority import (
    CategoryNavigationSourceSiteAuthority,
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
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.lifecycle import Clock, OperationControls, ResourceJournal
from lab_generate_skill.sites.shopping.tasks.navigation_native_request import (
    CategoryNavigationNativeRequestChecks,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.navigation_source_recovery import (
    CategoryNavigationSourceRecoveryChecks,
)
from .shopping_category_records import category_state_qualifications
from .shopping_category_source_records import CategoryNavigationSourceRecordPolicy
from .shopping_category_source_artifact import consume_category_navigation_source
from .source_qualification_records import SourceQualificationRecords
from .shopping_category_source_measurement import measure_category_navigation_source
from .shopping_category_source_publication import (
    ClosedCategoryNavigationFacts,
    PublishedCategoryNavigationSource,
    publish_category_navigation_source,
)
from .source_browser_assets import SourceBrowserAssets
from .source_qualification_environment import prepare_source
from .source_qualification_progress import SourceQualificationProgress
from .source_qualification_recovery import close_source_browser, restore_source


class CategoryNavigationSourceUnconfirmed(RuntimeError):
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
            "Original Shopping category navigation source unconfirmed; retain original scope/records and do not repeat effects"
        )


def qualify_category_navigation_source(
    owner: OriginalSourceQualificationOwner,
    spec: SiteResourceSpec,
    acquisition: OperationContext,
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
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
    retained_source: ClosedCategoryNavigationReadMaterial | None = None,
) -> PublishedCategoryNavigationSource:
    recovery_budgets = (
        None
        if recovery_budgets is None
        else SourceRecoveryBudgets.model_validate(recovery_budgets)
    )
    if (
        not isinstance(owner, OriginalSourceQualificationOwner)
        or not isinstance(assets, SourceBrowserAssets)
        or not isinstance(source_reads, ClosedSourceReadTransport)
        or type(raw) is not bytes
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
    policy = CategoryNavigationSourceRecordPolicy(raw, native_ref, public)
    inputs = spec.configuration.shopping_category_inputs
    if (
        spec.configuration.site_id != "shopping"
        or spec.configuration.schema_version != "site-worker-configuration/9"
        or inputs is None
        or inputs.scope != owner.scope
        or inputs.native_contract_sha256 != native_ref.sha256
        or inputs.private_input_sha256
        != hashlib.sha256(
            CategoryNavigationExecutionInput(spec=policy.private)
            .model_dump_json()
            .encode()
        ).hexdigest()
        or spec.configuration.files.image.sha256 != SHOPPING_IMAGE_SHA
        or spec.token.owner != owner.scope.owner
        or policy.public.identity != owner.scope.task
        or policy.private.task != owner.scope.task
        or source_reads.store is not owner.evidence
    ):
        raise OwnershipConflict(
            "Category source changed original task/image/scope/store"
        )
    control = controls.bind(acquisition)
    if retained_source is not None:
        retained_source = ClosedCategoryNavigationReadMaterial.model_validate(
            retained_source
        )
        if (
            retained_source.site.configuration.installation
            != spec.configuration.installation
            or retained_source.browser.configuration.installation
            != spec.configuration.installation
        ):
            raise OwnershipConflict(
                "Existing category source differs from the selected installation"
            )
        return consume_category_navigation_source(
            owner,
            retained_source,
            raw,
            native_ref,
            public,
            publication,
            controls,
            source_reads,
        )
    owner.require(acquisition, control, new_work=True)
    if owner.evidence.read(native_ref, control) != raw:
        raise OwnershipConflict(
            "Shopping category source changed original retained native bytes"
        )
    p = SourceQualificationProgress()
    rights = CategoryNavigationSourceSiteAuthority(owner, spec, acquisition)
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
        CategoryNavigationNativeRequestChecks(),
        current_evidence=source_reads,
    )
    records = SourceQualificationRecords(
        owner,
        native,
        site,
        policy,
        p,
        controls,
        clock,
        prefix,
        recovery_budgets=recovery_budgets,
        reuse_inputs=True,
    )
    qualifications = category_state_qualifications(
        owner.evidence,
        controls,
        SourceQualificationStateAuthority(native, lambda: p.selections),
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
                measure_category_navigation_source(
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
                            records,
                            qualifications,
                            CategoryNavigationSourceRecoveryChecks(),
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
    if records.input_bodies is not None:
        p.input_reuse = dict(records.input_bodies.records.statistics)
        records.input_bodies.close()
    native.close_input_read()
    if primary is not None or errors:
        raise CategoryNavigationSourceUnconfirmed(
            p, primary, tuple(errors)
        ) from primary
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
        raise CategoryNavigationSourceUnconfirmed(
            p,
            OwnershipConflict(
                "Original Shopping category source facts or complete closure are missing"
            ),
            (),
        )
    p.phase = "publishing-closed-source"
    try:
        freeze = closed_publication_operation(
            publication, prefix + ".public-context", metadata_seconds, controls, clock
        )
        result = publish_category_navigation_source(
            owner,
            ClosedCategoryNavigationFacts(
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
                dict(p.input_reuse),
            ),
            freeze,
            controls,
            source_reads=source_reads,
        )
    except BaseException as error:
        raise CategoryNavigationSourceUnconfirmed(p, error, ()) from error
    p.phase = "qualified-closed-source"
    return result
