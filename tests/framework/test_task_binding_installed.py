"""TaskBinding through fixed installed workers/resolver; synthetic site authority."""

import json
from dataclasses import asdict
import os
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.bootstrap.admin_description_records import (
    bind_product_description_records,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.task_bindings import TaskBindingInputLoads
from lab_generate_skill.runtime.lifecycle import OperationGuards
from managed_store_fixtures import assembled
from task_binding_fixtures import UnitAuthority, BASELINE
from test_admin_description_inputs import FIXTURE, public_task
from test_run_journal import command, CancelSwitch
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_selected_task_binding_uses_real_installed_evidence_port(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    public = public_task()
    store, storage_authority = assembled(
        tmp_path,
        installed_sources,
        max_object_bytes=32768,
        source_task_id=public.identity.source_task_id,
    )
    store.initialize(guard(60))

    def put(raw: bytes, schema: str, visibility: str = "private") -> EvidenceRef:
        return store.put(
            raw,
            EvidenceMetadata.model_validate(
                dict(
                    media_type="application/json",
                    content_schema=schema,
                    visibility=visibility,
                    producer="installed-binding-test",
                )
            ),
            guard(60),
        )

    native_bytes = FIXTURE.read_bytes()
    native = put(native_bytes, "admin-native-contract/1")
    inputs = load_product_description_inputs(native_bytes, native, public)
    binding = TaskBinding(
        identity=public.identity,
        registration_id="admin.product-description.v1",
        public_task_ref=put(
            public.model_dump_json().encode(), public.schema_version, "public"
        ),
        private_spec_ref=put(
            inputs.private_spec.model_dump_json().encode(),
            inputs.private_spec.schema_version,
        ),
        baseline_ref=put(BASELINE, "unit-admin-baseline/1"),
    )
    owner = storage_authority.binding.owner
    authority = UnitAuthority(owner.run_id, owner.owner_id)
    records = bind_product_description_records(
        store, OperationGuards(SystemClock(), CancelSwitch()), authority
    )
    publish_op = command().model_copy(
        update={"run_id": owner.run_id, "owner_id": owner.owner_id}
    )
    ref = records.publish(binding, publish_op)
    read_op = command().model_copy(
        update={"run_id": owner.run_id, "owner_id": owner.owner_id}
    )
    assert records.load(ref, read_op) == binding
    assert store.state == "ready" and len(authority.calls) == 2
    last = store.last_exchange
    assert last is not None and last.reusable and last.snapshot is not None
    snapshot = last.snapshot
    assert len(snapshot.entries) == 14
    assert all(entry.reusable for entry in snapshot.entries)
    assert last.execution is not None
    assert last.execution.capture.termination is not None
    assert last.execution.capture.termination.state == "reaped"
    assert last.resolution is not None
    # Exercise the new producer/consumer output through the same actual
    # fixed installed storage and resolver, with fresh original authority.
    assert isinstance(records, TaskBindingInputLoads)
    assert records.loads_inputs_in_one_call
    bodies = records.load_inputs(ref, read_op)
    assert bodies.binding == binding and bodies.public_task == public
    assert bodies.private_spec == inputs.private_spec.model_dump_json().encode()
    assert bodies.baseline == BASELINE
    assert len(authority.calls) == 3 and store.state == "ready"
    last = store.last_exchange
    assert last is not None and last.reusable and last.snapshot is not None
    assert last.execution is not None and last.execution.capture.termination is not None
    snapshot = last.snapshot
    assert len(snapshot.entries) == 19 and all(
        entry.reusable for entry in snapshot.entries
    )
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "task-binding-installed.json"
    )
    output.write_text(
        json.dumps(
            {
                "engineering_only": True,
                "synthetic_task_baseline_and_authority": True,
                "binding": binding.model_dump(mode="json"),
                "binding_ref": ref.model_dump(mode="json"),
                "store_state": store.state,
                "exchanges": len(snapshot.entries),
                "original_load_exchanges": 14,
                "same_call_input_bodies_consumed": True,
                "all_exchanges_reusable": all(
                    entry.reusable for entry in snapshot.entries
                ),
                "snapshot": snapshot.model_dump(mode="json"),
                "last_worker_termination": asdict(last.execution.capture.termination),
                "actual_site_preparation_verified": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
