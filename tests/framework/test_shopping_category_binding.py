"""Actual category binding records; dynamic authority called on every load."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    bind_category_navigation_records,
)
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_policy import (
    category_navigation_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationSpec,
)
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.clock import SystemClock
from evidence_control_fixtures import EvidenceFixtureStore
from test_resource_journal import NoCancellation
from test_shopping_category_navigation_input import originals as originals
from site_worker_fixtures import configuration, operation
from preparation_record_fixtures import put
from test_slurm_commands import guard


class CurrentAuthority:
    def __init__(self) -> None:
        self.calls = 0
        self.denied = False

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        spec = CategoryNavigationSpec.model_validate_json(private_spec)
        assert binding.identity == public_task.identity == spec.task
        assert (
            baseline
            == category_navigation_initial_spec(spec.task).model_dump_json().encode()
        )
        if self.denied:
            raise PermissionError("current source permission revoked")


@pytest.mark.parametrize(
    "fault", ["normal", "changed_private", "noncanonical", "denied"]
)
def test_group_binding_recomputation_and_fresh_dynamic_authority(
    tmp_path: Path, originals: Any, fault: str
) -> None:
    for raw, _, public in originals if fault == "normal" else originals[:1]:
        root = tmp_path / public.identity.source_task_id
        root.mkdir()
        store = EvidenceFixtureStore(root)
        ref = store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="shopping-native-contract/1",
                visibility="private",
                producer="unit-category-native",
            ),
            control=guard(),
        )
        spec = load_category_navigation_inputs(raw, ref, public).private_spec
        if fault == "changed_private":
            spec = spec.model_copy(
                update={
                    "original": spec.original.model_copy(
                        update={
                            "current_entry_review": "changed original private source label"
                        }
                    )
                }
            )
        baseline = category_navigation_initial_spec(spec.task)
        private = spec.model_dump_json().encode()
        if fault == "noncanonical":
            private = b" " + private
        private_ref = store.put(
            private,
            EvidenceMetadata(
                media_type="application/json",
                content_schema=spec.schema_version,
                visibility="private",
                producer="unit-category-private",
            ),
            control=guard(),
        )
        binding = TaskBinding(
            identity=public.identity,
            registration_id="unit-category",
            public_task_ref=put(store, public, "public"),
            private_spec_ref=private_ref,
            baseline_ref=put(store, baseline),
        )
        authority = CurrentAuthority()
        authority.denied = fault == "denied"
        records = bind_category_navigation_records(
            store, OperationGuards(SystemClock(), NoCancellation()), authority
        )
        op = operation(configuration())
        if fault == "normal":
            published = records.publish(binding, op)
            assert records.load(published, op) == binding and authority.calls == 2
            authority.denied = True
            with pytest.raises(PermissionError):
                records.load(published, op)
            assert authority.calls == 3
        else:
            with pytest.raises(
                PermissionError if fault == "denied" else EvidenceIntegrityError
            ):
                records.publish(binding, op)
            assert authority.calls == (1 if fault == "denied" else 0)
