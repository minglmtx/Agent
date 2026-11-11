"""Same complete-state scenarios, navigation contracts and synthetic authority."""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
import pytest
import test_state_qualification as original
from test_state_qualification import (
    test_original_environment_and_complete_reset_recompute,
    test_environment_rejects_incomplete_or_foreign_facts,
    test_reset_cannot_drop_or_substitute_original_evidence,
    test_authority_denied_and_wrong_owner_no_publication,
    test_partial_commit_retains_prefix_and_unknown_candidate,
    test_invalid_selection_shapes_rejected,
)
from admin_navigation_state_fixtures import qualified
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts
from lab_generate_skill.sites.shopping_admin.tasks.navigation_state_policy import (
    navigation_initial_state_spec,
)


@pytest.fixture(autouse=True)
def selected_navigation_contract(
    monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    def selected(
        root: Path, node: Path, patch: pytest.MonkeyPatch
    ) -> AbstractContextManager[Any]:
        return qualified(root, node, patch, contracts)

    monkeypatch.setattr(original, "qualified", selected)
    monkeypatch.setattr(
        original, "product_initial_state_spec", navigation_initial_state_spec
    )


def test_navigation_policy_preserves_full_components_without_product_seed(
    contracts: Any,
) -> None:
    from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
        bind_admin_navigation,
    )

    for native, ref, public in contracts:
        spec = navigation_initial_state_spec(
            bind_admin_navigation(native, ref, public).private_spec.task
        )
        assert spec.task_reset_checks == (
            "admin.database.restored",
            "admin.artifacts.restored",
            "admin.cache.cleared",
            "admin.search.restored",
        )
