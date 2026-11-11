"""Pure complete Teacher candidates; no I/O, counting, saving or dispatch."""

from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.teacher_input import native_evidence
from lab_generate_skill.domain.errors import OwnershipConflict
from .context_source import checked_teacher_policy, teacher_source
from .message_layout import original_messages, shared_messages
from .field_projection import project_fields
from .context_protection import teacher_audit


class TeacherContextProjector:
    def __init__(self, policy: ContextProjectionPolicy) -> None:
        self.policy = checked_teacher_policy(policy)

    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        policy = checked_teacher_policy(policy)
        if policy != self.policy:
            raise OwnershipConflict("Teacher projector changed original strategy")
        allowed = teacher_source(source, original, policy)
        drafts = []
        for kind in policy.candidate_order:
            actual = (
                original_messages(allowed)
                if kind == "identity"
                else shared_messages(
                    allowed,
                    project_fields(native_evidence(allowed.messages[1].content)),
                )
            )
            drafts.append(
                ContextInputDraft(
                    candidate_id=kind,
                    kind=kind,
                    source=source,
                    policy_sha256=policy.digest,
                    input_bytes=actual.model_dump_json().encode(),
                    audit=teacher_audit(source, allowed, policy, kind, actual),
                )
            )
        return tuple(drafts)
