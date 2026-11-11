"""Explicit-origin C on the original source/prepare/full Reset AB consumers.

SQL, services, browser and physical source authority remain explicit doubles.
These real record/guard checks never replay an original benchmark execution.
"""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_task_preparation import (
    gitlab_group_task_preparation,
)
from gitlab_group_task_port_fixtures import group_port_case
from gitlab_group_source_fixtures import group_source_unit_case
from gitlab_native_fixtures import Lease
from test_gitlab_group_task_ports import (
    test_complete_Group4_delayed_native_preparation_and_full_nonstart_reset as complete_ports,
)
from test_gitlab_group_source_composition import (
    contracts_for,
)
from test_gitlab_group_complete_starts import PINS, W
from site_instance_fixtures import node_path as node_path


def fixture_origin(patch: pytest.MonkeyPatch, source: str) -> None:
    import gitlab_group_fixtures as inputs

    patch.setattr(
        inputs,
        "FIXTURE",
        W
        / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
        / (source + ".json"),
    )
    patch.setattr(Lease, "ports", (18080, 12002))


@pytest.mark.parametrize("source", tuple(PINS))
def test_explicit_group_origin_on_full_original_preparation_and_Reset(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    fixture_origin(monkeypatch, source)
    with group_port_case(
        tmp_path, node_path, monkeypatch, source, explicit_origin=True
    ) as p:
        assert p.resource.spec.configuration.gitlab_group_inputs is not None
        complete_ports(p)


@pytest.mark.parametrize("source", tuple(PINS))
@pytest.mark.parametrize("fault", ["none", "cancel_after_reset", "restore_return_lost"])
def test_explicit_group_origin_on_original_source_records_and_complete_cleanup(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    fault: str,
) -> None:
    fixture_origin(monkeypatch, source)
    c = group_source_unit_case(
        tmp_path,
        node_path,
        monkeypatch,
        contracts_for(source),
        fault,
        explicit_origin=True,
    )
    assert not c.failure.actual_actor_dispatched
    if fault == "none":
        assert c.qualified is not None
        assert c.qualified.receipt.scope.task.source_task_id == source
    else:
        assert c.facts is None


def test_foreign_context_refused_before_site_acquisition(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = next(iter(PINS))
    fixture_origin(monkeypatch, source)
    with group_port_case(
        tmp_path, node_path, monkeypatch, source, explicit_origin=True
    ) as p:
        changed = p.declaration.model_copy(
            update={"scope": p.scope.model_copy(update={"context_id": "foreign"})}
        )
        with pytest.raises(ValueError, match="original declared scope"):
            gitlab_group_task_preparation(
                p.plan,
                changed,
                p.resource.spec,
                p.site,
                p.resource.journal,
                p.resource.evidence,
                p.resource.controls,
                p.bindings,
                p.authority,
            )
        assert p.site.phase == "new" and not p.requests and not p.resource.channels
