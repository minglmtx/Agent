"""Selected8 real source declarations/adapters; expensive native effects are doubles."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OperationStopped, EvidenceIntegrityError
from lab_generate_skill.domain.site_worker import SiteInstanceStarted
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.actor_projection import (
    FullAxProjection,
    check_projection_task,
)
from map_navigation_group_cases import SOURCES
from map_navigation_source_fixtures import selection, source_combination
from map_navigation_source_selection import MapNavigationSourceSelection
from map_navigation_evaluation_fixtures import closed_review
from map_navigation_browser_fixtures import CancelledControl
from map_registered_worker_fixtures import RegisteredMapCase
from map_preparation_native import MapPreparation
from map_source_inputs import source_inputs, engineering_scope
from test_map_source_inputs import source_case as source_case, SourceCase
from test_slurm_commands import guard
from test_site_resource import inspect
from site_instance_fixtures import node_path as node_path
from source_task_hooks import SourceTaskHooks
from lab_generate_skill.domain.lifecycle import ResourceOwner


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_pinned_source_plan_public_binding_repeat_and_no_native_effect(
    source_case: SourceCase, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    root, evidence, parent, base, store = source_case
    selected = selection(source)
    value = source_inputs(
        store,
        base.token.owner,
        base.installation,
        root,
        parent,
        guard(),
        scope=engineering_scope(base.token.owner, selected),
        evidence_root=evidence,
        selection=selected,
    )
    again = source_inputs(
        store,
        base.token.owner,
        base.installation,
        root,
        parent,
        guard(),
        scope=engineering_scope(base.token.owner, selected),
        evidence_root=evidence,
        selection=selected,
    )
    assert value == again
    assert isinstance(value.configuration.map_inputs, MapNavigationWorkerInputs)
    assert (
        value.configuration.map_inputs.scope.task == selected.public_template.identity
    )
    assert value.configuration.map_inputs.runtime.publication_job_id == "4795725"
    assert value.original_sources is None and value.original_reference_ref is None
    assert not list(parent.iterdir())
    check_projection_task(FullAxProjection(), selected.public_template.identity)
    from site_resource_fixtures import resource_case

    site_root = root / "declared-site"
    site_root.mkdir()
    c = resource_case(site_root, monkeypatch, config=value.configuration, store=store)
    c.spec = c.spec.model_copy(update={"configuration": value.configuration})
    c.op = c.op.model_copy(update={"recovery_ref": c.spec.token.recovery_ref})
    started = SiteInstanceStarted(
        files=value.configuration.files,
        endpoint="http://127.0.0.1:18080/",
        ports=(18080, 18081, 18082, 18083, 18084, 18085),
    )
    n = MapPreparation(c, started, value, allowed_actions=("click", "send_msg_to_user"))
    assert n.public.identity == selected.public_template.identity
    assert n.public.start_url == selected.public_at(started.endpoint, None).start_url
    assert n.recovery.restore_component_id == "map-native-navigation"
    assert (
        MapPreparation(
            c, started, value, allowed_actions=("click", "send_msg_to_user")
        ).binding_ref
        == n.binding_ref
    )
    assert not c.channels and not list(parent.iterdir())
    with pytest.raises(OperationStopped):
        source_inputs(
            store,
            base.token.owner,
            base.installation,
            root,
            parent,
            CancelledControl(),
            scope=engineering_scope(base.token.owner, selected),
            evidence_root=evidence,
            selection=selected,
        )


@pytest.mark.parametrize("invalid", [None, "", 1, [], {}])
def test_invalid_selection_bytes_rejected_without_source_effect(invalid: Any) -> None:
    selected = selection(SOURCES[0])
    with pytest.raises((TypeError, ValueError)):
        replace(selected, native=invalid)


def test_selection_wrong_source_native_bytes_actions_and_foreign_hook_rejected() -> (
    None
):
    selected, other = selection(SOURCES[0]), selection(SOURCES[1])
    for changes, error, message in (
        (
            {"binding": other.binding},
            EvidenceIntegrityError,
            "Invalid original Map navigation input",
        ),
        (
            {"public_template": other.public_template},
            ValueError,
            "Exact selected train navigation identity/contract required",
        ),
        (
            {"native": selected.native + b" "},
            ValueError,
            "Exact selected train navigation identity/contract required",
        ),
    ):
        with pytest.raises(error, match="^" + message + "$"):
            replace(selected, **changes)
    for endpoint in (
        "https://127.0.0.1:18080/",
        "http://example.org:18080/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:18080/path",
    ):
        with pytest.raises(ValueError):
            selected.public_at(endpoint, None)
    unit: Any = None
    owner = ResourceOwner(
        run_id="run", owner_id="owner", job_id="engineering", worker_id="source"
    )
    invalid_values: tuple[Any, ...] = ("", 1, {}, [])
    for invalid in invalid_values:
        wrong: Any = invalid
        with pytest.raises(TypeError):
            SourceTaskHooks(owner, unit, ("click",), unit, unit, map_selection=wrong)
    foreign: Any = object()
    with pytest.raises(ValueError):
        SourceTaskHooks(
            owner,
            unit,
            ("click",),
            unit,
            unit,
            map_selection=selected,
            private_site_plan=foreign,
        )


def test_selected_source_endpoint_bounds_wrong_types_and_heldout_rejected() -> None:
    selected = selection(SOURCES[0])
    for port in (1024, 65535):
        assert (
            selected.public_at(f"http://127.0.0.1:{port}/", None).identity
            == selected.public_template.identity
        )
    invalid_endpoints: tuple[Any, ...] = (None, True, 1, {}, [])
    for invalid in invalid_endpoints:
        bad: Any = invalid
        with pytest.raises(TypeError):
            selected.public_at(bad, None)
    for split in ("dev", "test"):
        task = selected.public_template.model_copy(
            update={
                "identity": selected.public_template.identity.model_copy(
                    update={"split": split}
                )
            }
        )
        with pytest.raises(ValueError):
            replace(selected, public_template=task)


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_current_actual_source_callbacks_evaluation_fresh_review_and_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        facts = source_combination(c, monkeypatch)
        closed_review(c, facts)
        assert inspect(c.resource).state == "closed"
    finally:
        c.close_sockets()


@pytest.mark.parametrize("kind", ["valid-negative", "missing-trace"])
def test_source_error_kept_unknown_or_original_failure_without_repeat_and_safe_reset(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        facts = source_combination(
            c,
            monkeypatch,
            negative=kind == "valid-negative",
            missing_trace=kind == "missing-trace",
        )
        if kind == "valid-negative":
            closed_review(c, facts)
        assert inspect(c.resource).state == "closed"
    finally:
        c.close_sockets()
