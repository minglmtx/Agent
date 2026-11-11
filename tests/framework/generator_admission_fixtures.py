"""Actual CAS/claims/journals; model output and live authority are unit fixtures."""

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.run_journal import FileRunJournal
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.adapters.plans.construction_evidence import ConstructionEvidence
from lab_generate_skill.adapters.plans.evidence import EvidenceRunPlans
from lab_generate_skill.adapters.plans.generator_admission import (
    EvidenceGeneratorCallInputs,
)
from lab_generate_skill.adapters.plans.retrieval_evidence import (
    EvidenceRetrievalRecords,
)
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.application.generator_admission import (
    ConstructionGeneratorAuthority,
    GeneratorAdmissionDeps,
)
from lab_generate_skill.domain.construction import (
    CallPlanned,
    CallCompleted,
    ProgressEvent,
)
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.construction_state import ConstructionProgress
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generator_model import (
    GeneratorModelRequest,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBaseParameters,
    LocalGeneratorParameters,
    LocalGeneratorBinding,
    LocalGeneratorIntent,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.generator.candidates import RecordedGenerator
from lab_generate_skill.generator.prompting import prepare_generator
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
import construction_storage_fixtures as storage
from local_generator_fixtures import UnitAuthority, UnitEngine
from test_evidence_run_plans import persisted_plan
from test_run_journal import Harness, CancelSwitch, command


class UnitActualParameterAuthority(storage.UnitConstructionAuthority):
    def verify_event(
        self, progress: ConstructionProgress, event: ProgressEvent, op: OperationContext
    ) -> None:
        if self.denied:
            raise OwnershipConflict("Unit construction denied")
        if isinstance(event, CallPlanned):
            parameters = LocalGeneratorParameters.model_validate_json(
                self.store.read(event.call.parameters_ref)
            )
            if (parameters.seed, parameters.temperature) != (
                event.call.seed,
                event.call.temperature,
            ):
                raise OwnershipConflict("Unit sampling mismatch")
        elif isinstance(event, CallCompleted):
            response = GeneratorTextCompletion.model_validate_json(
                self.store.read(event.response.response_ref)
            )
            if response.request_id != event.response.request_id:
                raise OwnershipConflict("Unit completion mismatch")
        else:
            super().verify_event(progress, event, op)


class UnitExecutionAuthority(UnitAuthority):
    def __init__(self) -> None:
        super().__init__()
        self.callback: Callable[[], None] | None = None

    def authorize_generate(
        self,
        intent: LocalGeneratorIntent,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        super().authorize_generate(intent, request, parameters, control)
        if self.callback is not None:
            self.callback()


@dataclass
class Case:
    data: storage.StorageFixture
    authority: ConstructionGeneratorAuthority
    deps: GeneratorAdmissionDeps
    execution: UnitExecutionAuthority
    local: DurableGeneratorInference
    role: RecordedGenerator
    inputs: EvidenceGeneratorCallInputs
    generation: GenerationInput
    request: GeneratorModelRequest
    parameters: LocalGeneratorParameters
    binding: LocalGeneratorBinding
    event: CallPlanned
    engine: UnitEngine
    operation: OperationContext
    controls: OperationGuards
    harness: Harness
    cancel: CancelSwitch
    root: Path

    def stop(self) -> None:
        snapshot = self.harness.journal.read(command())
        entry = self.harness.run_entry(snapshot, "closing", "cancelled")
        self.harness.journal.append(entry, snapshot.revision, entry.event.operation)

    def assert_no_inference(self) -> None:
        assert self.engine.calls == self.engine.validations == 0
        assert not list(self.root.glob("*.local-generator.json"))
        assert not list(self.root.glob("*.pending-*"))


def case(root: Path, *, planned: bool = True) -> Case:
    base = LocalGeneratorBaseParameters(
        max_input_tokens=10000, max_new_tokens=100, top_p=0.95, enable_thinking=False
    )
    original = persisted_plan

    def with_parameters(store: FileEvidenceStore) -> RunPlan:
        run = original(store)
        model_ref = store.put(
            b"unit model provenance", local_metadata("model-binding/1")
        )
        base_ref = store.put(
            base.model_dump_json().encode(), local_metadata("model-parameters/1")
        )
        models = tuple(
            (
                m.model_copy(
                    update={"model_binding_ref": model_ref, "parameters_ref": base_ref}
                )
                if m.role == "generator"
                else m
            )
            for m in run.models
        )
        return RunPlan.model_validate(run.model_copy(update={"models": models}))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(storage, "persisted_plan", with_parameters)
        data = storage.fixture(root, allowed_actions=("click", "send_msg_to_user"))
    data.authority = UnitActualParameterAuthority(data.store)
    cancel = CancelSwitch()
    controls = OperationGuards(SystemClock(), cancel)
    plans = EvidenceRunPlans(data.store, controls)
    run = plans.load(data.plan.run, command())
    journal = data.journal()
    progress = journal.create(data.plan, command())
    event = data.event(progress)
    assert isinstance(event, CallPlanned)
    generation = GenerationInput.model_validate_json(
        data.store.read(event.call.input_ref)
    )
    parameters = LocalGeneratorParameters.model_validate(
        {
            **base.model_dump(),
            "schema_version": "local-generator-parameters/1",
            "seed": generation.seed,
            "temperature": generation.temperature,
        }
    )
    parameters_ref = data.store.put(
        parameters.model_dump_json().encode(), local_metadata("model-parameters/1")
    )
    event = event.model_copy(
        update={
            "call": event.call.model_copy(update={"parameters_ref": parameters_ref})
        }
    )
    if planned:
        journal.append(event, progress.revision, event.operation)
    run_root = root / "run-journal"
    run_root.mkdir()
    runs = FileRunJournal(
        run_root, data.plan.run, controls, data.store, capacity=run.run_capacity
    )
    harness = Harness(
        run_root,
        data.store,
        runs,
        data.plan.run,
        data.plan.claim_ref,
        cancel,
        run.run_capacity,
    )
    harness.running()
    observations = EvidenceObservations(data.store, controls)
    construction = ConstructionEvidence(
        data.store,
        plans,
        data.authority,
        EvidenceContextRecords(data.store, controls, data.context_authority),
        EvidenceRetrievalRecords(data.store, controls, data.retrieval_authority),
        data.claims(),
    )
    inputs = EvidenceGeneratorCallInputs(construction, observations, prepare_generator)
    execution = UnitExecutionAuthority()
    deps = GeneratorAdmissionDeps(journal, runs, inputs, execution)
    authority = ConstructionGeneratorAuthority(data.plan.run, deps)
    binding = LocalGeneratorBinding(
        owner=data.plan.run.owner,
        source_task_id=data.plan.task.identity.source_task_id,
        release_ref=data.plan.run.release_ref,
        model_binding_ref=event.call.model_binding_ref,
        base_parameters_ref=event.call.base_parameters_ref,
    )
    inference_root = root / "inference"
    inference_root.mkdir()
    engine = UnitEngine()
    local = DurableGeneratorInference(
        inference_root, binding, engine, data.store, controls, authority
    )
    operation = command("actual-inference")
    request = prepare_generator(
        generation,
        observations.load(generation.context.initial_observation_ref, operation),
    )
    role = RecordedGenerator(observations, local, data.store, controls)
    return Case(
        data,
        authority,
        deps,
        execution,
        local,
        role,
        inputs,
        generation,
        request,
        parameters,
        binding,
        event,
        engine,
        operation,
        controls,
        harness,
        cancel,
        inference_root,
    )
