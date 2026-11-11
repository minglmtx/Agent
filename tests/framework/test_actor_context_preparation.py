"""Real ActorPublicTurn/renderer/protection + common CAS/native frame module ABC.

Original service/channel and full byte evidence, synthetic resident tokenizer
and authority; not installed model, actual website, source admission or quality.
"""

from pathlib import Path
from lab_generate_skill.bootstrap.context_projection import build_actor_context
from lab_generate_skill.application.context_preparation import (
    prepare_context,
    ContextPreparationDeps,
)
from lab_generate_skill.application.context_review import (
    review_context,
    ContextReviewDeps,
)
from lab_generate_skill.domain.context_preparation import ContextPreparationRequest
from lab_generate_skill.domain.evidence import EvidenceMetadata
from actor_context_projection_fixtures import actor_projection_case
from actor_context_fixtures import counter_case
from context_preparation_fixtures import UnitAuthority
from state_contract_fixtures import op
from test_actor_count_evidence import reviewer


def test_real_actor_source_complete_noop_audit_count_and_closed_read_combination(
    tmp_path: Path,
) -> None:
    native = counter_case(tmp_path)
    source = actor_projection_case()
    reference = native.evidence.put(
        source.raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="actor-public-turn/1",
            visibility="public",
            producer="unit-real-actor-schema",
        ),
        native.control,
    )
    assert reference == source.source.original_ref
    project, protection = build_actor_context(source.policy)
    operation = op("real-actor-context").model_copy(
        update={"attempt_id": source.source.scope.attempt_id}
    )
    request = ContextPreparationRequest(
        scope=source.source.scope,
        operation=operation,
        request_id="original-module-request",
        source=source.source,
        profile=native.profile,
        policy=source.policy,
    )
    authority = UnitAuthority()
    prepared = prepare_context(
        request,
        ContextPreparationDeps(
            native.evidence, authority, project, protection, native.counter
        ),
        control=native.control,
    )
    counts = reviewer(native)
    native.client.close(native.control)
    frames = len(native.channel.sent)
    receipt = review_context(
        request,
        prepared,
        ContextReviewDeps(native.evidence, authority, project, protection, counts),
        expected_input_ref=prepared.selected_input_ref,
        control=native.control,
    )
    assert (
        receipt.outcome == "prepared"
        and receipt.schema_version == "context-preparation/2"
    )
    assert (
        len(receipt.drafts) == 1
        and receipt.drafts[0].audit_ref.content_schema == "context-transform-audit/1"
    )
    assert (
        len(native.channel.sent) == frames
        and native.loader.session.calls == 0
        and native.loader.loads == 1
    )
