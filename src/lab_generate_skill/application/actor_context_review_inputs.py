"""One generation's immutable verified bodies; current permissions stay external.

Complete references and bytes are checked once when entering this carrier.
Only deeply immutable, explicitly selected contracts retain parsed values.
No caller can replace an admitted body through the public read-only view.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeVar, cast
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorPublicTurn
from lab_generate_skill.domain.actor_engine import LocalActorParameters
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.context_transformation import ContextTransformAudit
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.policies.evidence_bytes import require_complete_read_bound

from .actor_history_bodies import ActorHistoryBodies

T = TypeVar("T", bound=Contract)


class ActorContextReviewInputs:
    _schemas = frozenset(
        {
            "actor-context-configuration/1",
            "context-preparation/2",
            "actor-public-turn/1",
            "actor-public-turn/2",
            "actor-model-input/1",
            "model-parameters/1",
            "observation/1",
            "observation-viewport/1",
            "run-plan/3",
            "release-manifest/1",
            "source-claim/1",
            "recovery-plan/1",
            "context-transform-audit/1",
            "context-transform-audit/2",
            "observation-read-result/2",
            "actor-context-count-execution/1",
            "actor-context-count-command/1",
            "actor-context-count-reply/1",
        }
    )
    _models = frozenset(
        {
            ActorContextConfiguration,
            ActorPrompt,
            ActorPublicTurn,
            LocalActorParameters,
            ContextPreparationReceipt,
            ContextTransformAudit,
            Observation,
        }
    )

    def __init__(self, original: EvidenceReader) -> None:
        self.original = original
        self._bodies: dict[EvidenceRef, VerifiedEvidenceBody] = {}
        self._documents: dict[tuple[EvidenceRef, type[Contract], bool], Contract] = {}
        self._closed = False
        self._history = ActorHistoryBodies()

    @property
    def bodies(self) -> Mapping[EvidenceRef, bytes]:
        return MappingProxyType({ref: body.raw for ref, body in self._bodies.items()})

    def clear(self) -> None:
        self._closed = True
        self._bodies.clear()
        self._documents.clear()
        self._history.clear()

    def _open(self, control: OperationControl) -> None:
        control.checkpoint()
        if self._closed:
            raise OwnershipConflict("Original Actor input lifetime is closed")

    def retain(self, body: VerifiedEvidenceBody, control: OperationControl) -> None:
        self._open(control)
        if type(body) is not VerifiedEvidenceBody:
            raise EvidenceIntegrityError("Original verified Actor body required")
        ref = body.reference
        if ref.content_schema in self._history.schemas:
            self._history.retain(
                body, sum(len(value.raw) for value in self._bodies.values())
            )
            return
        if ref.content_schema not in self._schemas:
            return
        if ref in self._bodies:
            if self._bodies[ref].raw != body.raw:
                raise EvidenceIntegrityError("Original Actor body changed")
            return
        if len(self._bodies) >= 32 or ref.size_bytes > 16 * 1024**2:
            raise EvidenceIntegrityError("Actor context input graph exceeds bound")
        if (
            sum(len(value.raw) for value in self._bodies.values()) + len(body.raw)
            > 64 * 1024**2
        ):
            raise EvidenceIntegrityError("Actor context complete bodies exceed bound")
        self._history.reserve_primary(
            sum(len(value.raw) for value in self._bodies.values()) + len(body.raw)
        )
        self._bodies[ref] = body

    def read_verified(
        self, reference: EvidenceRef, control: OperationControl
    ) -> VerifiedEvidenceBody:
        reference = EvidenceRef.model_validate(reference)
        self._open(control)
        if reference in self._bodies:
            return self._bodies[reference]
        if reference.content_schema in self._history.schemas:
            history = self._history.get(reference)
            if history is not None:
                return history
        # Reject an oversized declared member before its I/O, as before.
        if reference.content_schema in self._schemas and (
            len(self._bodies) >= 32
            or reference.size_bytes > 16 * 1024**2
            or sum(len(value.raw) for value in self._bodies.values())
            + reference.size_bytes
            > 64 * 1024**2
        ):
            raise EvidenceIntegrityError("Actor context input graph exceeds bound")
        body = VerifiedEvidenceBody(reference, self.original.read(reference, control))
        self.retain(body, control)
        self._open(control)
        return body

    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        return self.read_verified(reference, control).raw

    def read_document(
        self,
        reference: EvidenceRef,
        model: type[T],
        limit: int,
        control: OperationControl,
        *,
        canonical: bool,
    ) -> T:
        require_complete_read_bound(reference, limit)
        body = self.read_verified(reference, control)
        key = (body.reference, model, canonical)
        if key in self._documents:
            return cast(T, self._documents[key])
        value = model.model_validate_json(body.raw)
        if canonical and value.model_dump_json().encode() != body.raw:
            raise EvidenceIntegrityError("Actor input must retain canonical bytes")
        if model in self._models and body.reference in self._bodies:
            self._documents[key] = value
        self._open(control)
        return value
