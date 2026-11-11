"""Finite Actor full/local drafts; no count, save, website operation or permission."""

import hashlib
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorMessage
from lab_generate_skill.domain.adaptive_candidates import (
    adaptive_candidate_ids,
    adaptive_candidate_kind,
)
from lab_generate_skill.domain.actor_observation_view import ActorObservationView
from lab_generate_skill.domain.observation_read import ObservationSourceSpan
from lab_generate_skill.domain.observation_read_geometry import (
    reading_display_spans,
    reading_progress_fingerprint,
)
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ActorContextSource,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.policies.observation_display import observation_read_body
from .context_source import actor_source, checked_actor_policy
from .adaptive_layout import adaptive_frame
from .observation_guidance import current_observation_body
from lab_generate_skill.policies.observation_viewport import public_viewport_ranges
from .adaptive_protection import (
    IndexProvider,
    original_index,
    full_observation_body,
    adaptive_audit,
    projected_local_window,
)


class AdaptiveActorProjector:
    def __init__(
        self, policy: ContextProjectionPolicy, indices: IndexProvider | None = None
    ) -> None:
        self.policy = checked_actor_policy(policy)
        self.indices = indices

    def project(
        self,
        source: AllowedContextSource,
        original: bytes,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextInputDraft, ...]:
        policy = checked_actor_policy(policy)
        if policy != self.policy or not isinstance(source, ActorContextSource):
            raise OwnershipConflict(
                "Adaptive projector changed original Actor source/policy"
            )
        turn = actor_source(source, original, policy)
        public = turn.observation_source
        if public is None:
            raise ValueError("Explicit public source2 required")
        index = original_index(turn, self.indices)
        identities = adaptive_candidate_ids(
            policy.schema_version,
            active_read=source.active_read_ref is not None,
            local_supported=public.eligibility == "local_supported",
        )
        system, prefix, suffix = adaptive_frame(turn)
        schema_tools = public.policy.schema_version == "observation-read-policy/2"
        drafts = []
        for identity in identities:
            kind = adaptive_candidate_kind(identity)
            local = kind == "local_ax"
            if local:
                window = projected_local_window(turn, index, identity)
                body = observation_read_body(window)
                spans = reading_display_spans(window)
                fingerprint = reading_progress_fingerprint(window)
                if schema_tools:
                    body = current_observation_body(
                        turn,
                        window=window,
                        viewport_applied=identity == "local_ax_navigation"
                        and index is not None
                        and bool(public_viewport_ranges(index)),
                    )
                omissions: tuple[str, ...] = ("unshown_source_ranges_remain_readable",)
            else:
                body = full_observation_body(turn)
                if schema_tools:
                    body = current_observation_body(turn, full_body=body)
                assert turn.observation.text is not None
                spans = (
                    ()
                    if not turn.observation.text
                    else (
                        ObservationSourceSpan(start=0, end=len(turn.observation.text)),
                    )
                )
                fingerprint = None
                omissions = ()
            extra = (
                dict(
                    tab_count=len(turn.observation.record.tabs),
                    invalid_proposals=public.invalid_proposals,
                )
                if schema_tools
                else {}
            )
            view = ActorObservationView.model_validate(
                dict(
                    schema_version=(
                        "actor-observation-view/3"
                        if schema_tools
                        else "actor-observation-view/2"
                    ),
                    snapshot=public.snapshot,
                    policy=public.policy,
                    mode="local" if local else "compact_full",
                    source_spans=spans,
                    body_start=len(prefix),
                    body_end=len(prefix) + len(body),
                    body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                    body_token_limit=public.policy.body_max_tokens if local else None,
                    tools=public.tools,
                    read_result_ref=public.read_result_ref if local else None,
                    reads_used=public.reads_used,
                    no_progress=public.no_progress,
                    omissions=omissions,
                    progress_fingerprint=fingerprint,
                    **extra,
                )
            )
            prompt = ActorPrompt(
                prompt_version=(
                    (
                        "browsergym-adaptive-local-ax-v2"
                        if schema_tools
                        else "browsergym-adaptive-local-ax-v1"
                    )
                    if local
                    else (
                        "browsergym-adaptive-full-ax-v2"
                        if schema_tools
                        else "browsergym-adaptive-full-ax-v1"
                    )
                ),
                messages=(
                    ActorMessage(role="system", content=system),
                    ActorMessage(role="user", content=prefix + body + suffix),
                ),
                observation_view=view,
            )
            drafts.append(
                ContextInputDraft.model_validate(
                    dict(
                        candidate_id=identity,
                        kind=kind,
                        source=source,
                        policy_sha256=policy.digest,
                        input_bytes=prompt.model_dump_json().encode(),
                        audit=adaptive_audit(
                            source,
                            turn,
                            policy,
                            kind,
                            prompt,
                            index,
                            candidate_id=identity,
                        ),
                    )
                )
            )
        return tuple(drafts)
