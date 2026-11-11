"""Invalid task scope must stop the native entry before allocating /tmp."""

from pathlib import Path
from typing import Any
import pytest
from evidence_control_fixtures import EvidenceFixtureStore
from map_source_inputs import engineering_scope, check_source_scope
from map_source_live import run_source
from map_navigation_source_fixtures import selection
from map_navigation_group_cases import SOURCES
from source_task_hooks import SourceTaskHooks
from site_worker_fixtures import configuration


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "wrong-type",
        "owner",
        "task",
        "heldout",
        "empty-attempt",
        "long-attempt",
        "empty-context",
    ],
)
def test_invalid_native_entry_scope_does_not_allocate_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    owner = configuration(job_id="4752096").token.owner
    chosen = selection(SOURCES[0])
    scope: Any = engineering_scope(owner, chosen)
    if fault == "empty":
        scope = None
    elif fault == "wrong-type":
        scope = {}
    elif fault == "owner":
        scope = scope.model_copy(
            update={"owner": owner.model_copy(update={"owner_id": "foreign"})}
        )
    elif fault == "task":
        scope = scope.model_copy(
            update={"task": selection(SOURCES[1]).public_template.identity}
        )
    elif fault == "heldout":
        scope = scope.model_copy(
            update={"task": scope.task.model_copy(update={"split": "test"})}
        )
    elif fault in ("empty-attempt", "long-attempt"):
        scope = scope.model_copy(
            update={"attempt_id": "" if fault == "empty-attempt" else "a" * 257}
        )
    else:
        scope = scope.model_copy(update={"context_id": ""})
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    hooks = SourceTaskHooks(
        owner,
        EvidenceFixtureStore(evidence),
        ("click",),
        lambda *args: None,
        lambda *args: None,
        map_selection=chosen,
    )
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> str:
        calls.append("mkdtemp")
        pytest.fail("Rejected scope reached /tmp allocation")

    monkeypatch.setattr("map_source_live.tempfile.mkdtemp", forbidden)
    absent: Any = None
    with pytest.raises((ValueError, TypeError)):
        run_source(
            absent, tmp_path, monkeypatch, hooks, scope=scope, evidence_root=evidence
        )
    assert not calls


@pytest.mark.parametrize("selected_navigation", [True, False])
def test_valid_explicit_scope_reaches_only_declared_allocation_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selected_navigation: bool
) -> None:
    owner = configuration(job_id="4752096").token.owner
    chosen = selection(SOURCES[0]) if selected_navigation else None
    scope = engineering_scope(owner, chosen).model_copy(
        update={
            "attempt_id": "candidate-0-first",
            "context_id": "qualified-original-context",
        }
    )
    assert check_source_scope(owner, scope, chosen) == scope
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    hooks = SourceTaskHooks(
        owner,
        EvidenceFixtureStore(evidence),
        ("click",),
        lambda *args: None,
        lambda *args: None,
        map_selection=chosen,
    )

    class AllocationReached(RuntimeError):
        pass

    def stop_before_effect(*args: object, **kwargs: object) -> str:
        raise AllocationReached(
            "valid original scope admitted to allocation boundary only"
        )

    monkeypatch.setattr("map_source_live.tempfile.mkdtemp", stop_before_effect)
    absent: Any = None
    with pytest.raises(AllocationReached):
        run_source(
            absent, tmp_path, monkeypatch, hooks, scope=scope, evidence_root=evidence
        )


@pytest.mark.parametrize("bad", [{}, [], True, ""])
def test_invalid_selection_type_has_no_engineering_scope_default(bad: Any) -> None:
    owner = configuration(job_id="4752096").token.owner
    with pytest.raises(TypeError):
        engineering_scope(owner, bad)
    with pytest.raises(TypeError):
        check_source_scope(owner, engineering_scope(owner, None), bad)
