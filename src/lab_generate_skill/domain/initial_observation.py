"""Select original browser acquisition evidence for existing initial-state checks."""

import hashlib
from typing import Literal, Self
from pydantic import model_validator
from .validation import Contract, Sha256
from .evidence import EvidenceRef
from .preparation_record import PreparedPublication
from .preparation import PreparedTask
from .browser_resource import BrowserResourceSpec, BrowserResourceStarted
from .browser_session import BrowserReadout
from .lifecycle import AllocationToken, OperationContext
from .state_checks import InitialStateSpec
from .state_scope import private_state_ref
from .observation import ResolvedObservation
from .errors import OwnershipConflict
from .browser_worker_acquisition import BrowserWorkerAcquiredFact


class InitialObservationSelection(Contract):
    schema_version: Literal["initial-observation-selection/2"] = (
        "initial-observation-selection/2"
    )
    preparation: PreparedPublication
    browser_spec_ref: EvidenceRef
    browser_acquired_ref: EvidenceRef

    @model_validator(mode="after")
    def refs(self) -> Self:
        for ref, schema in (
            (self.browser_spec_ref, "browser-resource-spec/4"),
            (self.browser_acquired_ref, "browser-resource-fact/1"),
        ):
            private_state_ref(ref, schema)
            if ref.media_type != "application/json":
                raise ValueError("Initial observation requires JSON resource facts")
        return self


class BrowserAcquiredDetails(Contract):
    started: BrowserResourceStarted
    worker_acquired_ref: EvidenceRef

    @model_validator(mode="after")
    def worker_reference(self) -> Self:
        private_state_ref(self.worker_acquired_ref, "browser-worker-acquired/1")
        return self


class BrowserAcquiredFact(Contract):
    """Strict view of the existing acquired fact, not a new resource event."""

    schema_version: Literal["browser-resource-fact/1"] = "browser-resource-fact/1"
    spec_sha256: Sha256
    token: AllocationToken
    operation: OperationContext
    state: Literal["acquired"]
    details: BrowserAcquiredDetails


class InitialObservationInputs(Contract):
    selection: InitialObservationSelection
    prepared: PreparedTask
    spec: InitialStateSpec
    browser: BrowserResourceSpec
    acquired: BrowserAcquiredFact
    worker_acquired: BrowserWorkerAcquiredFact
    returned: BrowserReadout
    observation: ResolvedObservation

    @model_validator(mode="after")
    def originals(self) -> Self:
        p, b, a, r = self.prepared, self.browser, self.acquired, self.returned
        started = a.details.started
        worker = self.worker_acquired
        worker.check_spec(b)
        raw_worker = worker.model_dump_json().encode()
        ref = a.details.worker_acquired_ref
        if (ref.sha256, ref.size_bytes) != (
            hashlib.sha256(raw_worker).hexdigest(),
            len(raw_worker),
        ):
            raise OwnershipConflict(
                "Initial return changed exact original worker reference"
            )
        prepared = worker.details.prepared
        if (
            (started.owner_guard, started.step, started.installed_sources)
            != (prepared.owner_guard, prepared.step, prepared.installed_sources)
            or worker.operation.parent_operation_id != r.operation.operation_id
            or worker.operation.operation_id
            in (a.operation.operation_id, r.operation.operation_id)
        ):
            raise OwnershipConflict(
                "Initial return lost original pre-navigation worker"
            )
        if (
            b.configuration.spec.scope != p.scope
            or b.configuration.spec.task != p.public_task
            or self.spec.task != p.scope.task
            or a.token != b.token
            or r.scope != p.scope
            or r.observation != self.observation.record
            or r.schema_version != "browser-initial-return/1"
            or r.action is not None
            or r.observation.sequence != 0
        ):
            raise OwnershipConflict(
                "Initial observation changed original preparation/browser return"
            )
        b.check_operation(r.operation, "execute")
        b.check_operation(a.operation, "execute")
        if (
            a.operation.parent_operation_id != r.operation.operation_id
            or a.operation.operation_id == r.operation.operation_id
            or started.initial_return_ref.content_schema != "browser-initial-return/1"
        ):
            raise OwnershipConflict(
                "Browser acquisition does not follow its initial return"
            )
        return self
