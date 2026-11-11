"""One measured source browser return/capture; no Actor or predicted baseline."""

from datetime import timedelta
from collections.abc import Callable
from dataclasses import dataclass
from lab_generate_skill.domain.source_recovery_budget import (
    SourceRecoveryBudgets,
    recovery_seconds,
)
from lab_generate_skill.domain.browser_initialization import BrowserInitialization
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.prepared_browser import PreparedBrowserTaskChecks
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.domain.validation import Identifier
from pydantic import TypeAdapter
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.recorded_capture import (
    RecordedBrowserCapture,
)
from lab_generate_skill.adapters.browsergym.source_qualification_authority import (
    SourceQualificationBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.source_qualification_observation import (
    SourceQualificationObservationAuthority,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.browser_capture import BrowserCaptureRequest
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_step import BrowserSlurmBinding
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRequirements
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import AllocationToken
from lab_generate_skill.domain.task import PublicTask
from .source_qualification_records import SourceQualificationRecords


from .source_browser_assets import SourceBrowserAssets as SourceBrowserAssets


@dataclass(frozen=True)
class SourceMeasurementBinding:
    initialization: BrowserInitialization
    prepared_checks: PreparedBrowserTaskChecks
    collector: tuple[str, str]
    initial_checks: Callable[[EvidenceRef, EvidenceRef], InitialObservationChecks]

    def __post_init__(self) -> None:
        TypeAdapter(tuple[Identifier, Identifier]).validate_python(
            self.collector, strict=True
        )
        TypeAdapter(BrowserInitialization).validate_python(
            self.initialization, strict=True
        )
        if not callable(getattr(self.prepared_checks, "check", None)) or not callable(
            self.initial_checks
        ):
            raise TypeError(
                "Explicit original preparation and initial check policies required"
            )


def measure_source(
    records: SourceQualificationRecords,
    token: AllocationToken,
    assets: SourceBrowserAssets,
    declaration: Callable[
        [SourceQualificationRecords, PublicTask], SourceMeasurementBinding
    ],
    *,
    operation_seconds: int,
) -> None:
    if (
        not isinstance(records, SourceQualificationRecords)
        or not isinstance(assets, SourceBrowserAssets)
        or not callable(declaration)
    ):
        raise TypeError(
            "Original source records/assets and explicit measurement binding required"
        )
    if type(operation_seconds) is not int or not 1 <= operation_seconds <= 3600:
        raise ValueError("Explicit bounded source browser operation duration required")
    p, native, owner = records.progress, records.native, records.owner
    token = AllocationToken.model_validate(token)
    if (
        token.owner != owner.scope.owner
        or token.attempt_id != owner.scope.attempt_id
        or token.resource_kind != "browser"
    ):
        raise OwnershipConflict(
            "Source browser token changed original owner/attempt/kind"
        )
    if (
        p.publication is None
        or p.prepare_request is None
        or records.records is None
        or records.binding is None
        or p.environment is None
        or p.environment_ref is None
        or records.spec is None
        or records.spec_ref is None
    ):
        raise OwnershipConflict(
            "Source observation requires actual original preparation/environment"
        )
    control = records.controls.bind(p.prepare_request.operation)
    public = records.reads.parse(
        records.binding.public_task_ref,
        "public-task/1",
        PublicTask,
        control,
        visibility="public",
    )
    site = records.site.site
    declared = declaration(records, public)
    initialization = declared.initialization
    configuration = BrowserWorkerConfiguration(
        spec=BrowserSessionSpec(
            scope=owner.scope,
            task=public,
            chromium_executable=assets.chromium_executable,
            seed=assets.seed,
            action_timeout_ms=assets.action_timeout_ms,
            requirements=assets.requirements,
            max_events=assets.max_events,
        ),
        initialization=initialization,
        installation=native.spec.configuration.installation,
        playwright_browsers_path=assets.playwright_browsers_path,
        library_directories=assets.library_directories,
    )
    slurm = native.spec.slurm
    spec = BrowserResourceSpec(
        token=token,
        configuration=configuration,
        slurm=BrowserSlurmBinding(
            execution=slurm.execution,
            parent=slurm.parent,
            srun_executable=slurm.srun_executable,
            scontrol_executable=slurm.scontrol_executable,
        ),
    )
    op = native.acquisition.model_copy(
        update={
            "operation_id": records.prefix + ".browser",
            "attempt_id": owner.scope.attempt_id,
            "allocation_id": token.allocation_id,
            "recovery_ref": token.recovery_ref,
            "deadline": min(
                native.acquisition.deadline,
                records.clock.utcnow() + timedelta(seconds=operation_seconds),
            ),
        }
    )
    prepared = PreparedBrowserBinding(
        p.publication,
        native.spec,
        site,
        native.acquisition,
        evidence=owner.evidence,
        preparations=records.records,
        journal=native.journal,
        task_checks=declared.prepared_checks,
        inputs=records.input_bodies,
    )
    b = RetainedBrowserResource(
        spec,
        op,
        journal=native.journal,
        evidence=owner.evidence,
        controls=records.controls,
        clock=records.clock,
        cleanup_seconds=recovery_seconds(
            records.recovery_budgets, "browser_close_seconds", operation_seconds
        ),
        authority=PreparedBrowserAuthority(
            spec, prepared, SourceQualificationBrowserAuthority(owner, spec, op)
        ),
    )
    p.browser = b
    spec_ref = records.put(spec, p.prepare_request.operation)
    p.phase = "initializing"
    session = b.open(records.controls.bind(op))
    if (
        session.resource_started_ref is None
        or session.observation_ref is None
        or not isinstance(session.engine, SupervisedBrowserSession)
    ):
        raise OwnershipConflict("Source observation lacks original guarded seq0 return")
    p.initial = InitialObservationSelection(
        preparation=p.publication,
        browser_spec_ref=spec_ref,
        browser_acquired_ref=session.resource_started_ref,
    )

    def checks() -> InitialObservationChecks:
        if p.capture_intent_ref is None or p.capture_result_ref is None:
            raise OwnershipConflict(
                "Source initial passive measurement is not available"
            )
        return declared.initial_checks(p.capture_intent_ref, p.capture_result_ref)

    authority = SourceQualificationObservationAuthority(
        native,
        b,
        lambda: p.capture_request,
        lambda: p.initial,
        checks,
        collector=declared.collector,
    )
    p.capture_request = BrowserCaptureRequest(
        scope=owner.scope,
        operation=op.model_copy(
            update={"operation_id": records.prefix + ".initial-capture"}
        ),
        observation_sha256=session.observation_ref.sha256,
        collector_id=declared.collector[0],
        collector_version=declared.collector[1],
    )
    capture = RecordedBrowserCapture(session.engine, owner.evidence, authority)
    result_ref = capture.capture(
        p.capture_request, control=records.controls.bind(p.capture_request.operation)
    )
    if capture.intent_ref is None:
        raise OwnershipConflict(
            "Source initial capture has no original persisted intent"
        )
    p.references.extend((capture.intent_ref, result_ref))
    p.capture_intent_ref, p.capture_result_ref = capture.intent_ref, result_ref
    initial_records = EvidenceInitialObservations(
        owner.evidence,
        records.controls,
        records.records,
        checks(),
        authority,
    )
    initial_op = records.task_operation("initial-checks")
    measured = initial_records.publish_complete(p.initial, initial_op)
    initial_ref, initial = measured.reference, measured.value
    p.references.append(initial_ref)
    baseline_op = records.task_operation("baseline")
    actual, preparation = measured.inputs, measured.preparation
    p.baseline_inputs = BaselineInputs(
        binding=records.binding,
        public_task=public,
        spec=records.spec,
        spec_ref=records.spec_ref,
        environment=p.environment,
        environment_ref=p.environment_ref,
        preparation=preparation,
        preparation_ref=p.publication.preparation_ref,
        prepared=actual.prepared,
        prepared_ref=p.publication.prepared_ref,
        observation=actual.observation.record,
        observation_ref=session.observation_ref,
        initial=initial,
        initial_ref=initial_ref,
    )
    p.baseline = assemble_baseline(p.baseline_inputs, baseline_op)
    if p.baseline.status != "ready":
        raise OwnershipConflict("Actual source initial state is not qualified ready")
    p.phase = "observed"
