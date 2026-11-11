"""Source-only Map initializer on the existing registered resource/native ports.

This produces the measured source before a task claim or Actor dispatch. The
application execute_task remains the only task lifecycle. No model, runner,
ledger, recovery replacement or automatic repeat is introduced here.
"""

import hashlib
from dataclasses import replace
from pydantic import TypeAdapter
from .source_publication_window import publication_parent, closed_publication_operation
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.retained_resource import RetainedSiteResource
from lab_generate_skill.adapters.sites.source_qualification_authority import (
    SourceQualificationSiteAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_state import (
    SourceQualificationStateAuthority,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.ports.lifecycle import ResourceJournal, OperationControls, Clock
from lab_generate_skill.sites.map.tasks.native_request_rules import (
    NavigationNativeRequestChecks,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from .map_navigation_source import MapNavigationSourceSelection
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from .map_source_environment import prepare_map_source
from .map_source_artifact import consume_map_navigation_source
from .map_source_measurement import SourceBrowserAssets, measure_map_source
from .map_source_progress import MapSourceProgress
from .map_source_publication import (
    ClosedMapQualificationFacts,
    PublishedClosedMapQualification,
    publish_closed_map_qualification,
)
from .map_source_records import MapSourceRecords
from .map_source_recovery import close_map_source_browser, restore_map_source
from .map_state_qualification import map_state_qualifications
from lab_generate_skill.adapters.map_artifacts.state_input_transport import (
    MapStateInputsTransport,
)


class MapSourceQualificationUnconfirmed(RuntimeError):
    """Original retained objects/refs only; never permission to reinitialize."""

    reason_code = "SOURCE_QUALIFICATION_UNCONFIRMED"

    def __init__(
        self,
        progress: MapSourceProgress,
        primary: BaseException | None,
        errors: tuple[BaseException, ...],
    ) -> None:
        self.progress, self.primary, self.cleanup_errors = progress, primary, errors
        self.references = tuple(dict.fromkeys(progress.references))
        self.actual_actor_dispatched = False
        super().__init__(
            "Original source qualification unconfirmed; retain original scope/records and do not repeat effects"
        )


def qualify_map_navigation_source(
    owner: OriginalSourceQualificationOwner,
    spec: SiteResourceSpec,
    acquisition: OperationContext,
    selection: MapNavigationSourceSelection,
    private: NavigationSpec,
    assets: SourceBrowserAssets,
    *,
    journal: ResourceJournal,
    controls: OperationControls,
    clock: Clock,
    prefix: str,
    metadata_seconds: int,
    source_reads: ClosedSourceReadTransport | None = None,
    recovery_budgets: SourceRecoveryBudgets | None = None,
    publication_root: OperationContext | None = None,
    state_inputs: MapStateInputsTransport | None = None,
    retained_source: ClosedMapReadMaterial | None = None,
) -> PublishedClosedMapQualification:
    recovery_budgets = (
        None
        if recovery_budgets is None
        else SourceRecoveryBudgets.model_validate(recovery_budgets)
    )
    if (
        not isinstance(owner, OriginalSourceQualificationOwner)
        or not isinstance(selection, MapNavigationSourceSelection)
        or not isinstance(private, NavigationSpec)
        or not isinstance(assets, SourceBrowserAssets)
    ):
        raise TypeError(
            "Actual source owner, original selected bytes and installed browser assets required"
        )
    prefix = TypeAdapter(Identifier).validate_python(prefix, strict=True)
    if (
        len(prefix) > 100
        or type(metadata_seconds) is not int
        or not 1 <= metadata_seconds <= 3600
    ):
        raise ValueError("Bounded source namespace and metadata budget required")
    spec, acquisition = SiteResourceSpec.model_validate(
        spec
    ), OperationContext.model_validate(acquisition)
    spec.check_operation(acquisition, "execute")
    publication = publication_parent(acquisition, publication_root, controls)
    inputs = spec.configuration.map_inputs
    if (
        not isinstance(inputs, MapNavigationWorkerInputs)
        or inputs.scope != owner.scope
        or inputs.origin.mode != "dynamic"
        or selection.public_template.identity != owner.scope.task
        or private.task != owner.scope.task
        or inputs.native_contract_sha256 != private.native_contract_ref.sha256
        or inputs.private_input_sha256
        != hashlib.sha256(private.model_dump_json().encode()).hexdigest()
        or selection.load(private.native_contract_ref, selection.public_template)
        != private
    ):
        raise OwnershipConflict(
            "Source initializer changed original selected task/private input/scope"
        )
    control = controls.bind(acquisition)
    if state_inputs is not None and (
        not isinstance(state_inputs, MapStateInputsTransport)
        or state_inputs.task != owner.scope.task
    ):
        raise OwnershipConflict("Map source state inputs changed original task")
    if retained_source is not None:
        retained_source = ClosedMapReadMaterial.model_validate(retained_source)
        if (
            retained_source.site.configuration.installation
            != spec.configuration.installation
            or retained_source.browser.configuration.installation
            != spec.configuration.installation
        ):
            raise OwnershipConflict(
                "Existing source differs from the selected installation"
            )
        if source_reads is None:
            raise TypeError(
                "Existing Map source requires the controlled installed reader"
            )
        return consume_map_navigation_source(
            owner,
            retained_source,
            selection,
            private,
            publication,
            controls,
            source_reads,
        )
    owner.require(acquisition, control, new_work=True)
    if (
        owner.evidence.read(private.native_contract_ref, control=control)
        != selection.native
    ):
        raise OwnershipConflict(
            "Source initializer changed original pinned native bytes"
        )
    progress = MapSourceProgress()
    rights = SourceQualificationSiteAuthority(owner, spec, acquisition)
    physical = ObservedSiteResourceAuthority(
        spec, acquisition, source=rights, evidence=owner.evidence
    )
    site_authority = TaskSiteAuthority(
        spec,
        acquisition,
        physical,
        origin=OriginalMapOriginAuthority(
            contexts=None, evidence=None, source=None, read_operation=None
        ),
    )
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
        lambda: progress.pending_native,
        NavigationNativeRequestChecks(),
        current_evidence=source_reads,
    )
    records = MapSourceRecords(
        owner,
        native,
        site,
        selection,
        private,
        progress,
        controls,
        clock,
        prefix,
        recovery_budgets=recovery_budgets,
    )
    qualifications = map_state_qualifications(
        owner.evidence,
        controls,
        SourceQualificationStateAuthority(native, lambda: progress.selections),
        spec,
        lambda: site.site,
        state_inputs=state_inputs,
    )
    primary: BaseException | None = None
    errors: list[BaseException] = []
    try:
        with physical:
            try:
                progress.phase = "acquiring-source"
                site.open(control)
                site_authority.bind_native(native, site.site)
                declaration_op = acquisition.model_copy(
                    update={"operation_id": prefix + ".definition"}
                )
                browser = records.define(declaration_op)
                prepare_map_source(records, qualifications)
                measure_map_source(
                    records, browser, assets, operation_seconds=metadata_seconds
                )
            except BaseException as error:
                primary = error
            finally:
                try:
                    close_map_source_browser(records, primary)
                except BaseException as error:
                    errors.append(error)
                # A failed initial check can still restore its known original
                # prepared state after confirmed browser closure. Unknown
                # restore/resume is never sent again under a new operation ID.
                if (
                    progress.prepare_request is not None
                    and progress.prepare_result is not None
                    and progress.browser_closure_ref is not None
                    and not progress.restore_attempted
                ):
                    try:
                        restore_map_source(records, qualifications)
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
        progress.input_reuse = dict(records.input_bodies.records.statistics)
        records.input_bodies.close()
    native.close_input_read()
    if primary is not None or errors:
        raise MapSourceQualificationUnconfirmed(
            progress, primary, tuple(errors)
        ) from primary
    p = progress
    if (
        p.initial is None
        or p.initial_capture is None
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
        raise MapSourceQualificationUnconfirmed(
            p, OwnershipConflict("Original source facts/closure are incomplete"), ()
        )
    p.phase = "publishing-closed-source"
    # Publication follows complete onsite closure, under the original signal/root.
    try:
        freeze = closed_publication_operation(
            publication, prefix + ".public-context", metadata_seconds, controls, clock
        )
        result = publish_closed_map_qualification(
            owner,
            ClosedMapQualificationFacts(
                p.selections.environment_ref,
                p.selections.restoration_ref,
                p.initial,
                p.initial_capture,
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
            clock,
            metadata_seconds=metadata_seconds,
            source_reads=source_reads,
        )
    except BaseException as error:
        raise MapSourceQualificationUnconfirmed(p, error, ()) from error
    p.phase = "qualified-closed-source"
    return replace(result, source_prefix_reuse=dict(progress.input_reuse))
