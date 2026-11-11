"""Actual selected pins and original typed declarations, no live resource grant."""

from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from admin_production_inputs import (
    SelectedAdminNavigation,
    load_admin_navigation_group,
    bind_admin_public,
    declare_admin_site,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from test_admin_navigation_source_authority import source_case
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.fixture(scope="module")
def selected() -> tuple[SelectedAdminNavigation, ...]:
    return load_admin_navigation_group(guard(60))


def test_all71_original_pins_and_static_branches_before_any_resource(
    selected: tuple[SelectedAdminNavigation, ...],
) -> None:
    assert len(selected) == 71
    assert len({s.private.task.source_task_id for s in selected}) == 71
    assert {s.private.initialization for s in selected} == {
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    }
    assert all(s.private.admission == "unverified" for s in selected)
    assert all(s.private.native_contract_ref == s.native_ref for s in selected)
    assert all(replace(s) == s for s in selected)


def test_original_v7_source_declaration_and_public_binding_are_exact(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    selected: tuple[SelectedAdminNavigation, ...],
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    inputs = c.spec.configuration.admin_navigation_inputs
    assert inputs is not None
    first = selected[0]
    assert first.private.task == owner.scope.task
    bound = bind_admin_public(first, inputs.origin, ("click", "send_msg_to_user"))
    assert bound.private_spec == first.private
    # Retain the actual original strict constructors and original unit fixture
    # declarations; no fake owner/default is built by the production consumer.
    value = declare_admin_site(
        first,
        owner.scope,
        c.spec.token,
        c.spec.configuration.files,
        c.spec.configuration.installation,
        inputs.origin,
        c.spec.slurm,
        c.op,
    )
    assert value == c.spec
    assert value.model_dump_json() == c.spec.model_dump_json()
    assert not tuple(c.journal._root.iterdir())


@pytest.mark.parametrize(
    "fault", ["task", "owner", "resource", "provider", "operation", "origin"]
)
def test_mismatched_current_bindings_are_refused_before_resource_effects(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    selected: tuple[SelectedAdminNavigation, ...],
    fault: str,
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    inputs = c.spec.configuration.admin_navigation_inputs
    assert inputs is not None
    scope, token, origin, op = owner.scope, c.spec.token, inputs.origin, c.op
    if fault == "task":
        scope = scope.model_copy(update={"task": selected[1].private.task})
    elif fault == "owner":
        token = token.model_copy(
            update={"owner": token.owner.model_copy(update={"owner_id": "other"})}
        )
    elif fault == "resource":
        token = token.model_copy(update={"expected_resource_id": "other"})
    elif fault == "provider":
        token = token.model_copy(
            update={"provider_id": "unit-not-a-production-default"}
        )
    elif fault == "operation":
        op = op.model_copy(update={"allocation_id": "other"})
    else:
        origin = origin.model_copy(
            update={"endpoint": "http://example.test:18080/admin"}
        )
    with pytest.raises((ValueError, OwnershipConflict)):
        declare_admin_site(
            selected[0],
            scope,
            token,
            c.spec.configuration.files,
            c.spec.configuration.installation,
            origin,
            c.spec.slurm,
            op,
        )
    assert not tuple(c.journal._root.iterdir())


def test_selection_cannot_change_native_or_public_fields(
    selected: tuple[SelectedAdminNavigation, ...],
) -> None:
    for change in (
        {"goal": "changed"},
        {"raw": b"{}"},
        {"private": selected[1].private},
    ):
        with pytest.raises((ValueError, OwnershipConflict, EvidenceIntegrityError)):
            replace(selected[0], **change)
