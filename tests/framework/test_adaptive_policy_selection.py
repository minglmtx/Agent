"""Explicit factory/version/pin boundaries; synthetic software document only."""

import json
import pytest
from lab_generate_skill.bootstrap.actor_context_policy import (
    ACTOR_CONTEXT_IMPLEMENTATION_FILES,
    ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
    accepted_actor_context_policy,
)
from lab_generate_skill.domain.actor_projection import (
    AdaptiveObservationProjection,
    ObservationTaskBinding,
    FullAxProjection,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.actor.context_source import ADAPTIVE_ACTOR_PROTECTION_RULES
from observation_read_fixtures import policy


def selected() -> AdaptiveObservationProjection:
    return AdaptiveObservationProjection(
        read_policy=policy(),
        local_bindings=(
            ObservationTaskBinding(
                site="map",
                family="navigation_page_identity",
                contract_version=1,
                split="train",
            ),
        ),
    )


def freeze(
    files: dict[str, str], projection: AdaptiveObservationProjection | FullAxProjection
) -> ContextProjectionPolicy:
    raw = json.dumps(
        dict(
            schema_version="framework-check/3",
            passed=True,
            source_stable_during_checks=True,
            files=files,
        )
    ).encode()
    ref = evidence_reference(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="framework-check/3",
            visibility="private",
            producer="unit-software-document",
        ),
    )
    return accepted_actor_context_policy(ref, raw, projection)


def test_actual_factory_keeps_explicit_adaptive_version_order_bindings_and_legacy_scope() -> (
    None
):
    files = {
        name: "a" * 64
        for name in (
            *ACTOR_CONTEXT_IMPLEMENTATION_FILES,
            *ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
        )
    }
    choice = selected()
    actual = freeze(files, choice)
    assert actual.schema_version == "context-projection-policy/3"
    assert actual.actor_projection == choice and actual.candidate_order == (
        "compact_full_ax",
        "local_ax",
    )
    assert actual.protected_rules == ADAPTIVE_ACTOR_PROTECTION_RULES
    assert not actual.allow_identity_fallback and actual.forced_kind is None
    common = {name: files[name] for name in ACTOR_CONTEXT_IMPLEMENTATION_FILES}
    # Other strategy pins neither activate this capability nor affect its old implementation digest.
    old = freeze(common, FullAxProjection())
    with_extras = freeze(files, FullAxProjection())
    assert old.implementation_sha256 == with_extras.implementation_sha256
    assert (
        old.schema_version == "context-projection-policy/1"
        and old.actor_projection is None
    )
    assert old.candidate_order == ("identity",)


@pytest.mark.parametrize(
    "fault", ["missing_reader", "missing_counter", "bad_pin", "foreign_unicode"]
)
def test_adaptive_factory_refuses_missing_implementation_or_changed_search_runtime(
    fault: str,
) -> None:
    files = {
        name: "a" * 64
        for name in (
            *ACTOR_CONTEXT_IMPLEMENTATION_FILES,
            *ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
        )
    }
    choice = selected()
    if fault == "missing_reader":
        del files["src/lab_generate_skill/adapters/plans/observation_reads.py"]
    elif fault == "missing_counter":
        del files["src/lab_generate_skill/adapters/models/observation_body_counts.py"]
    elif fault == "bad_pin":
        files[ACTOR_ADAPTIVE_IMPLEMENTATION_FILES[0]] = "Z" * 64
    else:
        choice = choice.model_copy(
            update={
                "read_policy": choice.read_policy.model_copy(
                    update={"unicode_version": "0.0"}
                )
            }
        )
    with pytest.raises(EvidenceIntegrityError):
        freeze(files, choice)
