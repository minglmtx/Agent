"""Pure freeze from the accepted exact software document, not current pointers."""

import hashlib
import json
import unicodedata
from lab_generate_skill.domain.actor_projection import (
    ActorProjectionConfiguration,
    MapRailsDiagnosticProjection,
    MapRailsAddressableProjection,
    AdaptiveObservationProjection,
    actor_projection_configuration,
)
from lab_generate_skill.domain.context_projection import ContextProjectionPolicy
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.actor.context_source import (
    ACTOR_PROTECTION_RULES,
    ADAPTIVE_ACTOR_PROTECTION_RULES,
)
from lab_generate_skill.adapters.processes.wire_json import json_object

ACTOR_CONTEXT_IMPLEMENTATION_FILES = (
    "src/lab_generate_skill/domain/adaptive_candidates.py",
    "src/lab_generate_skill/domain/actor_prompt.py",
    "src/lab_generate_skill/domain/context_projection.py",
    "src/lab_generate_skill/actor/history_layout.py",
    "src/lab_generate_skill/actor/response.py",
    "src/lab_generate_skill/actor/decisions.py",
    "src/lab_generate_skill/application/actor_loop_inputs.py",
    "src/lab_generate_skill/application/context_preparation.py",
    "src/lab_generate_skill/application/context_review.py",
    "src/lab_generate_skill/domain/actor_context.py",
    "src/lab_generate_skill/domain/context_preparation.py",
    "src/lab_generate_skill/domain/context_transformation.py",
    "src/lab_generate_skill/actor/context_source.py",
    "src/lab_generate_skill/actor/context_projection.py",
    "src/lab_generate_skill/actor/context_protection.py",
    "src/lab_generate_skill/actor/context_ax_protection.py",
    "src/lab_generate_skill/actor/message_layout.py",
    "src/lab_generate_skill/actor/instructions.py",
    "src/lab_generate_skill/domain/browser_action_catalog.py",
    "src/lab_generate_skill/actor/map_rails_projection.py",
    "src/lab_generate_skill/actor/rails_diagnostic_ax.py",
    "src/lab_generate_skill/application/actor_context_preparation.py",
    "src/lab_generate_skill/application/actor_context_review.py",
    "src/lab_generate_skill/application/actor_context_review_inputs.py",
    "src/lab_generate_skill/bootstrap/actor_context_runtime.py",
    "src/lab_generate_skill/bootstrap/actor_context_review.py",
    "src/lab_generate_skill/bootstrap/actor_context_policy.py",
)

# Extra implementation pins are consumed only by the explicitly selected
# adaptive strategy. Historical full/structural policy bytes keep their scope.
ACTOR_ADAPTIVE_IMPLEMENTATION_FILES = (
    "src/lab_generate_skill/actor/tool_contract.py",
    "src/lab_generate_skill/actor/proposal_correction.py",
    "src/lab_generate_skill/actor/tool_example_binding.py",
    "src/lab_generate_skill/domain/actor_tool_definitions.py",
    "src/lab_generate_skill/policies/actor_tool_schemas.py",
    "src/lab_generate_skill/policies/actor_proposal_identity.py",
    "src/lab_generate_skill/policies/actor_proposal_syntax.py",
    "src/lab_generate_skill/domain/observation_read_choice.py",
    "src/lab_generate_skill/actor/protocol_examples.py",
    "src/lab_generate_skill/policies/observation_navigation.py",
    "src/lab_generate_skill/domain/actor_projection.py",
    "src/lab_generate_skill/domain/actor_observation_source.py",
    "src/lab_generate_skill/domain/actor_observation_view.py",
    "src/lab_generate_skill/domain/observation_read.py",
    "src/lab_generate_skill/domain/observation_read_policy.py",
    "src/lab_generate_skill/domain/observation_read_progress.py",
    "src/lab_generate_skill/domain/observation_read_return.py",
    "src/lab_generate_skill/domain/observation_read_geometry.py",
    "src/lab_generate_skill/domain/observation_read_fact.py",
    "src/lab_generate_skill/domain/trace.py",
    "src/lab_generate_skill/domain/trace_events.py",
    "src/lab_generate_skill/ports/actor_context.py",
    "src/lab_generate_skill/ports/observation_reads.py",
    "src/lab_generate_skill/actor/adaptive_projection.py",
    "src/lab_generate_skill/actor/adaptive_layout.py",
    "src/lab_generate_skill/actor/adaptive_protection.py",
    "src/lab_generate_skill/actor/observation_read_response.py",
    "src/lab_generate_skill/policies/actor_observation_selection.py",
    "src/lab_generate_skill/policies/observation_index.py",
    "src/lab_generate_skill/policies/observation_pages.py",
    "src/lab_generate_skill/policies/observation_search.py",
    "src/lab_generate_skill/policies/observation_display.py",
    "src/lab_generate_skill/policies/observation_protection.py",
    "src/lab_generate_skill/application/adaptive_context_preparation.py",
    "src/lab_generate_skill/application/observation_read.py",
    "src/lab_generate_skill/application/observation_read_review.py",
    "src/lab_generate_skill/application/actor_read_review.py",
    "src/lab_generate_skill/adapters/plans/actor_observation_sources.py",
    "src/lab_generate_skill/adapters/plans/recorded_observation_sources.py",
    "src/lab_generate_skill/adapters/plans/observation_reads.py",
    "src/lab_generate_skill/adapters/plans/actor_closed_review.py",
    "src/lab_generate_skill/adapters/plans/reading_bodies.py",
    "src/lab_generate_skill/adapters/models/observation_body_counts.py",
    "src/lab_generate_skill/adapters/models/transformers_actor_session.py",
)


def accepted_actor_context_policy(
    software_ref: EvidenceRef, software: bytes, projection: ActorProjectionConfiguration
) -> ContextProjectionPolicy:
    software_ref = EvidenceRef.model_validate(software_ref)
    projection = actor_projection_configuration(projection)
    if (
        (software_ref.visibility, software_ref.content_schema, software_ref.media_type)
        != ("private", "framework-check/3", "application/json")
        or type(software) is not bytes
        or not 0 < len(software) <= 16 * 1024**2
        or (len(software), hashlib.sha256(software).hexdigest())
        != (software_ref.size_bytes, software_ref.sha256)
    ):
        raise EvidenceIntegrityError(
            "Original accepted bounded software evidence required"
        )
    value = json_object(software)
    if (
        value.get("schema_version") != "framework-check/3"
        or value.get("passed") is not True
        or value.get("source_stable_during_checks") is not True
    ):
        raise EvidenceIntegrityError(
            "Actor software gate not accepted or source unstable"
        )
    adaptive = isinstance(projection, AdaptiveObservationProjection)
    required_files = ACTOR_CONTEXT_IMPLEMENTATION_FILES + (
        ACTOR_ADAPTIVE_IMPLEMENTATION_FILES if adaptive else ()
    )
    files = value.get("files")
    if type(files) is not dict or any(
        type(files.get(name)) is not str
        or len(files[name]) != 64
        or any(c not in "0123456789abcdef" for c in files[name])
        for name in required_files
    ):
        raise EvidenceIntegrityError(
            "Actor software gate omits exact context implementation pins"
        )
    pins = {name: files[name] for name in required_files}
    implementation = hashlib.sha256(
        json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if isinstance(projection, AdaptiveObservationProjection):
        if projection.read_policy.unicode_version != unicodedata.unidata_version:
            raise EvidenceIntegrityError(
                "Adaptive search Unicode implementation differs from its frozen policy"
            )
        return ContextProjectionPolicy(
            schema_version="context-projection-policy/3",
            role="actor",
            policy_id="actor-adaptive-public-context-v1",
            implementation_sha256=implementation,
            software_evidence_ref=software_ref,
            protected_rules=ADAPTIVE_ACTOR_PROTECTION_RULES,
            candidate_order=("compact_full_ax", "local_ax"),
            allow_identity_fallback=False,
            forced_kind=None,
            actor_projection=projection,
        )
    structural = isinstance(
        projection, (MapRailsDiagnosticProjection, MapRailsAddressableProjection)
    )
    return ContextProjectionPolicy(
        role="actor",
        policy_id="actor-public-context-v1",
        implementation_sha256=implementation,
        software_evidence_ref=software_ref,
        protected_rules=ACTOR_PROTECTION_RULES,
        candidate_order=("identity", "structural_ax") if structural else ("identity",),
        allow_identity_fallback=True,
        forced_kind=None,
        actor_projection=projection if structural else None,
    )
