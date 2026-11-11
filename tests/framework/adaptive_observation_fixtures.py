"""Synthetic explicit view/count facts; never strategy or business qualification."""

import hashlib
from lab_generate_skill.domain.actor_observation_view import ActorObservationView
from lab_generate_skill.domain.actor_prompt import ActorMessage, ActorPrompt
from lab_generate_skill.domain.observation_read import ObservationReadRequest
from lab_generate_skill.domain.observation_read_progress import ObservationReadRecord
from lab_generate_skill.domain.context_budget import (
    CountedContextInput,
    TokenMeasurement,
)
from actor_engine_fixtures import UnitSession
from context_budget_fixtures import ref
from observation_read_fixtures import indexed


class ObservationSession(UnitSession):
    def __init__(self) -> None:
        super().__init__()
        self.body_tokens: tuple[int, ...] = (8, 9)
        self.body_calls: list[str] = []
        self.body_failure: BaseException | None = None

    def tokenize_observation(self, text: str) -> tuple[int, ...]:
        self.body_calls.append(text)
        if self.body_failure is not None:
            raise self.body_failure
        return self.body_tokens


def prompt(
    body: str = "[1] button Save", *, local: bool = True, limit: int = 8
) -> ActorPrompt:
    index = indexed(
        "[1] RootWebArea 'public'\n\t[2] button Save\n",
        body_target_tokens=min(6, limit),
        body_max_tokens=limit,
    )
    header = "Public observation follows.\n"
    view = ActorObservationView(
        snapshot=index.snapshot,
        policy=index.policy,
        mode="local" if local else "compact_full",
        source_spans=(),
        body_start=len(header),
        body_end=len(header) + len(body),
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        body_token_limit=limit if local else None,
        tools=("list_regions", "read_region", "search_regions"),
        read_result_ref=None,
        reads_used=0,
        no_progress=0,
        omissions=("undisplayed_ranges",) if local else (),
    )
    return ActorPrompt(
        prompt_version=(
            "browsergym-adaptive-local-ax-v1"
            if local
            else "browsergym-adaptive-full-ax-v1"
        ),
        messages=(
            ActorMessage(role="system", content="Synthetic registered protocol"),
            ActorMessage(role="user", content=header + body + "\nEnd observation."),
        ),
        observation_view=view,
    )


def record(
    request: ObservationReadRequest, body: str, *, tokens: int = 2
) -> ObservationReadRecord:
    return ObservationReadRecord(
        request=request,
        result_ref=ref("observation-read-result/1", "public", request.request_id),
        body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        count=CountedContextInput(
            measurement=TokenMeasurement(
                schema_version="context-token-measurement/2",
                role="actor",
                input_ref=ref("actor-model-input/1", tag=request.request_id),
                profile_sha256="a" * 64,
                policy_sha256="b" * 64,
                input_tokens=10,
                upper_bound_tokens=10,
                precision="exact",
                complete_request=True,
                elapsed_seconds=0.0,
                observation_tokens=tokens,
                observation_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            ),
            evidence_ref=ref("actor-context-count-execution/1", tag=request.request_id),
        ),
    )
