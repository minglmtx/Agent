"""Real frozen scroll inputs through current public publication/wire/selection.

The BrowserGym capture was executed once in 4971802. These consumer tests never
start a browser or model; wire edges are engineering fixtures, not authority.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from lab_generate_skill.adapters.browsergym.public_viewport import public_viewport
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.browsergym.worker_protocol import BrowserWorkerReply
from lab_generate_skill.adapters.plans.observation_viewports import read_public_viewport
from lab_generate_skill.adapters.plans.observations import ObservationReader
from lab_generate_skill.actor.adaptive_projection import AdaptiveActorProjector
from lab_generate_skill.actor.adaptive_protection import AdaptiveActorProtection
from lab_generate_skill.domain.actor_observation_source import ActorObservationSource
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.actor_prompt import ActorPrompt, ActorPublicTurn
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.observation import (
    Observation,
    ResolvedObservation,
    ObservationArtifact,
)
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    ReadObservationRegions,
    ObservationRegionRange,
)
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    VIEWPORT_NAME,
    VIEWPORT_METADATA,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.policies.observation_index import (
    index_public_ax,
    ObservationIndex,
)
from lab_generate_skill.policies.observation_navigation import with_complete_navigation
from lab_generate_skill.policies.observation_pages import observation_page
from lab_generate_skill.policies.observation_search import index_literal_search
from lab_generate_skill.policies.observation_viewport import with_public_viewport
from lab_generate_skill.ports.lifecycle import OperationControl

from browser_worker_fixtures import case as worker_case
from browsergym_fixtures import operation
from evidence_control_fixtures import EvidenceFixtureStore
from observation_read_fixtures import policy
from retrieval_fixtures import reference
from test_adaptive_context_repair import pure_case
from test_slurm_commands import guard

W = Path(__file__).resolve().parents[4]
FROZEN = (
    W
    / "experiments/framework-combined-release-20261030-v1/viewport-capture-stage-v2-4971802"
)


def captured(label: str = "before-scroll") -> dict[str, Any]:
    proof = json.loads((FROZEN / "capture-stage.json").read_bytes())
    assert (
        proof["passed"]
        and proof["browser_closed"]
        and proof["production_site_calls"] == 0
    )
    row = next(row for row in proof["captures"] if row["label"] == label)
    raw = Path(row["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    value: dict[str, Any] = json.loads(raw)
    return value


def projected(
    label: str = "before-scroll",
) -> tuple[Observation, ObservationViewport, dict[str, Any]]:
    frozen = captured(label)
    observed = Observation.model_validate_json(json.dumps(frozen["observation"]))
    raw = dict(
        screenshot=SimpleNamespace(shape=tuple(frozen["screenshot_shape"])),
        extra_element_properties=frozen["extra_element_properties"],
    )
    record, viewport = public_viewport(raw, observed)
    assert record.text == observed.text and record.sequence == observed.sequence
    return record, viewport, frozen


def index_for(
    label: str = "before-scroll",
) -> tuple[ObservationIndex, Observation, ObservationViewport]:
    observed, viewport, frozen = projected(label)
    state = StateScope.model_validate_json(json.dumps(frozen["readout"]["scope"]))
    resolved = ResolvedObservation(record=observed, text=observed.text)
    index = index_public_ax(
        reference(observed, "observation/1", "public"),
        observed.model_dump_json().encode(),
        resolved,
        state,
        policy(directory_entries=1),
        viewport=viewport,
    )
    return index, observed, viewport


def window(index: ObservationIndex) -> Any:
    request = ListObservationRegions(
        request_id="automatic-initial-directory",
        snapshot=index.snapshot,
        output_tokens=index.policy.body_max_tokens,
    )
    return observation_page(
        index,
        request,
        offset=0,
        limit=1,
        next_cursor="fixture-directory-next",
        search=index_literal_search(index),
    ).payload


@pytest.mark.parametrize(
    "label,shown,unshown",
    [
        ("before-scroll", "Top public target", "Bottom public target"),
        ("after-scroll", "Bottom public target", "Top public target"),
    ],
)
def test_same_capture_geometry_drives_viewport_and_full_source_stays_readable(
    label: str, shown: str, unshown: str
) -> None:
    index, observed, viewport = index_for(label)
    selected = with_public_viewport(
        index, with_complete_navigation(index, window(index))
    )
    body = "".join(fragment.text for fragment in selected.fragments)
    assert shown in body and unshown not in body
    assert "Navigation entry" in body
    assert shown in index.text and unshown in index.text
    assert (viewport.width, viewport.height) == (1280, 720)
    # Omitted off-screen content remains available under the same exact snapshot.
    node = next(node for node in index.nodes if unshown in index.lines[node.line])
    request = ReadObservationRegions(
        request_id="read-offscreen-explicitly",
        snapshot=index.snapshot,
        output_tokens=1000,
        ranges=(
            ObservationRegionRange(
                region_id=f"ax-line-{node.line}", unit="whole_region"
            ),
        ),
    )
    result = observation_page(
        index,
        request,
        offset=0,
        limit=index.policy.page_units,
        next_cursor="fixture-next",
        search=index_literal_search(index),
    ).payload
    assert unshown in "".join(fragment.text for fragment in result.fragments)
    viewport.require_observation(observed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", 999),
        ("context_id", "other-context"),
        ("attempt_id", "other-attempt"),
        ("tab_id", "other-tab"),
        ("active_url", "http://127.0.0.1/different"),
        ("text_sha256", "f" * 64),
    ],
)
def test_foreign_or_stale_viewport_rejected_without_structural_fallback(
    field: str, value: object
) -> None:
    _, observed, viewport = index_for()
    changed = viewport.model_copy(update={field: value})
    observed = observed.model_copy(
        update={
            "artifacts": (
                ObservationArtifact(name=VIEWPORT_NAME, reference=changed.reference),
            )
        }
    )
    with pytest.raises(EvidenceIntegrityError):
        changed.require_observation(observed)


def test_scroll_new_observation_cannot_reuse_previous_viewport_or_index() -> None:
    first, _, viewport = index_for()
    second, observed, _ = index_for("after-scroll")
    assert first.snapshot.observation_ref != second.snapshot.observation_ref
    assert first.snapshot.sequence == 0 and second.snapshot.sequence == 1
    with pytest.raises(EvidenceIntegrityError):
        viewport.require_observation(observed)
    with pytest.raises(OwnershipConflict, match="snapshot"):
        first.require_snapshot(second.snapshot)


@pytest.mark.parametrize(
    "change",
    ["nan", "infinite", "negative_box", "visibility", "duplicate", "wrong_type"],
)
def test_geometry_types_limits_and_duplicates_are_rejected(change: str) -> None:
    _, _, viewport = index_for()
    value = viewport.model_dump(mode="json")
    if change == "nan":
        value["elements"][0]["visibility"] = float("nan")
    elif change == "infinite":
        value["elements"][0]["box"]["x"] = float("inf")
    elif change == "negative_box":
        value["elements"][0]["box"]["width"] = -1.0
    elif change == "visibility":
        value["elements"][0]["visibility"] = 1.1
    elif change == "duplicate":
        value["elements"].append(value["elements"][0])
    else:
        value["width"] = True
    with pytest.raises((ValidationError, ValueError)):
        ObservationViewport.model_validate_json(json.dumps(value))


def test_projection_excludes_hidden_dom_only_properties_and_missing_geometry_stays_unknown() -> (
    None
):
    frozen = captured()
    observed = Observation.model_validate_json(json.dumps(frozen["observation"]))
    extra = dict(frozen["extra_element_properties"])
    extra["private-hidden-id"] = {
        "visibility": 1.0,
        "bbox": [0, 0, 100, 100],
        "private_answer": "do-not-project",
    }
    node_id = frozen["target_ids"]["Top public target"]
    extra.pop(node_id)
    _, viewport = public_viewport(
        dict(
            screenshot=SimpleNamespace(shape=(720, 1280, 3)),
            extra_element_properties=extra,
        ),
        observed,
    )
    assert (
        "private-hidden-id" not in viewport.model_dump_json()
        and "do-not-project" not in viewport.model_dump_json()
    )
    unknown = next(
        element for element in viewport.elements if element.node_id == node_id
    )
    assert unknown.visibility is None and unknown.box is None


def test_metadata_is_published_and_bounded_reader_rejects_missing_or_corrupt_bytes(
    tmp_path: Path,
) -> None:
    index, observed, viewport = index_for()
    store = EvidenceFixtureStore(tmp_path)
    store.put(viewport.model_dump_json().encode(), VIEWPORT_METADATA)
    observed_ref = store.put(
        observed.model_dump_json().encode(),
        EvidenceMetadata(
            content_schema="observation/1",
            visibility="public",
            media_type="application/json",
            producer="engineering-viewport-consumer",
        ),
    )
    resolved = ObservationReader(store).load(observed_ref, guard(30))
    assert read_public_viewport(resolved, store, guard(30)) == viewport
    with pytest.raises(EvidenceIntegrityError):
        read_public_viewport(resolved, None, guard(30))
    with pytest.raises(EvidenceIntegrityError):
        index_public_ax(
            index.snapshot.observation_ref,
            observed.model_dump_json().encode(),
            resolved,
            index.snapshot.scope,
            index.policy,
        )


def test_current_actor_projection_and_protection_consume_measured_viewport() -> None:
    index, observed, _ = index_for("after-scroll")
    old, _, _, selected_policy = pure_case(index.text)
    public_source = ActorObservationSource.model_validate(
        dict(
            snapshot=index.snapshot,
            policy=index.policy,
            eligibility="local_supported",
            reason="engineering-measured-viewport",
            tools=("list_regions", "read_region", "search_regions"),
            local_window=window(index),
            window_origin="automatic_initial",
            read_result_ref=None,
            reads_used=0,
            no_progress=0,
        )
    )
    public = ActorPublicTurn.model_validate(
        old.model_copy(
            update={
                "task": old.task.model_copy(update={"identity": observed.task}),
                "observation": ResolvedObservation(record=observed, text=observed.text),
                "observation_source": public_source,
            }
        )
    )
    assert isinstance(selected_policy.actor_projection, AdaptiveObservationProjection)
    projection = selected_policy.actor_projection.model_copy(
        update={"read_policy": index.policy}
    )
    selected_policy = selected_policy.model_copy(
        update={"actor_projection": projection}
    )
    source = ActorContextSource(
        scope=index.snapshot.scope,
        candidate_id="viewport-engineering",
        revision_round=0,
        turn_ref=reference(public, "actor-public-turn/2", "public"),
        active_read_ref=None,
    )
    raw = public.model_dump_json().encode()
    drafts = AdaptiveActorProjector(selected_policy, lambda turn: index).project(
        source, raw, selected_policy
    )
    draft = next(
        draft for draft in drafts if draft.candidate_id == "local_ax_navigation"
    )
    checks = AdaptiveActorProtection(selected_policy, lambda turn: index).verify(
        source, raw, draft, selected_policy
    )
    assert all(check.status == "pass" for check in checks)
    prompt = ActorPrompt.model_validate_json(draft.input_bytes)
    body = (
        prompt.observation_view.body(prompt.messages[1].content)
        if prompt.observation_view
        else ""
    )
    assert "Bottom public target" in body and "Top public target" not in body


def test_worker_reply_handoff_and_publication_use_complete_same_capture_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, service, channel, client = worker_case()
    original_value = engine.value
    measured: list[ObservationViewport] = []

    def value(op: Any, action: Any) -> Any:
        result = original_value(op, action)
        observed, viewport, _ = projected(
            "before-scroll" if action is None else "after-scroll"
        )
        # Current wire engineering identities; retained raw page/geometry remain the source.
        assert observed.task == result.observation.task
        observed = observed.model_copy(
            update={
                "context_id": result.scope.context_id,
                "attempt_id": result.scope.attempt_id,
            }
        )
        viewport = viewport.model_copy(
            update={
                "context_id": result.scope.context_id,
                "attempt_id": result.scope.attempt_id,
            }
        )
        observed = observed.model_copy(
            update={
                "artifacts": (
                    ObservationArtifact(
                        name=VIEWPORT_NAME, reference=viewport.reference
                    ),
                )
            }
        )
        viewport.require_observation(observed)
        engine.viewport = viewport  # type: ignore[attr-defined]
        measured.append(viewport)
        engine.last_readout = result.model_copy(update={"observation": observed})
        return engine.last_readout

    monkeypatch.setattr(engine, "value", value)
    store = EvidenceFixtureStore(tmp_path)
    session = EvidenceBrowserSession(client, store, viewport_source=client)
    op = operation(client.spec, "viewport-wire-start")
    initial = session.start(op, control=guard(30))
    assert (
        client.last_reply is not None
        and client.last_reply.schema_version == "browser-worker-reply/4"
    )
    assert client.viewport == measured[0]
    assert (
        ObservationReader(store).load(initial, guard(30)).record.artifacts[0].reference
        == measured[0].reference
    )
    from browser_worker_fixtures import action

    stepped = session.step(
        action(), operation(client.spec, "viewport-wire-next"), control=guard(30)
    )
    assert stepped.before_observation_ref == initial and client.viewport == measured[1]
    assert store.read(measured[1].reference) == measured[1].model_dump_json().encode()
    bad = client.last_reply.model_dump(mode="json")
    bad["viewport"] = measured[0].model_dump(mode="json")
    with pytest.raises((ValidationError, EvidenceIntegrityError)):
        BrowserWorkerReply.model_validate_json(json.dumps(bad))
    session.close(
        op.cleanup("close-viewport-wire", now=datetime.now(timezone.utc), seconds=30),
        control=guard(30),
    )
    assert engine.calls == ["start", "step", "close"] and channel.finishes == 1
