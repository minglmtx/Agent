"""Category source→claim→owned composition with explicit unit physical premises.

The original category producer and neutral persisted claim/run algorithms run.
No native candidate, model, Actor or benchmark instance is acquired here.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_browser_declarations import (
    OriginalShoppingCategoryBrowserDeclarations,
)
from lab_generate_skill.bootstrap.shopping_category_claimed_authority import (
    CategoryNavigationClaimedSiteAuthority,
)
from lab_generate_skill.bootstrap.shopping_category_execution_admission import (
    admit_shopping_category_execution_source,
)
from lab_generate_skill.bootstrap.shopping_category_owned_execution import (
    shopping_category_owned_execution,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from shopping_category_owned_fixtures import owned_navigation_case
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals


@pytest.mark.parametrize("value", [None, "", {}, [], 0, True])
def test_category_owned_requires_original_reader_owner_model_and_browser_factory(
    value: Any,
) -> None:
    with pytest.raises(TypeError):
        shopping_category_owned_execution(
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
        admit_shopping_category_execution_source(
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
        OriginalShoppingCategoryBrowserDeclarations(value, value, value, value, value)


def test_closed_category_producer_claim_and_owned_bundle_keep_scope_origin_and_no_resource_effects(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    owned = c.owned
    assert owned.resources.site.phase == "new" and owned.resources.browser() is None
    assert owned.bundle.preparation.declaration == c.declarations.preparation
    assert owned.bundle.task.plan.intent == c.admitted.published.source.intent
    assert owned.bundle.preparation.state.phase == "new"
    from lab_generate_skill.adapters.sites.task_preparation_inputs import (
        TaskPreparationDeclarationInputs,
    )
    from lab_generate_skill.bootstrap.shopping_category_production_member import (
        member_input_reuse,
    )

    carrier = owned.bundle.preparation.declared_inputs
    assert isinstance(carrier, TaskPreparationDeclarationInputs)
    assert (
        owned.resources.inputs is not None
        and owned.resources.inputs.preparation_declarations is carrier
    )
    assert member_input_reuse(owned)["preparation_declaration_reuse"] == {
        "declaration_graph_reads": 0,
        "declaration_graph_reuses": 0,
        "declaration_integrity_checks": 0,
    }
    rights = owned.physical_site.source
    assert isinstance(rights, CategoryNavigationClaimedSiteAuthority)
    op = rights.acquisition
    control = c.source.site.controls.bind(op)
    rights.verify_source(op, control)
    rights.verify_origin(rights.spec, op, control)
    assert not rights._spawn
    spec = rights.spec
    inputs = spec.configuration.shopping_category_inputs
    assert inputs is not None
    variants = [
        inputs.model_copy(
            update={
                "origin": inputs.origin.model_copy(
                    update={"endpoint": "http://127.0.0.1:12009/"}
                )
            }
        ),
        inputs.model_copy(update={"native_contract_sha256": "0" * 64}),
        inputs.model_copy(update={"private_input_sha256": "0" * 64}),
        inputs.model_copy(
            update={"scope": inputs.scope.model_copy(update={"attempt_id": "foreign"})}
        ),
        inputs.model_copy(
            update={"scope": inputs.scope.model_copy(update={"context_id": "foreign"})}
        ),
    ]
    for bad in variants:
        changed = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={"shopping_category_inputs": bad}
                )
            }
        )
        rejected = CategoryNavigationClaimedSiteAuthority(
            owned.resources.owner, changed, op
        )
        with pytest.raises(OwnershipConflict):
            rejected.verify_source(op, control)
        assert not rejected._spawn
    for version, value in [
        ("site-worker-configuration/6", inputs),
        ("site-worker-configuration/9", None),
    ]:
        changed = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={
                        "schema_version": version,
                        "shopping_category_inputs": value,
                    }
                )
            }
        )
        with pytest.raises((OwnershipConflict, ValueError)):
            CategoryNavigationClaimedSiteAuthority(owned.resources.owner, changed, op)
    assert owned.resources.site.phase == "new" and owned.resources.browser() is None
    assert (
        not (tmp_path / "candidate-trace").exists()
        and not (tmp_path / "candidate-calls").exists()
    )


def test_current_category_claim_is_reread_and_missing_history_is_never_recreated(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    rights = c.owned.physical_site.source
    assert isinstance(rights, CategoryNavigationClaimedSiteAuthority)
    op = rights.acquisition
    control = c.source.site.controls.bind(op)
    rights.verify_source(op, control)
    path = tmp_path / "candidate-claims" / c.admitted.claim.record.binding.key.filename
    raw = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(
            EvidenceIntegrityError,
            match="Initialized snapshot is missing; reconcile original history",
        ):
            rights.verify_source(op, control)
        assert not path.exists() and not rights._spawn
        assert (
            c.owned.resources.site.phase == "new"
            and c.owned.resources.browser() is None
        )
    finally:
        # Only the explicit synthetic test ledger is restored for teardown.
        path.write_bytes(raw)


def test_cancelled_category_origin_check_retains_original_stop_and_no_acquisition(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, originals[0])
    rights = c.owned.physical_site.source
    assert isinstance(rights, CategoryNavigationClaimedSiteAuthority)
    failure = OperationStopped("CANCELLED", rights.acquisition.operation_id)

    class Cancelled:
        def checkpoint(self) -> float:
            raise failure

        def wait(self, seconds: float) -> None:
            raise failure

    with pytest.raises(OperationStopped) as caught:
        rights.verify_origin(rights.spec, rights.acquisition, Cancelled())
    assert caught.value is failure and not rights._spawn
    assert c.owned.resources.site.phase == "new" and c.owned.resources.browser() is None
