"""Independent public-field/AX relation checks of actual rendered Actor bytes.

Never invokes the forward projector. Message framing is shared, but original
task/skill/history/tab fields are independently required, and the page checker
matches every source line against actual output and checks allowed omissions.
"""

import json
from urllib.parse import urlsplit
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from lab_generate_skill.domain.actor_projection import (
    MapRailsDiagnosticProjection,
    MapRailsAddressableProjection,
)
from lab_generate_skill.domain.context_preparation import ContextInputDraft
from lab_generate_skill.domain.context_projection import (
    AllowedContextSource,
    ContextProjectionPolicy,
    ContextProtectionCheck,
    ProjectionKind,
)
from lab_generate_skill.domain.context_transformation import (
    ContextChange,
    ContextTransformAudit,
    context_bytes_sha,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from .instructions import SYSTEM
from .message_layout import actor_messages
from .map_rails_projection import SCOPE, ADDRESSABLE_SCOPE
from .context_ax_protection import diagnostic_changes
from .context_source import actor_source, checked_actor_policy


def actor_page(turn: ActorPublicTurn, actual: ActorPrompt) -> str:
    observed = turn.observation.record
    active = next(tab for tab in observed.tabs if tab.tab_id == observed.active_tab_id)
    prefix = f"# Goal\n{turn.task.goal}\n\n# Current URL\n{active.url}\n\n# Current page accessibility tree\n"
    framing = actor_messages(turn, "")
    if not framing[1].content.startswith(prefix):
        raise EvidenceIntegrityError("Actor framing changed without a contract version")
    suffix = framing[1].content[len(prefix) :]
    user = actual.messages[1].content
    if (
        actual.messages[0].content != SYSTEM
        or not user.startswith(prefix)
        or not user.endswith(suffix)
    ):
        raise EvidenceIntegrityError(
            "Actor changed task/instructions/skill/history/constraints framing"
        )
    # Independent source extraction protects against omissions in a shared
    # formatter; no early events or public requirements can silently disappear.
    history_fields: tuple[str, ...] = (
        (
            "# Previous actions\n"
            + json.dumps([h.model_dump() for h in turn.history], ensure_ascii=False),
        )
        if all(item.executed is None for item in turn.history)
        else (
            "# Previous executed business actions\n"
            + json.dumps(
                [
                    dict(action=item.action, error=item.error, executed=True)
                    for item in turn.history
                    if item.executed is True
                ],
                ensure_ascii=False,
            ),
            "# Rejected proposals: not executed, not search results\n"
            + json.dumps(
                [
                    dict(
                        proposal=item.action,
                        status="proposal_rejected",
                        executed=False,
                        feedback=item.error,
                    )
                    for item in turn.history
                    if item.executed is False
                ],
                ensure_ascii=False,
            ),
        )
    )
    if any(item.executed is None for item in turn.history) and not all(
        item.executed is None for item in turn.history
    ):
        history_fields += (
            "# Legacy history: execution status was not explicitly recorded\n"
            + json.dumps(
                [item.model_dump() for item in turn.history if item.executed is None],
                ensure_ascii=False,
            ),
        )
    fields: tuple[str, ...] = (
        *history_fields,
        "# Last action error\n" + observed.last_action_error,
        "# Applicable skills\n"
        + json.dumps(turn.skill.model_payload(), ensure_ascii=False),
        "# Open tabs\n"
        + json.dumps(
            [
                dict(
                    index=i,
                    url=t.url,
                    title=t.title,
                    active=t.tab_id == observed.active_tab_id,
                )
                for i, t in enumerate(observed.tabs)
            ],
            ensure_ascii=False,
        ),
    )
    if turn.task.output_requirements:
        fields += (
            "# Public output requirements\n"
            + json.dumps(turn.task.output_requirements, ensure_ascii=False),
        )
    if any(field not in suffix for field in fields):
        raise EvidenceIntegrityError(
            "Actor shared layout omitted a protected original field"
        )
    return user[len(prefix) : len(user) - len(suffix)]


def _diagnostic_source(turn: ActorPublicTurn, policy: ContextProjectionPolicy) -> None:
    if not isinstance(
        policy.actor_projection,
        (MapRailsDiagnosticProjection, MapRailsAddressableProjection),
    ):
        raise OwnershipConflict("Unqualified Actor structural view")
    observed = turn.observation.record
    active = next(t for t in observed.tabs if t.tab_id == observed.active_tab_id)
    origin = urlsplit(turn.task.start_url)
    text = turn.observation.text
    assert text is not None
    if not (
        active.title == "Action Controller: Exception caught"
        and origin.scheme == "http"
        and origin.hostname == "127.0.0.1"
        and origin.port is not None
        and 1024 <= origin.port <= 65535
        and active.url == f"{origin.scheme}://{origin.netloc}/map"
        and text.startswith("RootWebArea 'Action Controller: Exception caught'")
        and "heading 'Routing Error'" in text
        and "heading 'No route matches [GET] \"/map\"'" in text
        and "heading 'Routes'" in text
    ):
        raise OwnershipConflict(
            "Structural Actor output changed original diagnostic eligibility"
        )


def actor_audit(
    source: AllowedContextSource,
    turn: ActorPublicTurn,
    policy: ContextProjectionPolicy,
    kind: ProjectionKind,
    prompt: ActorPrompt,
) -> ContextTransformAudit:
    page = actor_page(turn, prompt)
    original = turn.observation.text
    assert original is not None
    changes: tuple[ContextChange, ...] = ()
    no_op: str | None = "identity" if kind == "identity" else "non_diagnostic_full_ax"
    if prompt.prompt_version == "browsergym-baseline-full-ax-v1":
        if page != original:
            raise EvidenceIntegrityError(
                "Full AX candidate changed original page bytes"
            )
    else:
        if kind != "structural_ax":
            raise EvidenceIntegrityError(
                "Identity candidate cannot select structural content"
            )
        _diagnostic_source(turn, policy)
        preserve_ids = isinstance(
            policy.actor_projection, MapRailsAddressableProjection
        )
        scope = ADDRESSABLE_SCOPE if preserve_ids else SCOPE
        version = (
            "browsergym-map-rails-diagnostic-ax-v2"
            if preserve_ids
            else "browsergym-map-rails-diagnostic-ax-v1"
        )
        if prompt.prompt_version != version or not page.endswith(scope):
            raise EvidenceIntegrityError("Missing original declared diagnostic scope")
        changes = diagnostic_changes(
            original, page[: -len(scope)], page, preserve_ids=preserve_ids
        )
        no_op = None
    return ContextTransformAudit(
        role="actor",
        source_ref=source.original_ref,
        policy_sha256=policy.digest,
        kind=kind,
        input_sha256=context_bytes_sha(prompt.model_dump_json().encode()),
        no_op_reason=no_op,
        changes=changes,
    )


class ActorContextProtection:
    def __init__(self, policy: ContextProjectionPolicy) -> None:
        self._policy = checked_actor_policy(policy)

    def verify(
        self,
        source: AllowedContextSource,
        original: bytes,
        draft: ContextInputDraft,
        policy: ContextProjectionPolicy,
    ) -> tuple[ContextProtectionCheck, ...]:
        policy = checked_actor_policy(policy)
        if policy != self._policy:
            raise OwnershipConflict("Actor protection changed frozen strategy")
        turn = actor_source(source, original, policy)
        draft = ContextInputDraft.model_validate(draft)
        valid = (
            draft.source == source
            and draft.policy_sha256 == policy.digest
            and draft.kind in policy.candidate_order
        )
        try:
            prompt = ActorPrompt.model_validate_json(draft.input_bytes)
            if prompt.model_dump_json().encode() != draft.input_bytes:
                raise EvidenceIntegrityError("Noncanonical Actor input")
            expected = actor_audit(source, turn, policy, draft.kind, prompt)
            valid = valid and expected == draft.audit
        except (ValueError, EvidenceIntegrityError, OwnershipConflict):
            valid = False
        return tuple(
            ContextProtectionCheck(
                name=name,
                status="pass" if valid else "fail",
                reason_code=(
                    "ACTOR_COMPLETE_RELATIONS" if valid else "ACTOR_RELATIONS_CHANGED"
                ),
            )
            for name in policy.protected_rules
        )
