"""Combination failures stay visible while allowing original safe cleanup."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
import source_actor_callbacks as target
from actor_context_projection_fixtures import actor_projection_case


@pytest.mark.parametrize(
    "phase", ["none", "actor", "page", "evaluation", "unknown_browser"]
)
def test_original_failures_retained_and_judgment_receives_same_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    calls: list[str] = []
    sentinel = RuntimeError("original failure")
    dummy: Any = SimpleNamespace(
        engine=SimpleNamespace(
            state="broken" if phase == "unknown_browser" else "ready"
        )
    )
    policy = actor_projection_case().policy
    callbacks = target.SourceActorCallbacks(
        dummy, dummy, dummy, tmp_path, context_policy=policy
    )

    def execute(
        *args: Any, max_interactions: int, context_policy: Any, projection: Any = None
    ) -> tuple[dict[str, Any], BaseException | None]:
        assert max_interactions == 16 and projection is None
        assert context_policy == policy
        calls.append("actor")
        return {"trace_ref": "retained"}, sentinel if phase == "actor" else None

    def page(*args: Any) -> Any:
        calls.append("page")
        if phase == "page":
            raise sentinel
        return SimpleNamespace(model_dump=lambda **kwargs: {"original_page": True})

    def judge(source: Any, facts: Any, actor: Any) -> dict[str, Any]:
        calls.append("evaluation")
        assert actor is callbacks.facts and actor["trace_ref"] == "retained"
        if phase == "evaluation":
            raise sentinel
        return {"evaluation": {"status": "unknown" if phase != "none" else "failure"}}

    monkeypatch.setattr(target, "execute_source_actor", execute)
    monkeypatch.setattr(target, "final_page", page)
    monkeypatch.setattr(target, "judge_source_task", judge)
    observed: dict[str, Any] = {}
    site: dict[str, Any] = {}
    callbacks.execute(dummy, dummy, dummy, observed)
    # Actual caller closes browser before invoking this; no exception hides the
    # original resource manager's closure or causes a retry here.
    callbacks.evaluate(dummy, site)
    assert observed["actor"] is site["actor"] is callbacks.facts
    assert calls == (
        ["actor", "evaluation"]
        if phase == "unknown_browser"
        else ["actor", "page", "evaluation"]
    )
    assert callbacks.errors == (
        [sentinel] if phase in ("actor", "page", "evaluation") else []
    )
    if callbacks.errors:
        assert callbacks.facts["errors"][0]["error"]


def test_assembly_failure_and_capture_failure_both_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dummy: Any = SimpleNamespace(engine=SimpleNamespace(state="terminal"))
    policy = actor_projection_case().policy
    callbacks = target.SourceActorCallbacks(
        dummy, dummy, dummy, tmp_path, context_policy=policy
    )
    first, second = ValueError("assembly"), TimeoutError("capture")

    def execute(
        *args: Any, max_interactions: int, context_policy: Any, projection: Any = None
    ) -> Any:
        assert max_interactions == 16 and projection is None
        assert context_policy == policy
        raise first

    def page(*args: Any) -> Any:
        raise second

    monkeypatch.setattr(target, "execute_source_actor", execute)
    monkeypatch.setattr(target, "final_page", page)
    callbacks.execute(dummy, dummy, dummy, {})
    assert callbacks.errors == [first, second]
    assert [e["phase"] for e in callbacks.facts["errors"]] == ["actor", "page_capture"]
