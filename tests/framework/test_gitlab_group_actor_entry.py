"""Fixed Group forwarding and refusal before any model/site operation."""

import json
from pathlib import Path
from typing import Any
import pytest
import gitlab_group_actor_live as entry
from gitlab_source_selection import (
    GitlabSourceSelection,
    group_selection,
    ssh_selection,
)


def test_actual_group_entry_uses_current_helper_and_exact_original_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    installed: Any = object()

    def actual(
        value: Any, root: Path, patch: pytest.MonkeyPatch, **kwargs: Any
    ) -> None:
        assert value is installed and root == tmp_path and patch is monkeypatch
        calls.append(kwargs)

    monkeypatch.setattr(entry, "run_actual_actor_business_chain", actual)
    entry.test_actual_private_group_actor_business_chain(
        installed, tmp_path, monkeypatch
    )
    assert len(calls) == 1 and calls[0]["site_id"] == "gitlab"
    selected = calls[0]["gitlab_selection"]
    assert selected.group and selected.reference().sha256 == entry.CONTRACT_SHA
    assert selected.public_template.identity.source_task_id == entry.SOURCE


@pytest.mark.parametrize("bad", [None, {}, "", 1, False])
def test_invalid_selection_is_refused_before_shared_native_entry(
    bad: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(entry, "group_selection", lambda: bad)
    monkeypatch.setattr(
        entry, "run_actual_actor_business_chain", lambda *a, **k: calls.append(True)
    )
    absent: Any = None
    with pytest.raises(TypeError):
        entry.test_actual_private_group_actor_business_chain(
            absent, tmp_path, monkeypatch
        )
    assert not calls


@pytest.mark.parametrize("fault", ["ssh", "different-contract"])
def test_other_family_or_contract_cannot_consume_selected_engineering_execution(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = ssh_selection()
    if fault == "different-contract":
        original = group_selection()
        native = json.loads(original.native)
        native["goal"] = "Another private group goal"
        public = original.public_template.model_copy(update={"goal": native["goal"]})
        selected = GitlabSourceSelection(json.dumps(native).encode(), public)
    calls: list[bool] = []
    monkeypatch.setattr(entry, "group_selection", lambda: selected)
    monkeypatch.setattr(
        entry, "run_actual_actor_business_chain", lambda *a, **k: calls.append(True)
    )
    absent: Any = None
    with pytest.raises(ValueError):
        entry.test_actual_private_group_actor_business_chain(
            absent, tmp_path, monkeypatch
        )
    assert not calls


def test_group_independent_entry_requires_exact_task_on_current_readonly_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setenv("LAB_GROUP_ACTOR_ATTEMPT_ROOT", str(tmp_path))

    def review(root: Path, **kwargs: Any) -> None:
        assert root == tmp_path
        calls.append(kwargs)

    monkeypatch.setattr(entry, "review_actual_actor_attempt", review)
    entry.test_independent_actual_private_group_actor_attempt()
    assert calls == [
        {
            "gitlab": True,
            "expected_identity": group_selection().public_template.identity,
        }
    ]
