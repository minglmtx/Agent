"""Original sole-view record scenarios applied to navigation's exact setup."""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
import pytest
import test_initial_observation as original
from test_initial_observation import (
    test_publish_and_reconcile_only_initial_checks,
    test_original_worker_binding_cannot_be_replaced_in_initial_inputs,
    test_dependency_fault_preserved_without_publication,
    test_invalid_selection_rejected,
    test_check_operation_must_be_distinct_and_owned,
    test_denied_load_and_forged_summary_rejected,
    test_unready_view_does_not_pass_site_check,
    test_put_returns_wrong_reference_is_not_accepted,
    test_narrowed_site_check_coverage_is_rejected,
    test_post_commit_failure_keeps_original_reference_for_read_only_reconciliation,
    test_unconfirmed_put_keeps_candidate_without_claiming_existence,
)
from admin_navigation_initial_fixtures import initial_case
from test_admin_navigation_input import contracts as contracts


@pytest.fixture(autouse=True)
def selected_navigation_initial(
    monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    def selected(root: Path, patch: pytest.MonkeyPatch) -> AbstractContextManager[Any]:
        return initial_case(root, patch, contracts)

    monkeypatch.setattr(original, "initial_case", selected)
