"""Actual isolated production declaration callers; synthetic resource transports."""

import json
from pathlib import Path
import pytest
import production_actor_inputs as actual
import production_task_plan as plans
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.bootstrap.actor_context_policy import (
    ACTOR_CONTEXT_IMPLEMENTATION_FILES,
    ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
)
from production_inputs import OriginalDocuments
from source_actor_context_fixtures import source_context_case

RUNTIME = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1/runtime-adaptive-observation-candidate"
)


def test_actual_map_static_and_published_constructors_bind_same_explicit_adaptive_policy_before_model_or_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Path(actual.__file__).parent == Path(plans.__file__).parent == RUNTIME
    c = source_context_case(tmp_path / "case", monkeypatch)
    spec = c.actor.spec
    # Use the fixture's original run-level operation, never a historical owner.
    from test_run_journal import command

    op = command("actual-adaptive-configuration")
    op = op.model_copy(
        update={
            "run_id": spec.token.owner.run_id,
            "owner_id": spec.token.owner.owner_id,
        }
    )
    controls = c.actor.controls
    control = controls.bind(op)
    documents = OriginalDocuments(c.actor.evidence, controls)
    binding = ActorModelBinding.model_validate_json(
        c.actor.evidence.read(spec.model_binding_ref, control)
    )
    files = {
        name: "a" * 64
        for name in (
            *ACTOR_CONTEXT_IMPLEMENTATION_FILES,
            *ACTOR_ADAPTIVE_IMPLEMENTATION_FILES,
        )
    }
    software = json.dumps(
        dict(
            schema_version="framework-check/3",
            passed=True,
            source_stable_during_checks=True,
            files=files,
        )
    ).encode()
    software_ref = documents.raw(software, "framework-check/3", op)
    sent = len(c.channel.sent)
    frozen = actual.publish_known_actor_inputs(
        spec, binding, c.params, software_ref, software, documents, op
    )
    legacy_constructor = plans.freeze_actor_inputs(
        spec, c.params, software_ref, software, documents, op
    )
    assert legacy_constructor == frozen
    selected = plans.selected_observation_projection()
    assert isinstance(selected, AdaptiveObservationProjection)
    assert (
        frozen.policy.actor_projection
        == frozen.context.policy.actor_projection
        == selected
    )
    assert frozen.context.policy.schema_version == "context-projection-policy/2"
    assert (
        selected.read_policy.switch_tokens,
        selected.read_policy.body_target_tokens,
        selected.read_policy.body_max_tokens,
    ) == (24576, 6000, 8000)
    assert frozen.context.policy.candidate_order == ("compact_full_ax", "local_ax")
    assert len(c.channel.sent) == sent and c.session.calls == 0
    # Incomplete adaptive software pins reject before any declaration publication.
    files.pop("src/lab_generate_skill/adapters/plans/observation_reads.py")
    bad = json.dumps(
        dict(
            schema_version="framework-check/3",
            passed=True,
            source_stable_during_checks=True,
            files=files,
        )
    ).encode()
    bad_ref = documents.raw(bad, "framework-check/3", op)

    def no_publish(*args: object, **kwargs: object) -> None:
        raise AssertionError("Invalid static input reached a publication effect")

    monkeypatch.setattr(documents, "raw", no_publish)
    monkeypatch.setattr(documents, "put", no_publish)
    with pytest.raises(EvidenceIntegrityError):
        actual.publish_known_actor_inputs(
            spec, binding, c.params, bad_ref, bad, documents, op
        )
    c.client.close(control)
