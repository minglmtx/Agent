"""Frozen original revision, prepared model bytes and existing one-send plan.

These immutable links grant no source/model/fee permission. The original source
and provider authority and RequestLedger are mandatory at the real send gate.
"""

import hashlib
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract, NonEmptyText
from .construction import ConstructionCall
from .construction_inputs import RevisionInput
from .context_preparation import ContextPreparationRequest, PreparedContextRef
from .context_projection import TeacherContextSource
from .teacher_scope import TeacherContextScope
from .model_request import ModelSendPlan
from .model_response import ModelSendResult
from .evidence import EvidenceRef
from .budget import Money
from .state_scope import private_state_ref
from .skill import CompactSkill


class TeacherRevisionPlan(Contract):
    schema_version: Literal["teacher-revision-plan/1"] = "teacher-revision-plan/1"
    revision: RevisionInput
    call: ConstructionCall
    preparation: ContextPreparationRequest
    prepared: PreparedContextRef
    send: ModelSendPlan
    reasoning_accounting: Literal["completion_includes_reasoning", "separate_reasoning"]

    @model_validator(mode="after")
    def original_links(self) -> Self:
        revision, call, preparation, prepared, send = (
            self.revision,
            self.call,
            self.preparation,
            self.prepared,
            self.send,
        )
        source = preparation.source
        scope = preparation.scope
        profile = preparation.profile
        request = send.reservation.request
        if (
            not isinstance(source, TeacherContextSource)
            or not isinstance(scope, TeacherContextScope)
            or preparation.schema_version != "context-preparation-request/2"
        ):
            raise ValueError(
                "Actual Teacher revision requires its task-level allowed source"
            )
        if (
            (revision.request_id, revision.teacher_round, revision.seed)
            != (call.request_id, call.candidate_slot - 3, call.seed)
            or call.role != "teacher"
            or call.resample_index != 0
            or call.temperature is not None
        ):
            raise ValueError("Original registered Teacher call/round/sampling required")
        original = revision.model_dump_json().encode()
        if (call.input_ref.sha256, call.input_ref.size_bytes) != (
            hashlib.sha256(original).hexdigest(),
            len(original),
        ):
            raise ValueError(
                "Registered call must bind complete original RevisionInput bytes"
            )
        if (
            revision.projection_ref != source.allowed_input_ref
            or revision.teacher_round != source.teacher_round
            or revision.request_id != preparation.request_id
        ):
            raise ValueError("Teacher allowed projection/round/request changed")
        if (
            prepared.request_sha256
            != hashlib.sha256(preparation.model_dump_json().encode()).hexdigest()
            or prepared.outcome != "prepared"
            or prepared.selected_input_ref != send.input_ref
        ):
            raise ValueError(
                "Only original accepted preparation can bind a Teacher send"
            )
        if (
            profile.provider != "openrouter"
            or not profile.paid
            or profile.role != "teacher"
            or request.role != "teacher"
            or request.provider_id != "openrouter"
        ):
            raise ValueError("Frozen original paid OpenRouter Teacher role required")
        if (
            request.request_id,
            request.owner,
            request.task,
            request.attempt_id,
            request.candidate_index,
            request.revision_index,
            request.logical_index,
        ) != (
            revision.request_id,
            scope.owner,
            scope.task,
            None,
            call.candidate_slot,
            revision.teacher_round,
            0,
        ):
            raise ValueError(
                "Teacher send changed original logical source/call identity"
            )
        if (
            preparation.operation != send.operation
            or request.model_id != profile.model
            or profile.routing_ref != call.model_binding_ref
            or profile.configuration_ref != call.parameters_ref
            or send.parameters_ref != call.parameters_ref
        ):
            raise ValueError(
                "Teacher actual operation/model/routing/parameters changed"
            )
        fee = profile.fee_scope_ref
        budget = send.reservation.scope.model_dump_json().encode()
        if (
            fee is None
            or fee.media_type != "application/json"
            or (fee.sha256, fee.size_bytes)
            != (hashlib.sha256(budget).hexdigest(), len(budget))
        ):
            raise ValueError(
                "Teacher preparation must retain original complete fee scope"
            )
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Teacher revision plan exceeds metadata bound")
        return self


class TeacherCompletion(Contract):
    provider_request_id: NonEmptyText
    skill: CompactSkill
    charge: Money | None
    input_tokens: int | None = Field(default=None, ge=0, le=2147483647)
    output_tokens: int | None = Field(default=None, ge=0, le=2147483647)
    reasoning_tokens: int | None = Field(default=None, ge=0, le=2147483647)


class BoundTeacherRevisionPlan(Contract):
    reference: EvidenceRef
    plan: TeacherRevisionPlan

    @model_validator(mode="after")
    def original_document(self) -> Self:
        private_state_ref(self.reference, "teacher-revision-plan/1")
        raw = self.plan.model_dump_json().encode()
        if self.reference.media_type != "application/json" or (
            self.reference.sha256,
            self.reference.size_bytes,
        ) != (hashlib.sha256(raw).hexdigest(), len(raw)):
            raise ValueError("Exact complete original Teacher plan binding required")
        return self


class TeacherRevisionExecution(Contract):
    schema_version: Literal["teacher-revision-execution/1"] = (
        "teacher-revision-execution/1"
    )
    plan_ref: EvidenceRef
    send_result: ModelSendResult

    @model_validator(mode="after")
    def original_return(self) -> Self:
        private_state_ref(self.plan_ref, "teacher-revision-plan/1")
        if (
            self.plan_ref.media_type != "application/json"
            or self.send_result.fact.request.role != "teacher"
        ):
            raise ValueError("Original Teacher plan and real sender result required")
        if len(self.model_dump_json().encode()) > 2 * 1024**2:
            raise ValueError("Teacher original execution exceeds metadata bound")
        return self
