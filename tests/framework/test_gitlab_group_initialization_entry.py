"""No-Actor entry callbacks read only the already-authoritative initial binding."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence import EvidenceMetadata
from gitlab_source_selection import group_selection
from gitlab_group_initialization_live import observe_only_group, no_judgment


@pytest.mark.parametrize(
    "fault", ["none", "missing-selection", "unknown-baseline", "foreign-initial"]
)
def test_initialization_only_observer_never_needs_model_action_or_writer(
    tmp_path: Path,
    fault: str,
) -> None:
    selected = group_selection()
    ref = evidence_reference(
        b"{}",
        EvidenceMetadata(
            media_type="application/json",
            visibility="public",
            producer="explicit-observer-unit",
            content_schema="observation/1",
        ),
    )
    public = selected.public_at("http://127.0.0.1:12001/", None)
    source: Any = SimpleNamespace(
        gitlab_selection=None if fault == "missing-selection" else selected,
        saved={
            "baseline": SimpleNamespace(
                status="unknown" if fault == "unknown-baseline" else "ready",
                observation_ref=ref,
            )
        },
        native=SimpleNamespace(public=public),
    )
    browser: Any = SimpleNamespace(
        spec=SimpleNamespace(
            configuration=SimpleNamespace(spec=SimpleNamespace(task=public))
        )
    )
    session: Any = SimpleNamespace(
        observation_ref=(
            ref.model_copy(update={"sha256": "f" * 64})
            if fault == "foreign-initial"
            else ref
        )
    )
    observed: dict[str, Any] = {}
    if fault == "none":
        observe_only_group(source, browser, session, observed)
        assert observed["group_no_actor_observer"]["Actor_calls"] == 0
        assert observed["group_no_actor_observer"][
            "original_initial_ref"
        ] == ref.model_dump(mode="json")
    else:
        with pytest.raises(AssertionError):
            observe_only_group(source, browser, session, observed)
        assert observed == {}
    assert list(tmp_path.iterdir()) == []


def test_initialization_only_scope_rejects_task_judgment() -> None:
    absent: Any = None
    with pytest.raises(AssertionError, match="cannot evaluate an Actor task"):
        no_judgment(absent, {})
