"""Actual installed controlled storage before a task context/RunPlan exists.

Actual Slurm/kernel/writer/worker/CAS/session close, no task/source/model grant.
The installation fixture supplies frozen real package bytes only; no fixture
storage admission or synchronous EvidenceStore is installed in this assembly.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.bootstrap.owner_metadata_store import owner_metadata_store
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.runtime.lifecycle import OperationGuards
from registered_storage_fixtures import request, roots
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_linux_cgroups import actual_slurm_execution
from test_resource_journal import NoCancellation


def test_actual_original_owner_metadata_worker_and_session_without_plan_or_claim(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    execution, _ = actual_slurm_execution()
    root = tmp_path / "metadata"
    root.mkdir()
    roots(root)
    command = request(root, create=True, installation=installed_sources)
    owner = command.binding.owner.model_copy(
        update={
            "run_id": "map42-metadata-" + execution.job_id,
            "job_id": execution.job_id,
        }
    )
    binding = command.binding.model_copy(
        update={
            "scope": "run",
            "source_task_id": None,
            "owner": owner,
        }
    )
    workspace = Path(
        os.path.commonpath([str(tmp_path), str(installed_sources.workspace)])
    )
    scope = OwnerMetadataStorageScope(
        binding=binding,
        config=command.config,
        writer=current_process_identity(),
        execution=execution,
        workspace_root=str(workspace),
    )
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    op = OperationContext(
        operation_id="original-metadata-bootstrap",
        run_id=owner.run_id,
        owner_id=owner.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    bound = owner_metadata_store(
        scope,
        op,
        clock,
        controls,
        controls.bind(op),
        max_io_seconds=30,
        cleanup_seconds=10,
    )
    initial = bound.store.initialize(controls.bind(op))
    assert initial.binding == binding
    assert bound.admission.source_record is None
    metadata = EvidenceMetadata(
        media_type="application/json",
        content_schema="source-qualification-owner-metadata/1",
        visibility="private",
        producer="original-owner-metadata-actual-check",
    )
    raw = b'{"source_measurement_not_yet_started":true}'
    ref = bound.store.put(raw, metadata, controls.bind(op))
    assert bound.store.read(ref, controls.bind(op)) == raw
    assert bound.store.state == "ready"
    activation = bound.admission.activation_observation
    last = bound.admission.last_observation
    assert activation is not None and last is not None
    assert activation.membership == last.membership
    bound.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        bound.store.read(ref, controls.bind(op))
    assert bound.store.state == "ready"
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / "owner-metadata-store-actual.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "scope": scope.model_dump(mode="json"),
                    "reference": ref.model_dump(mode="json"),
                    "actual_original_controller": activation.membership.model_dump(
                        mode="json"
                    ),
                    "store_state_after_revocation": bound.store.state,
                    "actual_actor_members_executed": [],
                    "task_claim_created": False,
                    "model_calls": 0,
                    "site_instances": 0,
                    "paid_calls": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
