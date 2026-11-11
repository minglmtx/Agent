"""Affected viewport resolution and independent review boundaries only."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from lab_generate_skill.adapters.plans.observation_viewports import read_public_viewport
from lab_generate_skill.adapters.plans.recorded_observation_sources import (
    RecordedActorObservationSources,
)
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.domain.actor_context import ActorContextConfiguration
from lab_generate_skill.domain.actor_observation_source import ActorObservationSource
from lab_generate_skill.domain.actor_projection import AdaptiveObservationProjection
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.observation import (
    ObservationArtifact,
    ResolvedObservation,
)
from lab_generate_skill.domain.observation_viewport import (
    VIEWPORT_METADATA,
    VIEWPORT_NAME,
    MAX_VIEWPORT_BYTES,
)
from lab_generate_skill.ports.lifecycle import OperationControl

from context_budget_fixtures import profile
from evidence_control_fixtures import EvidenceFixtureStore
from test_adaptive_context_repair import pure_case
from test_public_viewport_handoff import index_for, window, projected
from test_slurm_commands import guard
from browsergym_fixtures import operation, spec


def test_resolved_text_cannot_rebind_inline_capture_even_with_matching_metadata() -> (
    None
):
    _, observed, viewport = index_for()
    with pytest.raises(EvidenceIntegrityError, match="inline"):
        viewport.require_observation(
            observed.model_copy(update={"text": "different full body"}), observed.text
        )


@pytest.mark.parametrize("kind", ["oversized", "corrupt", "legacy"])
def test_reader_bounds_complete_bytes_and_explicit_legacy_branch(kind: str) -> None:
    _, observed, viewport = index_for()

    class Reader:
        calls = 0

        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            control.checkpoint()
            self.calls += 1
            return b"corrupt"

    reader = Reader()
    if kind == "oversized":
        ref = viewport.reference.model_copy(
            update={"size_bytes": MAX_VIEWPORT_BYTES + 1}
        )
        observed = observed.model_copy(
            update={
                "artifacts": (ObservationArtifact(name=VIEWPORT_NAME, reference=ref),)
            }
        )
    elif kind == "legacy":
        observed = observed.model_copy(update={"artifacts": ()})
    resolved = ResolvedObservation(record=observed, text=observed.text)
    if kind == "legacy":
        assert read_public_viewport(resolved, reader, guard(10)) is None
    else:
        with pytest.raises(EvidenceIntegrityError):
            read_public_viewport(resolved, reader, guard(10))
    assert reader.calls == (1 if kind == "corrupt" else 0)


@pytest.mark.parametrize("has_reader", [True, False])
def test_recorded_source_rebuilds_same_measured_index_or_refuses_missing_dependency(
    tmp_path: Path, has_reader: bool
) -> None:
    index, observed, viewport = index_for()
    store = EvidenceFixtureStore(tmp_path)
    assert (
        store.put(viewport.model_dump_json().encode(), VIEWPORT_METADATA)
        == viewport.reference
    )
    old, _, _, selected = pure_case(index.text)
    source = ActorObservationSource.model_validate(
        dict(
            snapshot=index.snapshot,
            policy=index.policy,
            eligibility="local_supported",
            reason="isolated-measured-source",
            tools=("list_regions", "read_region", "search_regions"),
            local_window=window(index),
            window_origin="automatic_initial",
            read_result_ref=None,
            reads_used=0,
            no_progress=0,
        )
    )
    recorded = ActorPublicTurn.model_validate(
        old.model_copy(
            update={
                "task": old.task.model_copy(update={"identity": observed.task}),
                "observation": ResolvedObservation(record=observed, text=observed.text),
                "observation_source": source,
            }
        )
    )
    assert isinstance(selected.actor_projection, AdaptiveObservationProjection)
    selected = selected.model_copy(
        update={
            "actor_projection": selected.actor_projection.model_copy(
                update={"read_policy": index.policy}
            )
        }
    )
    config = ActorContextConfiguration(
        policy=selected, profiles=(profile(provider="fixed-actor-worker"),)
    )
    adapter = RecordedActorObservationSources(config, store if has_reader else None)
    # Only the already validated prefix interface consumed by this pure review
    # boundary is simulated. It grants no execution or original history proof.
    before: Any = SimpleNamespace(
        plan=SimpleNamespace(scope=index.snapshot.scope),
        project=lambda: SimpleNamespace(
            current_observation=lambda plan: index.snapshot.observation_ref, turns=()
        ),
    )
    request: Any = SimpleNamespace(scope=index.snapshot.scope)
    if has_reader:
        adapter.verify_public_source(
            request,
            before,
            operation(spec(), "viewport-review"),
            recorded,
            recorded,
            control=guard(30),
        )
        rebuilt = adapter.index_for_public(recorded)
        assert (
            rebuilt is not None
            and rebuilt.viewport == viewport
            and rebuilt.snapshot == index.snapshot
        )
        adapter.clear_inputs()
    else:
        with pytest.raises(EvidenceIntegrityError, match="reader"):
            adapter.verify_public_source(
                request,
                before,
                operation(spec(), "viewport-review"),
                recorded,
                recorded,
                control=guard(30),
            )


def test_geometry_publication_failure_never_publishes_dangling_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed, viewport, frozen = projected()
    readout = BrowserReadout.model_validate_json(json.dumps(frozen["readout"]))
    readout = readout.model_copy(update={"observation": observed})
    store = EvidenceFixtureStore(tmp_path)
    calls: list[str] = []
    original = store.put

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        calls.append(metadata.content_schema)
        if metadata.content_schema == "observation-viewport/1":
            raise OSError("injected viewport publication failure")
        return original(data, metadata, control)

    monkeypatch.setattr(store, "put", put)
    raw: Any = SimpleNamespace()
    source: Any = SimpleNamespace(viewport=viewport)
    session = EvidenceBrowserSession(raw, store, viewport_source=source)
    with pytest.raises(OSError, match="publication"):
        session._publish(readout, guard(10))
    assert calls == ["observation-viewport/1"]
