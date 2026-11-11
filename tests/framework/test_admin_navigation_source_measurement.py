"""All71 declared source bindings, without source/site/browser/model permission."""

from dataclasses import replace
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_navigation_source_measurement import (
    admin_navigation_measurement_binding,
)
from lab_generate_skill.domain.admin_navigation_browser_initialization import (
    AdminNavigationInitialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from test_admin_navigation_input import contracts as contracts, NETLOC
from retrieval_fixtures import reference
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl


class NoRead:
    def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
        raise AssertionError("Pure source declaration must not read or acquire")


def test_all71_source_declarations_keep_original_two_starts_and_collectors(
    contracts: Any,
) -> None:
    seen = set()
    for native, ref, public in contracts:
        private = bind_admin_navigation(native, ref, public).private_spec
        binding = admin_navigation_measurement_binding(
            private,
            public,
            "http://" + NETLOC + "/admin",
            reference({}, "prepared-task/1"),
            reference({}, "site-resource-started/1"),
            NoRead(),
        )
        selected = binding.initialization
        assert isinstance(selected, AdminNavigationInitialization)
        assert selected.start_path == native["start_path"]
        assert selected.native_contract_sha256 == ref.sha256
        assert binding.collector == ("admin-navigation-page", "1")
        assert private.admission == "unverified"
        seen.add(public.identity.source_task_id)
    assert len(seen) == 71


@pytest.mark.parametrize(
    "fault",
    ["task", "origin", "prepared", "site", "collector", "checks", "prepared-checks"],
)
def test_source_measurement_binding_refuses_invalid_policy_before_acquisition(
    contracts: Any, fault: str
) -> None:
    native, ref, public = contracts[0]
    private = bind_admin_navigation(native, ref, public).private_spec
    prepared, site = reference({}, "prepared-task/1"), reference(
        {}, "site-resource-started/1"
    )
    if fault == "task":
        public = public.model_copy(
            update={
                "identity": public.identity.model_copy(
                    update={"source_task_id": "foreign"}
                )
            }
        )
    if fault == "prepared":
        prepared = site
    if fault == "site":
        site = prepared
    with pytest.raises((ValueError, TypeError, OwnershipConflict)):
        binding = admin_navigation_measurement_binding(
            private,
            public,
            (
                "http://127.0.0.1:19000/admin"
                if fault == "origin"
                else "http://" + NETLOC + "/admin"
            ),
            prepared,
            site,
            NoRead(),
        )
        if fault == "collector":
            replace(binding, collector=("", "1"))
        elif fault == "checks":
            replace(binding, initial_checks=None)  # type: ignore[arg-type]
        elif fault == "prepared-checks":
            replace(binding, prepared_checks=True)  # type: ignore[arg-type]
