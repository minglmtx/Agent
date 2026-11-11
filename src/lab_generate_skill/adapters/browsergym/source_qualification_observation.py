"""One actual source initial capture/check on the original live browser.

No trace, Actor, source claim or predicted observation is needed. The original
registered browser supplies the one seq0 return and original worker/acquisition.
"""

import hashlib
from lab_generate_skill.policies.evidence_bytes import require_complete_bytes
from collections.abc import Callable
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.worker_client import (
    SupervisedBrowserSession,
)
from lab_generate_skill.adapters.browsergym.resource_records import phase, encode
from lab_generate_skill.adapters.plans.state_reads import StateReads
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.adapters.sites.source_qualification_native import (
    SourceQualificationNativeAuthority,
)
from lab_generate_skill.domain.browser_capture import (
    BrowserCaptureRequest,
    BrowserCaptureIntent,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import (
    InitialObservationInputs,
    InitialObservationSelection,
    BrowserAcquiredFact,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.ports.initial_observation import InitialObservationChecks
from lab_generate_skill.ports.lifecycle import OperationControl


class SourceQualificationObservationAuthority:
    def __init__(
        self,
        native: SourceQualificationNativeAuthority,
        browser: RetainedBrowserResource,
        capture: Callable[[], BrowserCaptureRequest | None],
        initial: Callable[[], InitialObservationSelection | None],
        checks: Callable[[], InitialObservationChecks],
        *,
        collector: tuple[str, str],
    ) -> None:
        if (
            not isinstance(native, SourceQualificationNativeAuthority)
            or not isinstance(browser, RetainedBrowserResource)
            or any(not callable(f) for f in (capture, initial, checks))
        ):
            raise TypeError(
                "Original source/browser and passive measurement producers required"
            )
        self.native, self.browser = native, browser
        self.collector = TypeAdapter(tuple[Identifier, Identifier]).validate_python(
            collector, strict=True
        )
        self.capture, self.initial, self.checks = capture, initial, checks
        self.reads = StateReads(native.owner.evidence)
        self.capture_attempted = False
        if (
            browser.spec.configuration.spec.scope != native.owner.scope
            or browser.spec.slurm.execution != native.spec.slurm.execution
            or browser.spec.slurm.parent != native.spec.slurm.parent
        ):
            raise OwnershipConflict(
                "Source observation changed original browser/task/controller"
            )

    def _live(
        self,
        operation: OperationContext,
        control: OperationControl,
        inputs: InitialObservationInputs | None = None,
    ) -> tuple[BrowserAcquiredFact, Observation]:
        self.native.owner.require(operation, control, new_work=True)
        self.native.require_acquired(operation, control)
        b = self.browser
        if b.phase != "open":
            raise OwnershipConflict("Original source observation browser is not open")
        session = b.session
        engine = session.engine
        if (
            not isinstance(engine, SupervisedBrowserSession)
            or engine.configuration_reply is None
            or engine.last_readout is None
            or session.resource_started_ref is None
            or session.observation_ref is None
        ):
            raise OwnershipConflict(
                "Source observation requires original guarded initialized browser"
            )
        read = b.operation.model_copy(
            update={
                "operation_id": operation.operation_id + ".source-initial-browser-read",
                "mode": "cleanup",
                "parent_operation_id": b.operation.operation_id,
                "deadline": operation.deadline,
                "cancellation_ref": None,
            }
        )
        record = b.journal.read(b.spec.token, read)
        if (
            record.token != b.spec.token
            or record.state != "acquired"
            or len(record.events) != 3
            or len(record.events[2].evidence) != 1
        ):
            raise OwnershipConflict(
                "Source initial observation changed original browser acquisition"
            )
        if inputs is not None and self.native.current_evidence is not None:
            # Exact bodies from this same complete read, plus the live owner,
            # site/browser journals and storage check above. This is content
            # delivery, not delegation of the original physical authority.
            worker, acquired, observation = (
                inputs.worker_acquired,
                inputs.acquired,
                inputs.observation.record,
            )
            for reference, raw in (
                (record.events[2].evidence[0], worker.model_dump_json().encode()),
                (
                    session.resource_started_ref,
                    encode(acquired.model_dump(mode="json")),
                ),
                (session.observation_ref, observation.model_dump_json().encode()),
            ):
                require_complete_bytes(reference, raw)
            worker.check_spec(b.spec)
        else:
            worker = self.reads.parse(
                record.events[2].evidence[0],
                "browser-worker-acquired/1",
                BrowserWorkerAcquiredFact,
                control,
            )
            worker.check_spec(b.spec)
            acquired = self.reads.parse(
                session.resource_started_ref,
                "browser-resource-fact/1",
                BrowserAcquiredFact,
                control,
            )
            observation = self.reads.parse(
                session.observation_ref,
                "observation/1",
                Observation,
                control,
                visibility="public",
            )
        started = acquired.details.started
        if (
            acquired.token != b.spec.token
            or worker.operation != phase(b.operation, "worker-acquired")
            or acquired.operation != phase(b.operation, "acquired")
            or acquired.spec_sha256 != worker.spec_sha256
            or acquired.details.worker_acquired_ref != record.events[2].evidence[0]
            or started.initial_observation_ref != session.observation_ref
            or started.owner_guard != engine.configuration_reply.owner_guard
            or started.owner_guard.controller != self.native.owner.controller.writer
            or started.owner_guard != worker.details.prepared.owner_guard
            or started.step != worker.details.prepared.step
            or started.installed_sources != worker.details.prepared.installed_sources
            or observation.sequence != 0
            or observation.state != "ready"
            or observation.last_action_error
            or observation != engine.last_readout.observation
            or observe_process_cgroup(
                b.spec.slurm.execution, started.owner_guard.worker, control
            ).membership
            != started.step.controller.target.worker
        ):
            raise OwnershipConflict(
                "Source initial observation differs from original seq0/physical worker"
            )
        return acquired, observation

    def verify_capture(
        self,
        configuration: BrowserWorkerConfiguration,
        request: BrowserCaptureRequest,
        intent_ref: EvidenceRef,
        control: OperationControl,
    ) -> None:
        request = BrowserCaptureRequest.model_validate(request)
        self._live(request.operation, control)
        b = self.browser
        b.spec.check_operation(request.operation, "execute")
        if self.capture_attempted:
            raise DispatchAlreadyCommitted("Source initial capture already attempted")
        intent = self.reads.parse(
            intent_ref, "browser-capture-intent/1", BrowserCaptureIntent, control
        )
        if (
            configuration != b.spec.configuration
            or request != self.capture()
            or request.scope != self.native.owner.scope
            or b.session.observation_ref is None
            or request.observation_sha256 != b.session.observation_ref.sha256
            or (request.collector_id, request.collector_version) != self.collector
            or intent_ref.producer != "browser-capture-v1"
            or intent.request != request
            or intent.configuration_sha256
            != hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Source initial capture changed original persisted request/collector"
            )
        self.capture_attempted = True

    def verify(
        self,
        inputs: InitialObservationInputs,
        checks: StateChecks,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        inputs = InitialObservationInputs.model_validate(inputs)
        acquired, observation = self._live(operation, control, inputs)
        if (
            not self.capture_attempted
            or inputs.selection != self.initial()
            or inputs.browser != self.browser.spec
            or inputs.acquired != acquired
            or inputs.observation.record != observation
            or checks != self.checks().check(inputs, control)
        ):
            raise OwnershipConflict(
                "Source initial checks changed original complete measured inputs"
            )
