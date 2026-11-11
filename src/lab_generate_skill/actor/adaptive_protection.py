"""Reverse checks of actual model bytes against original public source/ranges."""

import hashlib
import json
from collections.abc import Callable
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
    ProjectionKind,
)
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_transformation import (
    ContextTransformAudit,
    ContextChange,
    context_bytes_sha,
)
from lab_generate_skill.policies.observation_protection import (
    verify_observation_read_window,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.observation_read import (
    ObservationOverview,
    ObservationReadPayload,
)
from lab_generate_skill.domain.adaptive_candidates import (
    adaptive_candidate_ids,
    adaptive_candidate_kind,
)
from lab_generate_skill.policies.observation_navigation import with_complete_navigation
from lab_generate_skill.policies.observation_viewport import (
    with_public_viewport,
    public_viewport_ranges,
)
from lab_generate_skill.domain.observation_read_geometry import (
    reading_display_spans,
    reading_progress_fingerprint,
)
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)
from lab_generate_skill.policies.observation_display import observation_read_body
from .context_source import actor_source, checked_actor_policy
from .adaptive_layout import adaptive_frame
from .observation_guidance import current_observation_body

IndexProvider = Callable[[ActorPublicTurn], ObservationIndex | None]


def original_index(
    turn: ActorPublicTurn, provider: IndexProvider | None
) -> ObservationIndex | None:
    source = turn.observation_source
    if source is None:
        raise OwnershipConflict("Original adaptive public source required")
    if provider is not None:
        supplied = provider(turn)
        if supplied is not None and (
            supplied.snapshot != source.snapshot
            or supplied.text != turn.observation.text
        ):
            raise OwnershipConflict(
                "Same-call source index changed original public snapshot"
            )
        return supplied
    if source.snapshot.structure == "opaque_public_text/1":
        return None
    return index_public_ax(
        source.snapshot.observation_ref,
        turn.observation.record.model_dump_json().encode(),
        turn.observation,
        source.snapshot.scope,
        source.policy,
    )


def full_observation_body(turn: ActorPublicTurn) -> str:
    observed = turn.observation.record
    assert observed.active_tab_id is not None and turn.observation.text is not None
    overview = ObservationOverview(
        active_tab_id=observed.active_tab_id,
        tabs=observed.tabs,
        last_action_error=observed.last_action_error,
    )
    return (
        "# Original public current state\n"
        + overview.model_dump_json()
        + "\n# Complete captured accessibility text\n"
        + turn.observation.text
    )


def validate_local_source(turn: ActorPublicTurn, index: ObservationIndex) -> None:
    source = turn.observation_source
    assert source is not None
    window = source.local_window
    if source.eligibility != "local_supported" or window is None or not source.tools:
        raise OwnershipConflict(
            "Unregistered or unsupported source cannot become a local view"
        )
    verify_observation_read_window(index, window)


def projected_local_window(
    turn: ActorPublicTurn, index: ObservationIndex | None, candidate_id: str
) -> ObservationReadPayload:
    source = turn.observation_source
    if source is None or source.local_window is None:
        raise OwnershipConflict("Original supported local window required")
    if candidate_id == "local_ax_navigation":
        if index is None or source.window_origin != "automatic_initial":
            raise OwnershipConflict(
                "Complete navigation applies only to the original initial window"
            )
        return with_public_viewport(
            index, with_complete_navigation(index, source.local_window)
        )
    if candidate_id != "local_ax":
        raise ValueError("Unknown local candidate identity")
    return source.local_window


def adaptive_audit(
    source: AllowedContextSource,
    turn: ActorPublicTurn,
    policy: ContextProjectionPolicy,
    kind: ProjectionKind,
    prompt: ActorPrompt,
    index: ObservationIndex | None,
    *,
    candidate_id: str | None = None,
) -> ContextTransformAudit:
    from lab_generate_skill.domain.context_projection import ActorContextSource

    if not isinstance(source, ActorContextSource):
        raise OwnershipConflict("Adaptive audit requires an Actor source")
    public = turn.observation_source
    identity = kind if candidate_id is None else candidate_id
    if public is not None:
        expected_ids = adaptive_candidate_ids(
            policy.schema_version,
            active_read=source.active_read_ref is not None,
            local_supported=public.eligibility == "local_supported",
        )
        if identity not in expected_ids or adaptive_candidate_kind(identity) != kind:
            raise OwnershipConflict(
                "Actual adaptive candidate changed declared identity/order"
            )
    view = prompt.observation_view
    if (
        public is None
        or view is None
        or prompt.prompt_version
        not in (
            "browsergym-adaptive-full-ax-v1",
            "browsergym-adaptive-local-ax-v1",
            "browsergym-adaptive-full-ax-v2",
            "browsergym-adaptive-local-ax-v2",
        )
    ):
        raise EvidenceIntegrityError("Actual explicit adaptive Actor input required")
    system, prefix, suffix = adaptive_frame(turn)
    user = prompt.messages[1].content
    if (
        prompt.messages[0].content != system
        or not user.startswith(prefix)
        or not user.endswith(suffix)
    ):
        raise EvidenceIntegrityError(
            "Adaptive frame changed public task/skill/action/history/output facts"
        )
    body = view.body(user)
    schema_tools = public.policy.schema_version == "observation-read-policy/2"
    if schema_tools and (
        view.invalid_proposals != public.invalid_proposals
        or view.tab_count != len(turn.observation.record.tabs)
        or view.schema_version != "actor-observation-view/3"
    ):
        raise EvidenceIntegrityError(
            "Actual view changed current tab or rejected-proposal facts"
        )
    if (
        view.body_start != len(prefix)
        or view.body_end != len(user) - len(suffix)
        or user != prefix + body + suffix
    ):
        raise EvidenceIntegrityError(
            "Adaptive body left the actual complete model-input framing"
        )
    if (view.snapshot, view.policy, view.tools, view.reads_used, view.no_progress) != (
        public.snapshot,
        public.policy,
        public.tools,
        public.reads_used,
        public.no_progress,
    ):
        raise EvidenceIntegrityError(
            "Actual view changed frozen source/tool/quota facts"
        )
    if kind == "compact_full_ax":
        expected_body = full_observation_body(turn)
        if schema_tools:
            expected_body = current_observation_body(turn, full_body=expected_body)
        if (
            view.mode != "compact_full"
            or view.read_result_ref is not None
            or body != expected_body
        ):
            raise EvidenceIntegrityError(
                "Complete view omitted or changed original public facts"
            )
        assert turn.observation.text is not None
        expected_spans = (
            ()
            if not turn.observation.text
            else (
                dict(
                    unit="unicode_codepoints", start=0, end=len(turn.observation.text)
                ),
            )
        )
        if tuple(span.model_dump() for span in view.source_spans) != expected_spans:
            raise EvidenceIntegrityError(
                "Complete view changed original source coverage"
            )
        if view.progress_fingerprint is not None:
            raise EvidenceIntegrityError(
                "Complete view invented a returned read coverage fact"
            )
    elif kind == "local_ax":
        if index is None:
            raise OwnershipConflict(
                "Local view has no qualified original structure index"
            )
        validate_local_source(turn, index)
        window = projected_local_window(turn, index, identity)
        expected_body = observation_read_body(window)
        if schema_tools:
            expected_body = current_observation_body(
                turn,
                window=window,
                viewport_applied=identity == "local_ax_navigation"
                and bool(public_viewport_ranges(index)),
            )
        if (
            view.mode != "local"
            or view.read_result_ref != public.read_result_ref
            or body != expected_body
        ):
            raise EvidenceIntegrityError(
                "Local view changed the original current returned/automatic window"
            )
        if view.source_spans != reading_display_spans(
            window
        ) or view.progress_fingerprint != reading_progress_fingerprint(window):
            raise EvidenceIntegrityError(
                "Local input changed actual displayed-source/coverage geometry"
            )
    else:
        raise ValueError("Unsupported adaptive input kind")
    original = turn.observation.text
    assert original is not None
    change = ContextChange(
        operation="layout" if kind == "compact_full_ax" else "select_source_ranges",
        source_path="/observation/text",
        target_path="/messages/1/content/observation",
        source_sha256=hashlib.sha256(original.encode()).hexdigest(),
        target_sha256=hashlib.sha256(body.encode()).hexdigest(),
        related_source_paths=(),
        reason_code=(
            "EXACT_PUBLIC_FULL_LAYOUT"
            if kind == "compact_full_ax"
            else "EXACT_PUBLIC_LOCAL_RANGES"
        ),
    )
    return ContextTransformAudit(
        schema_version="context-transform-audit/2",
        role="actor",
        source_ref=source.original_ref,
        policy_sha256=policy.digest,
        kind=kind,
        input_sha256=context_bytes_sha(prompt.model_dump_json().encode()),
        no_op_reason=None,
        changes=(change,),
    )


class AdaptiveActorProtection:
    def __init__(
        self, policy: ContextProjectionPolicy, indices: IndexProvider | None = None
    ) -> None:
        self.policy = checked_actor_policy(policy)
        self.indices = indices

    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        policy = checked_actor_policy(policy)
        if policy != self.policy:
            raise OwnershipConflict(
                "Adaptive protection changed original frozen policy"
            )
        turn = actor_source(source, original, policy)
        valid = draft.source == source and draft.policy_sha256 == policy.digest
        try:
            prompt = ActorPrompt.model_validate_json(draft.input_bytes)
            expected = adaptive_audit(
                source,
                turn,
                policy,
                draft.kind,
                prompt,
                original_index(turn, self.indices),
                candidate_id=draft.candidate_id,
            )
            valid = (
                valid
                and prompt.model_dump_json().encode() == draft.input_bytes
                and expected == draft.audit
            )
        except (ValueError, EvidenceIntegrityError, OwnershipConflict):
            valid = False
        return tuple(
            ContextProtectionCheck(
                name=name,
                status="pass" if valid else "fail",
                reason_code=(
                    "ACTOR_EXACT_PUBLIC_WINDOW" if valid else "ACTOR_WINDOW_CHANGED"
                ),
            )
            for name in policy.protected_rules
        )
