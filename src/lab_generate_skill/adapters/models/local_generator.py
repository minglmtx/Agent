"""Durable GeneratorInference with no replay after an uncertain first intent.

One trusted root across callers, keyed by original run/source/request. The stable
lock covers intent, one engine invocation and completion publication. Native I/O
and inference still need external supervision; a dead writer's unlocked intent
never grants permission to infer again. Cleanup only commits original facts.
"""

from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OwnershipConflict,
)
from lab_generate_skill.domain.generator_model import (
    GeneratorModelRequest,
    GeneratorTextCompletion,
)
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorBinding,
    LocalGeneratorIntent,
    LocalGeneratorSnapshot,
    LocalGeneratorOutput,
    LocalGeneratorFact,
    GeneratorExecutionObservation,
)
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.local_generator import (
    GeneratorInvocationEngine,
    LocalGeneratorAuthority,
)
from .local_generator_evidence import LocalGeneratorEvidence, local_metadata
from .local_generator_state import invocation_file, load_invocation, require_intent


class DurableGeneratorInference:
    def __init__(
        self,
        root: Path,
        binding: LocalGeneratorBinding,
        engine: GeneratorInvocationEngine,
        evidence: EvidenceStore,
        controls: OperationControls,
        authority: LocalGeneratorAuthority,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("Local inference root must be trusted and absolute")
        self._root = root
        self._binding = LocalGeneratorBinding.model_validate(binding)
        self._engine, self._controls, self._authority = engine, controls, authority
        self._evidence = LocalGeneratorEvidence(evidence)

    def _access(self, op: OperationContext) -> OperationControl:
        if (
            (op.run_id, op.owner_id)
            != (self._binding.owner.run_id, self._binding.owner.owner_id)
            or op.attempt_id is not None
            or op.allocation_id is not None
            or op.recovery_ref is not None
        ):
            raise OwnershipConflict(
                "Local inference operation differs from its original owner"
            )
        control = self._controls.bind(op)
        control.checkpoint()
        self._authority.authorize_access(self._binding, op, control)
        control.checkpoint()
        if self._root.resolve(strict=True) != self._root or not self._root.is_dir():
            raise EvidenceIntegrityError("Local inference root must be canonical")
        return control

    def _intent(
        self,
        request: GeneratorModelRequest,
        op: OperationContext,
        parameters_ref: EvidenceRef,
    ) -> LocalGeneratorIntent:
        return LocalGeneratorIntent(
            binding=self._binding,
            request_id=request.request_id,
            request_ref=evidence_reference(
                request.model_dump_json().encode(),
                local_metadata("generator-model-request/1"),
            ),
            parameters_ref=parameters_ref,
            operation=op,
        )

    def generate(
        self, request: GeneratorModelRequest, op: OperationContext
    ) -> EvidenceRef:
        request, op = GeneratorModelRequest.model_validate(
            request
        ), OperationContext.model_validate(op)
        if op.mode != "execute" or op.parent_operation_id is not None:
            raise OwnershipConflict("Cleanup cannot start local inference")
        control = self._access(op)
        parameters = self._evidence.parameters(self._binding, request, control)
        intent = self._intent(
            request,
            op,
            evidence_reference(
                parameters.model_dump_json().encode(),
                local_metadata("model-parameters/1"),
            ),
        )
        reference: EvidenceRef | None = None
        fact_ref: EvidenceRef | None = None
        completion: GeneratorTextCompletion | None = None
        committing = False
        try:
            with invocation_file(self._root, self._binding, request.request_id).locked(
                control
            ) as transaction:
                prior = load_invocation(transaction)
                if prior is not None:
                    require_intent(prior, intent)
                    if prior.fact_ref is None:
                        raise DispatchAlreadyCommitted(
                            "Original local inference is unresolved; no automatic re-execution"
                        )
                    reference, fact_ref = prior.response_ref, prior.fact_ref
                    committing = True
                    fact, completion = self._evidence.fact(
                        intent, request, fact_ref, parameters, control
                    )
                    if fact.response_ref != reference:
                        raise EvidenceIntegrityError(
                            "Snapshot response differs from original fact"
                        )
                    self._authority.verify_completion(fact, op, control)
                    control.checkpoint()
                    self._evidence.put(
                        completion.model_dump_json().encode(),
                        "generator-model-response/1",
                        control,
                    )
                    self._evidence.put(
                        fact.model_dump_json().encode(),
                        "local-generator-fact/1",
                        control,
                    )
                    transaction.confirm()
                else:
                    self._authority.authorize_generate(
                        intent, request, parameters, control
                    )
                    control.checkpoint()
                    self._engine.validate(request, parameters, control)
                    control.checkpoint()
                    self._evidence.retain_inputs(intent, request, parameters, control)
                    committing = True
                    transaction.retain_pending(
                        "0" * 64, intent.model_dump_json().encode()
                    )
                    transaction.write(
                        LocalGeneratorSnapshot(intent=intent).model_dump_json().encode()
                    )
                    transaction.checkpoint()
                    output = LocalGeneratorOutput.model_validate(
                        self._engine.invoke(intent, request, parameters, control)
                    )
                    completion = GeneratorTextCompletion(
                        request_id=request.request_id,
                        generation_input_sha256=request.generation_input_sha256,
                        model_input_sha256=request.model_input_sha256,
                        parameters_ref=intent.parameters_ref,
                        text=output.text,
                        finish_reason=output.finish_reason,
                    )
                    reference = evidence_reference(
                        completion.model_dump_json().encode(),
                        local_metadata("generator-model-response/1"),
                    )
                    fact = LocalGeneratorFact(
                        intent=intent, output=output, response_ref=reference
                    )
                    fact_ref = evidence_reference(
                        fact.model_dump_json().encode(),
                        local_metadata("local-generator-fact/1"),
                    )
                    self._evidence.put(
                        completion.model_dump_json().encode(),
                        "generator-model-response/1",
                        control,
                    )
                    self._evidence.put(
                        fact.model_dump_json().encode(),
                        "local-generator-fact/1",
                        control,
                    )
                    # Persist even a model's out-of-budget fact, but never commit it as completed.
                    self._evidence.fact(intent, request, fact_ref, parameters, control)
                    self._authority.verify_completion(fact, op, control)
                    transaction.checkpoint()
                    transaction.write(
                        LocalGeneratorSnapshot(
                            intent=intent, response_ref=reference, fact_ref=fact_ref
                        )
                        .model_dump_json()
                        .encode()
                    )
            control.checkpoint()
            assert reference is not None
            return reference
        except BaseException as error:
            if committing:
                error.generator_execution = GeneratorExecutionObservation(intent, reference, completion, fact_ref)  # type: ignore[attr-defined]
            raise

    def inspect(
        self, request: GeneratorModelRequest, op: OperationContext
    ) -> LocalGeneratorSnapshot:
        request, op = GeneratorModelRequest.model_validate(
            request
        ), OperationContext.model_validate(op)
        control = self._access(op)
        parameters = self._evidence.parameters(self._binding, request, control)
        parameters_ref = evidence_reference(
            parameters.model_dump_json().encode(), local_metadata("model-parameters/1")
        )
        with invocation_file(self._root, self._binding, request.request_id).locked(
            control, create_lock=False
        ) as transaction:
            prior = load_invocation(transaction)
            if prior is None:
                raise EvidenceNotFound("Local inference has no original intent")
            expected = self._intent(request, prior.intent.operation, parameters_ref)
            require_intent(prior, expected)
            transaction.checkpoint()
        control.checkpoint()
        return prior

    def reconcile(
        self,
        request: GeneratorModelRequest,
        fact_ref: EvidenceRef,
        op: OperationContext,
    ) -> EvidenceRef:
        request, op = GeneratorModelRequest.model_validate(
            request
        ), OperationContext.model_validate(op)
        fact_ref = EvidenceRef.model_validate(fact_ref)
        if op.mode != "cleanup":
            raise OwnershipConflict(
                "Completion reconciliation requires independent cleanup"
            )
        control = self._access(op)
        prior = self.inspect(request, op)
        if op.parent_operation_id != prior.intent.operation.operation_id:
            raise OwnershipConflict(
                "Cleanup does not refer to original local inference"
            )
        parameters = self._evidence.parameters(self._binding, request, control)
        completion: GeneratorTextCompletion | None = None
        reference: EvidenceRef | None = None
        committing = False
        try:
            with invocation_file(self._root, self._binding, request.request_id).locked(
                control, create_lock=False
            ) as transaction:
                current = load_invocation(transaction)
                if current is None:
                    raise EvidenceNotFound("Original local inference disappeared")
                require_intent(current, prior.intent)
                if current.fact_ref is not None and current.fact_ref != fact_ref:
                    raise OwnershipConflict(
                        "Original completion fact cannot be replaced"
                    )
                fact, completion = self._evidence.fact(
                    prior.intent, request, fact_ref, parameters, control
                )
                reference = fact.response_ref
                if (
                    current.response_ref is not None
                    and current.response_ref != reference
                ):
                    raise EvidenceIntegrityError(
                        "Snapshot response differs from original fact"
                    )
                self._authority.verify_completion(fact, op, control)
                transaction.checkpoint()
                committing = True
                self._evidence.put(
                    completion.model_dump_json().encode(),
                    "generator-model-response/1",
                    control,
                )
                self._evidence.put(
                    fact.model_dump_json().encode(), "local-generator-fact/1", control
                )
                if current.fact_ref is None:
                    transaction.write(
                        LocalGeneratorSnapshot(
                            intent=prior.intent,
                            response_ref=reference,
                            fact_ref=fact_ref,
                        )
                        .model_dump_json()
                        .encode()
                    )
                else:
                    transaction.confirm()
            control.checkpoint()
            return reference
        except BaseException as error:
            if committing:
                error.generator_execution = GeneratorExecutionObservation(prior.intent, reference, completion, fact_ref)  # type: ignore[attr-defined]
            raise
