"""Current declarations, explicit attempt scope; no native/model permission."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.map_task_configuration import map_task_configuration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path


def arguments(c: RegisteredMapCase) -> dict[str, Any]:
    cfg = c.configuration
    inputs = cfg.map_inputs
    assert inputs is not None
    return dict(
        runtime=inputs.runtime,
        private=c.private,
        scope=c.scope,
        token=cfg.token,
        installation=cfg.installation,
        origin=inputs.origin if isinstance(inputs, MapNavigationWorkerInputs) else None,
        evidence_root=Path(inputs.evidence_root),
        resource_journal_root=Path(inputs.resource_journal_root),
        artifact_root=Path(inputs.artifact_root),
        max_files=inputs.max_files,
        max_file_bytes=inputs.max_file_bytes,
        max_total_bytes=inputs.max_total_bytes,
    )


@pytest.fixture
def c(node_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RegisteredMapCase]:
    value = RegisteredMapCase(node_path, monkeypatch)
    try:
        yield value
    finally:
        value.close_sockets()


def test_original_MapData_configuration_and_repeat_are_exact(
    c: RegisteredMapCase,
) -> None:
    assert map_task_configuration(**arguments(c)) == c.configuration
    assert map_task_configuration(**arguments(c)) == c.configuration
    assert not c.resource.channels and c.worker is None


@pytest.mark.parametrize("source", SOURCES)
def test_all8_original_scope_and_custom_attempt_change_only_scope(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        values = arguments(c)
        assert map_task_configuration(**values) == c.configuration
        scope = c.scope.model_copy(
            update={
                "attempt_id": "candidate-0-first",
                "context_id": "qualified-current-context",
            }
        )
        changed = map_task_configuration(**{**values, "scope": scope})
        assert changed.map_inputs is not None and c.configuration.map_inputs is not None
        assert changed.map_inputs.scope == scope
        assert changed.model_dump(exclude={"map_inputs"}) == c.configuration.model_dump(
            exclude={"map_inputs"}
        )
        assert changed.map_inputs.model_dump(
            exclude={"scope"}
        ) == c.configuration.map_inputs.model_dump(exclude={"scope"})
        assert not c.resource.channels and c.worker is None
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("runtime", None),
        ("private", {}),
        ("private", []),
        ("scope", ""),
        ("token", False),
        ("installation", {}),
        ("evidence_root", ""),
        ("evidence_root", Path(".")),
        ("resource_journal_root", Path("/tmp/foreign")),
        ("artifact_root", None),
        ("max_files", 0),
        ("max_files", True),
        ("max_files", 10001),
        ("max_file_bytes", -1),
        ("max_file_bytes", None),
        ("max_total_bytes", float("nan")),
        ("max_total_bytes", 2 * 1024**4 + 1),
    ],
)
def test_invalid_inputs_rejected_without_worker(
    c: RegisteredMapCase, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError, OwnershipConflict)):
        map_task_configuration(**{**arguments(c), field: bad})
    assert not c.resource.channels and c.worker is None


@pytest.mark.parametrize(
    "fault", ["owner", "task", "heldout", "instance", "provider", "version", "scope"]
)
def test_foreign_scope_or_allocation_never_declares(
    c: RegisteredMapCase, fault: str
) -> None:
    values = arguments(c)
    if fault == "owner":
        values["scope"] = c.scope.model_copy(
            update={
                "owner": c.scope.owner.model_copy(update={"owner_id": "foreign-owner"})
            }
        )
    elif fault in ("task", "heldout"):
        changes = (
            {"source_task_id": "foreign-source"}
            if fault == "task"
            else {"split": "dev"}
        )
        values["scope"] = c.scope.model_copy(
            update={"task": c.scope.task.model_copy(update=changes)}
        )
    else:
        update: dict[str, Any] = {
            "instance": {"expected_resource_id": "foreign-instance"},
            "provider": {"provider_id": "other-worker"},
            "version": {"provider_version": "5"},
            "scope": {"scope": "attempt", "attempt_id": c.scope.attempt_id},
        }[fault]
        values["token"] = c.configuration.token.model_copy(update=update)
    with pytest.raises((ValueError, OwnershipConflict)):
        map_task_configuration(**values)
    assert not c.resource.channels and c.worker is None


@pytest.mark.parametrize(
    "max_files,max_file_bytes,max_total_bytes",
    [(1, 1, 1), (10000, 2 * 1024**4, 2 * 1024**4)],
)
def test_exact_declared_budget_boundaries(
    c: RegisteredMapCase, max_files: int, max_file_bytes: int, max_total_bytes: int
) -> None:
    cfg = map_task_configuration(
        **{
            **arguments(c),
            "max_files": max_files,
            "max_file_bytes": max_file_bytes,
            "max_total_bytes": max_total_bytes,
        }
    )
    assert cfg.map_inputs is not None
    assert (
        cfg.map_inputs.max_files,
        cfg.map_inputs.max_file_bytes,
        cfg.map_inputs.max_total_bytes,
    ) == (max_files, max_file_bytes, max_total_bytes)
    assert not c.resource.channels
