"""Real Slurm/writer and installed public store; claim entitlement is a fixture."""

from pathlib import Path
from dataclasses import replace
import json
import os
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.claim_reader import StorageClaimReader
from lab_generate_skill.adapters.storage.publication_reader import (
    StoragePublicationReader,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.bootstrap.storage_scope import assemble_slurm_evidence_store
from lab_generate_skill.domain.storage_scope import StorageScope
from lab_generate_skill.domain.claims import SourceClaimBinding
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.run_plan import RunPlan
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.runtime.lifecycle import OperationGuards
from storage_launch_fixtures import selection
from release_current_fixtures import store as current_store, op as publication_op
from lab_generate_skill.domain.release_activation import ReleaseSwitch
from storage_scope_fixtures import operation
from registered_storage_fixtures import request, roots
from claim_fixtures import fixture as claim_fixture, operation as claim_operation
from generator_release_fixtures import metadata as release_metadata
from test_filesystem_evidence import metadata
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard
from test_run_journal import CancelSwitch
from test_run_plan import reference
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


@pytest.mark.parametrize("source", [False, True])
def test_real_scope_installed_store(
    tmp_path: Path, installed_sources: InstalledFixture, source: bool
) -> None:
    execution, accounting_raw = actual_slurm_execution()
    root = tmp_path / "storage"
    root.mkdir()
    roots(root)
    command = request(root, create=True, installation=installed_sources)
    config = command.config
    owner = command.binding.owner.model_copy(update={"job_id": execution.job_id})
    run = RunBinding(
        owner=owner,
        plan_ref=reference("run-plan/3"),
        release_ref=config.installation.manifest_ref,
        submission_key="engineering",
    )
    claim = None
    ledger = None
    fixture = None
    frozen_plan = None
    if source:
        control_root = tmp_path / "control-plane"
        control_root.mkdir()
        fixture = claim_fixture(control_root)
        # Publish the ACTUAL installed manifest and a plan containing its exact ref.
        installed_ref = fixture.store.put(
            config.installation.manifest.model_dump_json().encode(),
            release_metadata("release-manifest/1"),
        )
        assert installed_ref == config.installation.manifest_ref
        old_plan = fixture.plans.load(
            fixture.binding.run, claim_operation(fixture.binding)
        )
        plan = RunPlan.model_validate(
            old_plan.model_copy(
                update={"release_ref": installed_ref, "purpose": "engineering"}
            )
        )
        owner = owner.model_copy(update={"run_id": plan.run_id})
        run = run.model_copy(update={"owner": owner})
        provisional = SourceClaimBinding(
            scope_id="unit-scope", run=run, task=plan.tasks[0]
        )
        plan_ref = fixture.plans.publish(plan, claim_operation(provisional))
        run = run.model_copy(update={"plan_ref": plan_ref})
        claim = provisional.model_copy(update={"run": run})
        fixture = replace(fixture, binding=claim)
        ledger = fixture.ledger()
        ledger.claim(claim, claim_operation(claim))
        frozen_plan = plan
    binding = command.binding.model_copy(
        update={
            "owner": owner,
            "scope": "source" if source else "run",
            "source_task_id": (
                claim.task.identity.source_task_id if claim is not None else None
            ),
        }
    )
    # Both fixture trees share this canonical per-job temporary workspace.
    workspace = Path(
        os.path.commonpath([str(tmp_path), str(installed_sources.workspace)])
    )
    scope = StorageScope(
        binding=binding,
        config=config,
        run=run,
        writer=current_process_identity(),
        execution=execution,
        workspace_root=str(workspace),
        claim=claim,
    )
    launch, publication = selection(scope, frozen_plan)
    if claim is not None:
        assert launch.scope.claim == claim
    scope = launch.scope
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    current = current_store(publication_root)
    current.initialize(publication.initialized_by)
    current.activate(publication.switches[0])
    clock = SystemClock()
    publication_reader = StoragePublicationReader(
        publication_root, launch, OperationGuards(clock, CancelSwitch())
    )
    claim_reader = (
        StorageClaimReader(
            fixture.root / "claims",
            scope,
            OperationGuards(clock, CancelSwitch()),
            fixture.authority,
        )
        if fixture is not None
        else None
    )
    assembled = assemble_slurm_evidence_store(
        launch,
        publication_reader,
        claim_reader,
        operation(scope),
        clock,
        OperationGuards(clock, CancelSwitch()),
        guard(60),
        max_io_seconds=60,
        cleanup_seconds=60,
    )
    assert assembled.launch == launch and assembled.publication == publication
    publication_execution = publication_reader.last_execution
    assert publication_execution is not None
    assert publication_execution.reply.worker.process_id != scope.writer.process_id
    assert publication_execution.capture.termination is not None
    assert publication_execution.capture.termination.state == "reaped"
    # A later explicit publication cannot change this already selected run.
    current.activate(
        ReleaseSwitch(
            expected_revision=1,
            activation=launch.activation,
            operation=publication_op("later-publication"),
        )
    )
    assert assembled.store.state == "new"
    assert not list((root / "sessions").iterdir())
    assembled.store.initialize(guard(60))
    ref = assembled.store.put(b"actual admitted scope", metadata(), guard(60))
    assert assembled.store.read(ref, guard(60)) == b"actual admitted scope"
    exchange = assembled.store.last_exchange
    assert exchange is not None and exchange.reusable
    if fixture is not None:
        assert claim_reader is not None and claim_reader.last_execution is not None
        assert (
            claim_reader.last_execution.reply.worker.process_id
            != scope.writer.process_id
        )
        assert fixture.authority.read_calls == 1
        assert assembled.admission.source_record is not None
    observed = assembled.admission.activation_observation
    assert observed is not None and observed.capture.reads and observed.capture.controls
    assert observed.membership.writer == scope.writer
    assert observed.membership.job_id == execution.job_id
    assembled.admission.stop_new_io()
    before = {
        path: path.read_bytes()
        for path in (root / "sessions").iterdir()
        if path.is_file()
    }
    with pytest.raises(InvalidTransition):
        assembled.store.put(b"stopped", metadata(), guard(60))
    assert all(path.read_bytes() == data for path, data in before.items())
    output = (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / f"storage-scope-{source}.json"
    )
    output.write_text(
        json.dumps(
            {
                "engineering_only": True,
                "concrete_publication_reader": True,
                "publication_worker": publication_execution.reply.worker.model_dump(
                    mode="json"
                ),
                "publication_worker_phase": publication_execution.reply.phase,
                "selected_publication_revision": assembled.publication.revision,
                "current_revision_after_selection": current.read(
                    publication_op("check")
                ).revision,
                "execution": execution.model_dump(mode="json"),
                "accounting": accounting_raw.decode(),
                "membership": observed.membership.model_dump(mode="json"),
                "claim_read_once": fixture.authority.read_calls if fixture else None,
                "claim_worker": (
                    claim_reader.last_execution.reply.worker.model_dump(mode="json")
                    if claim_reader and claim_reader.last_execution
                    else None
                ),
                "snapshot": (
                    exchange.snapshot.model_dump(mode="json")
                    if exchange.snapshot
                    else None
                ),
            },
            indent=2,
        )
    )
