"""Explicit synthetic public snapshot and proposed settings; no registered tool."""

from typing import Any
import unicodedata
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.policies.observation_index import (
    ObservationIndex,
    index_public_ax,
)
from observation_fixtures import sample_observation
from retrieval_fixtures import reference
from state_contract_fixtures import scope


def policy(**changes: Any) -> ObservationReadPolicy:
    return ObservationReadPolicy.model_validate(
        dict(
            policy_id="unit-proposed-adaptive-observation-v1",
            unicode_version=unicodedata.unidata_version,
            switch_tokens=24576,
            body_target_tokens=6000,
            body_max_tokens=8000,
            reads_per_observation=6,
            warn_remaining=2,
            consecutive_no_progress=2,
            max_ranges=4,
            directory_entries=16,
            search_hits=3,
            page_units=20,
            max_source_lines=20000,
        )
        | changes
    )


def indexed(text: str, **changes: Any) -> ObservationIndex:
    state = scope()
    record = sample_observation(
        state.task, state.context_id, state.attempt_id
    ).model_copy(update={"text": text})
    return index_public_ax(
        reference(record, "observation/1", "public"),
        record.model_dump_json().encode(),
        ResolvedObservation(record=record, text=text),
        state,
        policy(**changes),
    )
