"""Actual public observations/CAS with a unit inference recorder, no model calls."""

from dataclasses import dataclass
from pathlib import Path
import json
from lab_generate_skill.adapters.clock import SystemClock
from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.adapters.storage.observations import EvidenceObservations
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.generator_model import (
    GeneratorModelRequest,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.generator.candidates import RecordedGenerator
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_commands import Cancel
from test_construction_inputs import generation_input
from test_construction_state import skill
from observation_fixtures import sample_observation


def put(
    store: FileEvidenceStore, raw: bytes, schema: str, public: bool = False
) -> EvidenceRef:
    return store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="public" if public else "private",
            producer="unit-generator",
        ),
    )


class UnitInference:
    def __init__(self, store: FileEvidenceStore) -> None:
        self.store = store
        self.calls = 0
        self.executions = 0
        self.saved: tuple[GeneratorModelRequest, EvidenceRef] | None = None
        self.text = json.dumps(skill("output").model_payload())
        self.finish = "stop"
        self.mismatch = ""

    def generate(
        self, request: GeneratorModelRequest, op: OperationContext
    ) -> EvidenceRef:
        self.calls += 1
        if self.saved is not None:
            if self.saved[0] != request:
                raise OwnershipConflict("unit request changed")
            return self.saved[1]
        self.executions += 1
        parameters = put(
            self.store,
            json.dumps(
                {
                    "seed": request.seed + (1 if self.mismatch == "seed" else 0),
                    "temperature": request.temperature
                    + (0.1 if self.mismatch == "temperature" else 0),
                    "max_new_tokens": 1024,
                }
            ).encode(),
            "model-parameters/1",
        )
        completion = GeneratorTextCompletion(
            request_id="other" if self.mismatch == "request" else request.request_id,
            generation_input_sha256=(
                "f" * 64
                if self.mismatch == "source_digest"
                else request.generation_input_sha256
            ),
            model_input_sha256=(
                "f" * 64
                if self.mismatch == "wire_digest"
                else request.model_input_sha256
            ),
            parameters_ref=parameters,
            text=self.text,
            finish_reason=self.finish,
        )
        response = put(
            self.store,
            completion.model_dump_json().encode(),
            "generator-model-response/1",
        )
        self.saved = (request, response)
        return response


@dataclass
class Fixture:
    request: GenerationInput
    evidence: FileEvidenceStore
    inference: UnitInference
    observations: EvidenceObservations
    controls: OperationGuards
    generator: RecordedGenerator


def fixture(root: Path) -> Fixture:
    store = FileEvidenceStore(root)
    request = generation_input()
    observation = sample_observation(
        request.context.task.identity, request.context.context_id
    )
    reference = put(
        store, observation.model_dump_json().encode(), "observation/1", True
    )
    request = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"initial_observation_ref": reference}
            )
        }
    )
    controls = OperationGuards(SystemClock(), Cancel())
    observations = EvidenceObservations(store, controls)
    inference = UnitInference(store)
    return Fixture(
        request,
        store,
        inference,
        observations,
        controls,
        RecordedGenerator(observations, inference, store, controls),
    )
