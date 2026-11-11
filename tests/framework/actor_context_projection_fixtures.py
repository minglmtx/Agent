"""Real public Actor schemas; synthetic site pages or pinned original Map input."""

from dataclasses import dataclass
from lab_generate_skill.actor.context_source import ACTOR_PROTECTION_RULES
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorHistoryItem
from lab_generate_skill.domain.actor_projection import MapRailsDiagnosticProjection
from lab_generate_skill.domain.context_projection import (
    ActorContextSource,
    ContextProjectionPolicy,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.identity import Site
from lab_generate_skill.domain.observation import ResolvedObservation
from context_budget_fixtures import selection
from state_contract_fixtures import scope
from test_actor_protocol import turn

PAGES: dict[Site, str] = {
    "shopping_admin": "[1] textbox SKU value='SKU-A' required\n[2] checkbox Enabled checked disabled\n[3] row store='2'\n\t[4] gridcell Price value='€12.30'\n[5] button Save\n",
    "shopping": "[1] row SKU='A-red-42' qty='2' total='$24.60'\n\t[2] link Same name variant='red-42'\n[3] row SKU='A-blue-42' qty='1'\n\t[4] link Same name variant='blue-42'\n",
    "gitlab": "[1] heading ns/project ref='feature/x' path='lib/main.py'\n[2] code 'def f():\\n    return 1'\n[3] row discussion='2'\n\t[4] link comment value='unchanged'\n",
    "reddit": "[1] article forum='news' author='one' post='11'\n\t[2] comment 'same body' author='a'\n\t\t[3] comment 'same body' author='b'\n[4] button Subscribe pressed='false'\n",
    "map": "[1] textbox Start value='A'\n[2] textbox End value='B'\n[3] row mode='walk' distance='1.2 km' duration='17 min'\n\t[4] gridcell step='1' direction='left'\n\t[5] gridcell step='2' direction='right'\n",
}


@dataclass(frozen=True)
class ActorProjectionCase:
    turn: ActorPublicTurn
    raw: bytes
    source: ActorContextSource
    policy: ContextProjectionPolicy


def actor_projection_case(
    site: Site = "shopping_admin",
    *,
    original: ActorPublicTurn | None = None,
    structural: bool = False,
    page: str | None = None,
) -> ActorProjectionCase:
    value = turn() if original is None else original
    if original is None:
        task = value.task.model_copy(
            update={"identity": value.task.identity.model_copy(update={"site": site})}
        )
        text = PAGES[site] if page is None else page
        observed = value.observation.record.model_copy(
            update={
                "task": task.identity,
                "text": text,
                "sequence": 9,
                "last_action_error": "step 8: value rejected, unsaved",
            }
        )
        value = ActorPublicTurn.model_validate(
            value.model_copy(
                update={
                    "task": task,
                    "observation": ResolvedObservation(record=observed, text=text),
                    "history": tuple(
                        ActorHistoryItem(
                            action=f"fill('1', 'value-{i}')", error=f"error-{i}"
                        )
                        for i in range(9)
                    ),
                }
            )
        )
    raw = value.model_dump_json().encode()
    reference = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="actor-public-turn/1",
            visibility="public",
            producer="unit-real-actor-schema",
        ),
    )
    observed = value.observation.record
    state = scope().model_copy(
        update={
            "task": value.task.identity,
            "context_id": observed.context_id,
            "attempt_id": observed.attempt_id,
        }
    )
    source = ActorContextSource(
        scope=state,
        candidate_id="original-candidate",
        revision_round=0,
        turn_ref=reference,
    )
    base = selection(
        structural=structural,
        counts=(90, 70) if structural else (90,),
        kinds=("identity", "structural_ax") if structural else ("identity",),
    ).policy
    policy = ContextProjectionPolicy.model_validate(
        {
            **base.model_dump(),
            "protected_rules": ACTOR_PROTECTION_RULES,
            "actor_projection": MapRailsDiagnosticProjection() if structural else None,
        }
    )
    return ActorProjectionCase(value, raw, source, policy)
