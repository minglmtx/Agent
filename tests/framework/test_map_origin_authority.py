"""Original full context/source gate before worker effects, not a permission cache."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.lifecycle import OperationControl
from map_navigation_group_cases import SOURCES
from map_task_execution_current_fixtures import (
    current_map_execution_case,
    CurrentMapExecutionCase,
)
from map_origin_fixtures import source_origin
from map_registered_worker_fixtures import RegisteredMapCase
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from test_core_contracts import reference


@pytest.fixture
def current(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[CurrentMapExecutionCase]:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as value:
        yield value


def test_original_context_full_graph_is_read_each_time_without_task_effects(
    current: CurrentMapExecutionCase,
) -> None:
    spec, authority = source_origin(current)
    c, context = current.p.original.resource, current.journals.context
    before = len(context.context_operations)
    for _ in range(2):
        authority.verify_origin(spec, c.op, guard())
    assert len(context.context_operations) == before + 4
    assert context.context_operations[-4:] == [current.p.plan.read_operation, c.op] * 2
    assert current.p.requests == [] and current.p.preparation.state.phase == "new"
    context.denied_context = True
    with pytest.raises(OwnershipConflict, match="permission denied"):
        authority.verify_origin(spec, c.op, guard())
    assert current.p.requests == []


@pytest.mark.parametrize(
    "fault",
    [
        "url",
        "public-ref",
        "same-attempt",
        "wrong-source",
        "missing-records",
        "missing-reader",
        "partial-bytes",
        "cancel",
    ],
)
def test_original_source_binding_refuses_mismatch_and_unconfirmed_reads(
    current: CurrentMapExecutionCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    spec, authority = source_origin(current)
    c = current.p.original.resource
    data = spec.model_dump()
    inputs = data["configuration"]["map_inputs"]
    if fault == "url":
        inputs["origin"]["source_start_url"] += "#foreign"
    elif fault == "public-ref":
        inputs["origin"]["source_context_ref"] = reference(
            "public", "public-construction-context/1"
        ).model_dump()
    elif fault == "same-attempt":
        inputs["scope"]["attempt_id"] = current.journals.source.scope.attempt_id
    elif fault == "wrong-source":
        from map_navigation_fixtures import navigation_case

        private = navigation_case(SOURCES[1]).load().private_spec
        inputs["scope"]["task"] = private.task.model_dump()
        inputs["native_contract_sha256"] = private.native_contract_ref.sha256
    elif fault == "missing-records":
        authority.contexts = None
    elif fault == "missing-reader":
        authority.evidence = None
    elif fault == "partial-bytes":

        class Partial:
            def read(self, reference: Any, control: OperationControl) -> bytes:
                control.checkpoint()
                return b"{}"

        authority.evidence = Partial()
    elif fault == "cancel":

        class Cancel:
            def checkpoint(self) -> float:
                raise TimeoutError("original origin cancelled")

            def wait(self, seconds: float) -> None:
                raise AssertionError("no waits")

        with pytest.raises(TimeoutError, match="original origin cancelled"):
            authority.verify_origin(spec, c.op, Cancel())
        assert current.p.requests == []
        return
    changed = SiteResourceSpec.model_validate(data)
    with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
        authority.verify_origin(changed, c.op, guard())
    assert current.p.requests == []


def test_dynamic_origin_is_explicitly_not_source_qualification(
    current: CurrentMapExecutionCase,
) -> None:
    spec = current.p.original.resource.spec
    inputs = spec.configuration.map_inputs
    assert isinstance(inputs, MapNavigationWorkerInputs)
    assert inputs.origin == MapOriginPolicy.dynamic()
    OriginalMapOriginAuthority(
        contexts=None, evidence=None, source=None, read_operation=None
    ).verify_origin(spec, current.p.original.resource.op, guard())
    assert current.p.requests == []


def test_navigation_parent_requires_explicit_origin_supplier_before_spawn(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with pytest.raises(ValueError, match="origin authority"):
            TaskSiteAuthority(
                c.resource.spec, c.resource.op, c.resource.authority, origin=None
            )
        error = PermissionError("original context permission denied")

        class Denied:
            def verify_origin(
                self, spec: SiteResourceSpec, operation: Any, control: OperationControl
            ) -> None:
                control.checkpoint()
                raise error

        authority = TaskSiteAuthority(
            c.resource.spec, c.resource.op, c.resource.authority, origin=Denied()
        )
        with pytest.raises(PermissionError) as caught:
            with registered_site(
                c.resource.spec,
                c.resource.op,
                journal=c.resource.journal,
                evidence=c.resource.evidence,
                controls=c.resource.controls,
                clock=c.resource.clock,
                authority=authority,
            ):
                pytest.fail("origin denied before any worker")
        assert caught.value is error
        assert not c.resource.channels and c.worker is None and not c.case.loaded
    finally:
        c.close_sockets()


def test_default_task_rejects_origin_from_other_construction_context(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace
    import map_task_execution_current_fixtures as fixtures
    from test_map_origin_policy import frozen_values

    from lab_generate_skill.bootstrap.map_task_execution import (
        map_navigation_task_execution as original,
    )

    rejected = []

    def checked(
        declarations: Any, resources: Any, authorities: Any, runtime: Any
    ) -> Any:
        data = resources.site_spec.model_dump()
        data["configuration"]["map_inputs"]["origin"] = MapOriginPolicy(
            **frozen_values()
        ).model_dump()
        changed = replace(resources, site_spec=SiteResourceSpec.model_validate(data))
        with pytest.raises(OwnershipConflict, match="original source origin/context"):
            original(declarations, changed, authorities, runtime)
        rejected.append(True)
        return original(declarations, resources, authorities, runtime)

    monkeypatch.setattr(fixtures, "map_navigation_task_execution", checked)
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as c:
        assert rejected == [True]
        assert c.p.requests == [] and c.native.loader.session.calls == 0
