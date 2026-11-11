"""Pure pre-start declaration and actual acquiring facts on original preparation."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.task_preparation import SiteTaskPreparationPlan
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.errors import OwnershipConflict, DispatchAlreadyCommitted
from lab_generate_skill.adapters.sites.task_preparation import (
    TaskPreparationUnconfirmed,
)
from map_task_preparation_port_fixtures import preparation_case
from task_execution_fixtures import task_case
from test_task_preparation_admission import declaration
from site_instance_fixtures import node_path as node_path


def test_pure_declaration_has_no_predicted_startup_and_explicitly_refuses_old_wire(
    tmp_path: Path,
) -> None:
    c = task_case(tmp_path / "plan")
    pure = declaration(c)
    assert pure.schema_version == "site-task-preparation-plan/2"
    assert "site_started_ref" not in pure.model_dump()
    assert c.model.calls == c.browser.calls == 0
    assert SiteTaskPreparationPlan.model_validate_json(pure.model_dump_json()) == pure
    with pytest.raises(ValueError):
        SiteTaskPreparationPlan.model_validate(
            {**pure.model_dump(), "site_started_ref": pure.site_spec_ref}
        )
    with pytest.raises(ValueError):
        SiteTaskPreparationPlan.model_validate(
            {**pure.model_dump(), "schema_version": "site-task-preparation-plan/1"}
        )


def test_actual_binding_published_only_by_original_acquire_and_reused_by_prepared(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with preparation_case(node_path, monkeypatch) as p:
        original_plan = p.plan.model_dump_json()
        assert p.preparation.state.acquired_ref is None and p.requests == []
        acquired = p.acquire()
        state = p.preparation.state
        assert state.acquired_ref is not None and state.acquired_ref in acquired
        actual = SiteTaskAcquired.model_validate_json(
            p.original.resource.evidence.read(state.acquired_ref)
        )
        assert actual == state.original_acquired()
        assert actual.operation == p.operation("acquiring")
        assert actual.declaration_ref == p.plan.declaration_ref
        assert (
            p.original.resource.evidence.read(actual.site_started_ref)
            == p.site.site.model_dump_json().encode()
        )
        assert p.plan.model_dump_json() == original_plan
        p.prepare()
        assert (
            state.result is not None and state.result.acquired_ref == state.acquired_ref
        )
        assert [x.action for x in p.requests] == ["snapshot", "prepare"]


@pytest.mark.parametrize(
    "field",
    [
        "declaration_ref",
        "resource_intent_ref",
        "resource_acquired_ref",
        "site_started_ref",
    ],
)
def test_saved_binding_rejects_in_memory_ref_substitution_before_snapshot(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    with preparation_case(node_path, monkeypatch) as p:
        p.acquire()
        state = p.preparation.state
        actual = state.original_acquired()
        state.acquired = actual.model_copy(
            update={
                field: getattr(actual, field).model_copy(update={"sha256": "f" * 64})
            }
        )
        with pytest.raises(TaskPreparationUnconfirmed) as caught:
            p.prepare()
        assert isinstance(caught.value.primary, OwnershipConflict)
        assert p.requests == []


def test_binding_commit_ack_loss_is_preserved_without_native_or_reacquire(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with preparation_case(node_path, monkeypatch) as p:
        store = p.original.resource.evidence
        original = store.put
        saved = []
        error = OSError("original acquired binding reply lost")

        def lost(data: bytes, metadata: Any, *args: Any, **kwargs: Any) -> Any:
            ref = original(data, metadata, *args, **kwargs)
            if metadata.content_schema == "site-task-acquired/1":
                saved.append(ref)
                raise error
            return ref

        monkeypatch.setattr(store, "put", lost)
        with pytest.raises(TaskPreparationUnconfirmed) as caught:
            p.acquire()
        assert caught.value.primary is error and len(saved) == 1
        assert getattr(error, "preparation_candidate_reference") == saved[0]
        assert (
            p.preparation.state.acquired is not None
            and p.preparation.state.acquired_ref is None
        )
        assert p.requests == []
        with pytest.raises(DispatchAlreadyCommitted):
            p.acquire()


@pytest.mark.parametrize("bad", [None, "", [], {}, True, 0])
def test_empty_or_wrong_acquired_packet_rejected(bad: Any) -> None:
    with pytest.raises(ValueError):
        SiteTaskAcquired.model_validate(bad)
