"""Pure refusal boundaries. No fixture permission becomes a production default."""

from typing import Any
from pathlib import Path
from lab_generate_skill.bootstrap.admin_navigation_claimed_authority import (
    AdminNavigationClaimedSiteAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from admin_navigation_owned_fixtures import owned_navigation_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
import pytest
from lab_generate_skill.bootstrap.admin_navigation_owned_execution import (
    admin_navigation_owned_execution,
)
from lab_generate_skill.bootstrap.admin_navigation_execution_admission import (
    admit_admin_navigation_execution_source,
)
from lab_generate_skill.bootstrap.admin_navigation_browser_declarations import (
    OriginalAdminNavigationBrowserDeclarations,
)


@pytest.mark.parametrize("value", [None, "", {}, [], 0, True])
def test_explicit_admin_owner_source_reader_model_and_browser_declarations_required(
    value: Any,
) -> None:
    with pytest.raises(TypeError):
        admin_navigation_owned_execution(
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            bindings=value,
            controls=value,
            clock=value,
            trace_root=value,
            calls_root=value,
            trace_capacity=value,
        )
    with pytest.raises(TypeError):
        admit_admin_navigation_execution_source(
            value,
            value,
            value,
            value,
            value,
            value,
            claim_root=value,
            claim_scope=value,
            evidence=value,
            controls=value,
            source_reads=value,
        )
    with pytest.raises(TypeError):
        OriginalAdminNavigationBrowserDeclarations(value, value, value, value, value)


def test_normal_closed_source_claim_and_default_admin_binding_with_no_resource_effects(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)
    owned, source = c.owned, c.source
    assert owned.resources.site.phase == "new" and owned.resources.browser() is None
    assert owned.bundle.preparation.declaration == c.declarations.preparation
    assert owned.bundle.task.plan.intent == c.admitted.published.source.intent
    assert owned.bundle.task.plan.skill_ref == c.declarations.plan.skill_ref
    assert owned.bundle.preparation.state.phase == "new"
    rights = owned.physical_site.source
    assert isinstance(rights, AdminNavigationClaimedSiteAuthority)
    op = rights.acquisition
    control = source.site.controls.bind(op)
    rights.verify_source(op, control)
    assert not rights._spawn
    spec = rights.spec
    inputs = spec.configuration.admin_navigation_inputs
    assert inputs is not None
    variants = (
        inputs.model_copy(
            update={
                "origin": inputs.origin.model_copy(
                    update={"endpoint": "http://127.0.0.1:12009/admin"}
                )
            }
        ),
        inputs.model_copy(update={"native_contract_sha256": "0" * 64}),
        inputs.model_copy(update={"private_input_sha256": "0" * 64}),
        inputs.model_copy(
            update={"scope": inputs.scope.model_copy(update={"attempt_id": "foreign"})}
        ),
    )
    for bad in variants:
        changed = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={"admin_navigation_inputs": bad}
                )
            }
        )
        rejected = AdminNavigationClaimedSiteAuthority(
            owned.resources.owner, changed, op
        )
        with pytest.raises(OwnershipConflict):
            rejected.verify_source(op, control)
        assert not rejected._spawn
    assert owned.resources.site.phase == "new" and owned.resources.browser() is None
    assert (
        not (tmp_path / "candidate-trace").exists()
        and not (tmp_path / "candidate-calls").exists()
    )
