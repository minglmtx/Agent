"""Fresh private real Group initialization/restoration only; no Actor or source replay."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRecoverySnapshot,
    GroupObserved,
)
from lab_generate_skill.sites.gitlab.tasks.group_capture import same_group_state
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.sites.gitlab.tasks.group_request import task_input
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from qualified_source_native import QualifiedSource
from browser_resource_fixtures import ResourceCase
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from evidence_control_fixtures import EvidenceFixtureStore
from source_task_hooks import SourceTaskHooks
from gitlab_source_selection import group_selection
from gitlab_site_native_plan import private_site_plan
from site_worker_fixtures import configuration
from storage_installation_fixtures import storage_installation
from test_linux_cgroups import actual_slurm_execution
from test_site_resource_installed import run_registered_site_case
from generator_engine_live import verify_source
from source_review_records import ReadOnlyEvidence, review_resource, review_state
from gitlab_actor_review import review_gitlab_reset
from test_resource_journal import NoCancellation


def observe_only_group(
    source: QualifiedSource,
    browser: ResourceCase,
    session: EvidenceBrowserSession,
    observed: dict[str, Any],
) -> None:
    assert source.gitlab_selection is not None and source.gitlab_selection.group
    assert source.saved["baseline"].status == "ready"
    assert source.saved["baseline"].observation_ref == session.observation_ref
    assert browser.spec.configuration.spec.task == source.native.public
    observed["group_no_actor_observer"] = dict(
        identity=source.native.public.identity.model_dump(mode="json"),
        original_initial_ref=source.saved["baseline"].observation_ref.model_dump(
            mode="json"
        ),
        Actor_calls=0,
    )


def no_judgment(source: QualifiedSource, facts: dict[str, Any]) -> None:
    raise AssertionError("Initialization-only scope cannot evaluate an Actor task")


def test_actual_private_group_initialization_unique_initial_full_restore(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = Path(__file__).resolve().parents[2]
    receipt = Path(os.environ["LAB_GROUP_SOURCE_SOFTWARE_RECEIPT"])
    verify_source(receipt, source_root=project)
    execution, _ = actual_slurm_execution()
    selected = group_selection()
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "group-initialization-only"
    output.mkdir(mode=0o700)
    resource = output / "resource"
    resource.mkdir(mode=0o700)
    evidence_root = resource / "evidence"
    evidence_root.mkdir(mode=0o700)
    sessions = resource / "site-private-sessions"
    sessions.mkdir(mode=0o700)
    base = configuration(job_id=execution.job_id)
    plan = private_site_plan(
        base.token.owner,
        storage_installation(installed_sources),
        evidence_root=evidence_root,
        session_root=sessions,
        journal_root=tmp_path / "journal",
        selection=selected,
    )
    declaration = dict(
        engineering_only=True,
        formal_source_admission=False,
        original_whole_source_executions=0,
        Actor_calls=0,
        paid_API_calls=0,
        site="gitlab",
        mode="qualified_source",
        identity=selected.public_template.identity.model_dump(mode="json"),
        original_contract_sha256=selected.reference().sha256,
        software_receipt=str(receipt),
        execution_source=str(project),
        evidence_root=str(evidence_root),
        private_profile=plan.profile.model_dump(mode="json"),
    )
    (output / "declaration.json").write_text(json.dumps(declaration, indent=2) + "\n")
    hooks = SourceTaskHooks(
        base.token.owner,
        EvidenceFixtureStore(evidence_root),
        selected.public_template.allowed_actions,
        observe_only_group,
        no_judgment,
        private_site_plan=plan,
        gitlab_selection=selected,
    )
    run_registered_site_case(
        installed_sources,
        tmp_path,
        monkeypatch,
        "qualified_source",
        task_hooks=hooks,
        site_id="gitlab",
    )
    verify_source(receipt, source_root=project)


def test_independent_readonly_actual_group_initialization_and_full_reset() -> None:
    root = Path(os.environ["LAB_GROUP_SOURCE_INITIALIZATION_ROOT"])
    declaration_path = root / "group-initialization-only/declaration.json"
    facts_path = root / "registered-site-qualified_source.json"
    declaration_raw, facts_raw = declaration_path.read_bytes(), facts_path.read_bytes()
    declaration, facts = json.loads(declaration_raw), json.loads(facts_raw)
    project, receipt = Path(declaration["execution_source"]), Path(
        declaration["software_receipt"]
    )
    verify_source(receipt, source_root=project)
    assert (
        declaration["Actor_calls"]
        == declaration["paid_API_calls"]
        == declaration["original_whole_source_executions"]
        == 0
    )
    assert (
        facts["passed"]
        and facts["site_id"] == "gitlab"
        and facts["mode"] == "qualified_source"
    )
    assert facts["private_root_removed"] and not Path(facts["private_root"]).exists()
    assert (
        "actor" not in facts
        and "catalog_before" not in facts
        and "catalog_after" not in facts
    )
    store = ReadOnlyEvidence(Path(declaration["evidence_root"]))
    controls = OperationGuards(SystemClock(), NoCancellation())
    from lab_generate_skill.domain.lifecycle import OperationContext

    operation = OperationContext(
        operation_id="readonly-group-initialization-review",
        run_id="run",
        owner_id="owner",
        mode="cleanup",
        parent_operation_id="group-initialization-only",
        deadline=datetime.now(timezone.utc),
    )
    operation = operation.cleanup(
        "readonly-group-initialization-review-control",
        now=datetime.now(timezone.utc),
        seconds=120,
    )
    control = controls.bind(operation)
    initial, reset = review_state(facts, store, control)
    assert initial.public_task.identity == group_selection().public_template.identity
    assert (
        initial.public_task.identity.model_dump(mode="json") == declaration["identity"]
    )
    assert initial.observation.sequence == 0
    assert reset.plan.attempt_allocations == (reset.closures[0].token,)
    source_record = ResourceRecord.model_validate_json(json.dumps(facts["record"]))
    source = review_resource(facts["record"], source_record.token, store, control)
    browser = review_resource(
        facts["prepared_browser"]["browser_record"],
        reset.closures[0].token,
        store,
        control,
    )
    review_gitlab_reset(facts, reset, store, control)
    assert [x["request"]["action"] for x in facts["task_rpc"]] == [
        "snapshot",
        "prepare",
        "restore",
    ]
    snapshot_result = SiteTaskResult.model_validate_json(
        json.dumps(facts["task_rpc"][0]["result"])
    )
    snapshot = GroupRecoverySnapshot.model_validate_json(snapshot_result.private_result)
    prepared_result = SiteTaskResult.model_validate_json(
        json.dumps(facts["task_rpc"][1]["result"])
    )
    prepared = GroupObserved.model_validate_json(prepared_result.private_result)
    before = load_group_capture(
        store.read(snapshot.native_before.payload_ref, control),
        task_input(snapshot.request),
    )
    after = load_group_capture(
        store.read(prepared.native.payload_ref, control), task_input(prepared.request)
    )
    assert same_group_state(before, after)
    assert (
        source["configuration"]["configuration"]["private_evidence"]["profile"]
        == declaration["private_profile"]
    )
    assert (
        declaration_path.read_bytes() == declaration_raw
        and facts_path.read_bytes() == facts_raw
    )
    verify_source(receipt, source_root=project)
    result = dict(
        engineering_only=True,
        original_whole_source_executions=0,
        Actor_calls=0,
        paid_API_calls=0,
        independent_process=os.getpid(),
        original_job_root=str(root),
        original_execution_source=str(project),
        read_only=True,
        identity=declaration["identity"],
        baseline="ready",
        reset="safe",
        full_original_native_JSON_and_COPY_preserved=True,
        original_site_and_browser_resources="closed",
        private_root_removed=True,
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "group-initialization-independent-review.json"
    ).write_text(json.dumps(result, indent=2) + "\n")
