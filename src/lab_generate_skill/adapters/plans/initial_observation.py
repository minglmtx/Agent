"""Read initial evidence once through existing typed preparation/observation readers."""

import hashlib
from dataclasses import dataclass
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
    BrowserAcquiredFact,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.preparation_records import (
    PreparationRecords,
    PreparationReceiptReads,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .state_reads import StateReads
from .observations import ObservationReader
from .prepared_browser import read_operation


@dataclass(frozen=True)
class LoadedInitialObservation:
    inputs: InitialObservationInputs
    preparation: PreparationReceipt | None


class InitialObservationReader:
    def __init__(self, store: EvidenceReader, preparations: PreparationRecords) -> None:
        self.reads, self.observations = StateReads(store), ObservationReader(store)
        self.preparations = preparations

    def load(
        self,
        selection: InitialObservationSelection,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialObservationInputs:
        return self.load_complete(selection, operation, control).inputs

    def load_complete(
        self,
        selection: InitialObservationSelection,
        operation: OperationContext,
        control: OperationControl,
    ) -> LoadedInitialObservation:
        selection = InitialObservationSelection.model_validate(selection)
        read = self.reads.parse
        request = read(
            selection.preparation.selection.request_ref,
            "site-task-request/2",
            SiteTaskRequest,
            control,
        )
        if (operation.run_id, operation.owner_id, operation.attempt_id) != (
            request.operation.run_id,
            request.operation.owner_id,
            request.operation.attempt_id,
        ):
            raise OwnershipConflict(
                "Initial-check reader changed original preparation ownership"
            )
        preparation = None
        preparation_inputs = None
        prepare_op = read_operation(request.operation, operation)
        if isinstance(self.preparations, PreparationReceiptReads):
            loaded = self.preparations.load_with_receipt(
                selection.preparation, prepare_op
            )
            prepared, preparation = loaded.prepared, loaded.receipt
            preparation_inputs = loaded.inputs
        else:
            prepared = self.preparations.load(selection.preparation, prepare_op)
        if preparation_inputs is not None:
            if prepared.spec_ref != preparation_inputs.binding.baseline_ref:
                raise OwnershipConflict(
                    "Preparation changed complete baseline reference"
                )
            spec = preparation_inputs.spec
        else:
            spec = read(
                prepared.spec_ref, "initial-state-spec/1", InitialStateSpec, control
            )
        browser = read(
            selection.browser_spec_ref,
            "browser-resource-spec/4",
            BrowserResourceSpec,
            control,
        )
        acquired = read(
            selection.browser_acquired_ref,
            "browser-resource-fact/1",
            BrowserAcquiredFact,
            control,
        )
        if (
            acquired.spec_sha256
            != hashlib.sha256(browser.model_dump_json().encode()).hexdigest()
        ):
            raise OwnershipConflict(
                "Initial browser fact changed original specification"
            )
        started = acquired.details.started
        worker = read(
            acquired.details.worker_acquired_ref,
            "browser-worker-acquired/1",
            BrowserWorkerAcquiredFact,
            control,
        )
        returned = read(
            started.initial_return_ref,
            "browser-initial-return/1",
            BrowserReadout,
            control,
        )
        observation = self.observations.load(started.initial_observation_ref, control)
        inputs = InitialObservationInputs(
            selection=selection,
            prepared=prepared,
            spec=spec,
            browser=browser,
            acquired=acquired,
            worker_acquired=worker,
            returned=returned,
            observation=observation,
        )
        self.reads.dependencies((started, worker), control)
        control.checkpoint()
        return LoadedInitialObservation(inputs, preparation)
