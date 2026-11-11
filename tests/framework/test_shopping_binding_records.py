"""Real immutable inputs and CAS transport, with explicit synthetic run rights."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from lab_generate_skill.bootstrap.shopping_order_eta_records import (
    bind_order_eta_records,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.order_eta_policy import (
    order_eta_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_spec import OrderEtaSpec
from evidence_control_fixtures import EvidenceFixtureStore
from site_worker_fixtures import configuration, operation
from test_resource_journal import NoCancellation
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.adapters.clock import SystemClock
from test_shopping_order_eta_inputs import FIXTURE, public_task
from preparation_record_fixtures import put
from test_slurm_commands import guard


class UnitBusinessAuthority:
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
        spec = OrderEtaSpec.model_validate_json(private_spec)
        assert baseline == order_eta_initial_spec(spec.task).model_dump_json().encode()
        if self.denied:
            raise PermissionError("synthetic run/source denied")


@pytest.mark.parametrize(
    "fault", ["none", "private_date", "noncanonical", "denied", "heldout"]
)
def test_binding_recomputes_native_inputs_and_delegates_actual_rights(
    tmp_path: Path, fault: str
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    store = EvidenceFixtureStore(root)
    public = public_task()
    raw = FIXTURE.read_bytes()
    if fault == "heldout":
        native = json.loads(raw)
        native["heldout_quarantine"] = True
        raw = json.dumps(native).encode()
    ref = store.put(
        raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema="shopping-native-contract/1",
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    # A held-out native revision must be rejected before any binding is created.
    if fault == "heldout":
        with pytest.raises(EvidenceIntegrityError):
            load_order_eta_inputs(raw, ref, public)
        return
    private = load_order_eta_inputs(raw, ref, public).private_spec
    if fault == "private_date":
        private = private.model_copy(update={"recorded_date": "2023-02-04"})
    baseline = order_eta_initial_spec(private.task)
    private_raw = private.model_dump_json().encode()
    if fault == "noncanonical":
        private_raw = b" " + private_raw
    private_ref = store.put(
        private_raw,
        EvidenceMetadata(
            media_type="application/json",
            content_schema=private.schema_version,
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    binding = TaskBinding(
        identity=public.identity,
        registration_id="unit-shopping",
        public_task_ref=put(store, public, "public"),
        private_spec_ref=private_ref,
        baseline_ref=put(store, baseline),
    )
    authority = UnitBusinessAuthority()
    authority.denied = fault == "denied"
    records = bind_order_eta_records(
        store, OperationGuards(SystemClock(), NoCancellation()), authority
    )
    op = operation(configuration())
    if fault == "none":
        result = records.publish(binding, op)
        assert records.load(result, op) == binding and authority.calls == 2
    else:
        with pytest.raises(
            PermissionError if fault == "denied" else EvidenceIntegrityError
        ):
            records.publish(binding, op)
        assert authority.calls == (1 if fault == "denied" else 0)
