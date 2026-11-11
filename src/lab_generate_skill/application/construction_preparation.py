"""Prepare the original local Generator step without registering or invoking it."""

from dataclasses import dataclass
from typing import Any
from lab_generate_skill.domain.construction import CallPlanned, ConstructionCall
from lab_generate_skill.domain.construction_control import (
    ConstructionStepPlan,
    GenerateConstructionWork,
)
from lab_generate_skill.domain.construction_inputs import GenerationInput
from lab_generate_skill.domain.construction_preparation import (
    GeneratorPreparation,
    ConstructionGenerationSource,
    PublishedConstructionStep,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    generator_evidence_metadata,
)
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    RevisionConflict,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.generator_admission import ConstructionGeneratorInputs
from .construct_targets import ConstructionDeps, verify_ready_construction
from .context_evidence import publish_raw


@dataclass(frozen=True)
class GenerationPreparationDeps:
    construction: ConstructionDeps
    evidence: EvidenceStore
    inputs: ConstructionGeneratorInputs

    def __post_init__(self) -> None:
        if (
            not isinstance(self.construction, ConstructionDeps)
            or self.evidence is None
            or not callable(getattr(self.inputs, "prepare", None))
        ):
            raise ValueError(
                "Original construction/CAS/input-reader dependencies required"
            )


class GenerationPreparationUnconfirmed(RuntimeError):
    def __init__(
        self,
        request: GeneratorPreparation,
        phase: str,
        primary: BaseException,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.request, self.phase, self.primary, self.retained = (
            request,
            phase,
            primary,
            retained,
        )
        super().__init__(
            "Generator preparation unresolved; inspect retained exact refs, never infer dispatch"
        )


def prepare_generator_step(
    request: GeneratorPreparation, deps: GenerationPreparationDeps
) -> PublishedConstructionStep:
    request = GeneratorPreparation.model_validate(request)
    retained: list[EvidenceRef] = []
    phase = "admission"
    try:
        d = deps.construction
        control = d.controls.bind(request.operation)
        control.checkpoint()
        progress = d.journal.read(request.operation)
        if progress.plan.run != request.run:
            raise OwnershipConflict("Preparation differs from original run")
        if progress.revision != request.expected_revision:
            raise RevisionConflict("Preparation requires exact current history")
        action = progress.project().next_action
        if (
            action.kind != "generate"
            or action.candidate_slot is None
            or action.resample_index is None
        ):
            raise InvalidTransition(
                "Only original ready Generator work may be prepared; pending/unknown never renew"
            )
        if any(
            isinstance(e, CallPlanned) and e.call.request_id == request.request_id
            for e in progress.events
        ):
            raise OwnershipConflict(
                "Registered original request ID cannot be prepared again"
            )
        verify_ready_construction(progress, d, request.operation, control)
        phase = "original_public_inputs"
        source = ConstructionGenerationSource.model_validate(
            deps.inputs.prepare(progress.plan, request.operation, control)
        )
        model = next(m for m in progress.plan.models if m.role == "generator")
        if model.paid or source.context.task.identity != progress.plan.task.identity:
            raise OwnershipConflict("Original local Generator/public source required")
        seed, temperature = progress.plan.method.generator_sampling(
            action.candidate_slot, action.resample_index
        )
        if (progress.plan.actor_context_configuration_ref is None) != (
            source.actor_capabilities is None
        ):
            raise OwnershipConflict(
                "Prepared Generator source lost selected Actor capabilities"
            )
        selected: dict[str, Any] = (
            {}
            if source.actor_capabilities is None
            else dict(
                schema_version="generation-input/2",
                actor_capabilities=source.actor_capabilities,
            )
        )
        public = GenerationInput(
            **selected,
            request_id=request.request_id,
            context=source.context,
            retrieved_skills=source.skills,
            candidate_index=action.candidate_slot,
            resample_index=action.resample_index,
            seed=seed,
            temperature=temperature,
        )
        parameters = LocalGeneratorParameters.model_validate(
            {
                **source.base.model_dump(),
                "schema_version": "local-generator-parameters/1",
                "seed": seed,
                "temperature": temperature,
            }
        )
        input_raw, parameters_raw = (
            public.model_dump_json().encode(),
            parameters.model_dump_json().encode(),
        )
        if len(input_raw) > 4 * 1024**2:
            raise ValueError(
                "Complete Generator input exceeds original command byte bound"
            )

        def metadata(schema: str, visibility: str = "private") -> EvidenceMetadata:
            return EvidenceMetadata.model_validate(
                dict(
                    media_type="application/json",
                    content_schema=schema,
                    visibility=visibility,
                    producer="construction-generation-preparation-v1",
                )
            )

        input_meta, parameters_meta = metadata(
            public.schema_version, "public"
        ), generator_evidence_metadata("model-parameters/1")
        input_ref, parameters_ref = evidence_reference(
            input_raw, input_meta
        ), evidence_reference(parameters_raw, parameters_meta)
        step = ConstructionStepPlan(
            run=request.run,
            expected_revision=progress.revision,
            operation=request.operation,
            work=GenerateConstructionWork(
                planned=CallPlanned(
                    operation=request.operation,
                    call=ConstructionCall(
                        schema_version=(
                            "construction-call/2"
                            if source.actor_capabilities is not None
                            else "construction-call/1"
                        ),
                        request_id=request.request_id,
                        role="generator",
                        candidate_slot=action.candidate_slot,
                        resample_index=action.resample_index,
                        seed=seed,
                        temperature=temperature,
                        model_binding_ref=model.model_binding_ref,
                        base_parameters_ref=model.parameters_ref,
                        input_ref=input_ref,
                        parameters_ref=parameters_ref,
                    ),
                ),
                request=public,
                invoke_operation=request.invoke_operation,
                completion_operation=request.completion_operation,
            ),
        )
        step_raw = step.model_dump_json().encode()
        # All typed scope/sampling/byte checks occur before the first publication.
        verify_ready_construction(progress, d, request.operation, control)
        for phase, raw, meta in [
            ("publish_input", input_raw, input_meta),
            ("publish_parameters", parameters_raw, parameters_meta),
        ]:
            publish_raw(deps.evidence, raw, meta, retained, control)
        phase = "publish_step"
        ref = publish_raw(
            deps.evidence,
            step_raw,
            metadata("construction-step-plan/1"),
            retained,
            control,
        )
        verify_ready_construction(progress, d, request.operation, control)
        return PublishedConstructionStep(reference=ref, step=step)
    except BaseException as error:
        raise GenerationPreparationUnconfirmed(
            request, phase, error, tuple(retained)
        ) from error
