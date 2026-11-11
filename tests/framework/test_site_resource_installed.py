"""Real fixed site worker plus persistent journal; explicitly engineering admission.

The test authority permits only this fresh private fixture and verifies actual
kernel/raw facts. It is not production release/source authority or hard-I/O proof.
"""

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal
import urllib.request
import pytest
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.sites.worker_client import SiteWorkerFailure
from lab_generate_skill.adapters.processes.remote_errors import (
    RemoteError,
    describe_error,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_process_cgroup
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceReady,
    SiteResourceAttempt,
    SiteStepClosed,
)
from lab_generate_skill.domain.site_worker import (
    SiteWorkerConfiguration,
    SiteInstanceStarted,
)
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRecoverySnapshot,
    ProductRestored,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
    ProductState,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRecoverySnapshot,
    OrderEtaRestored,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import OrderEtaState
from lab_generate_skill.sites.reddit.tasks.image_recovery import (
    ImageRecoverySnapshot,
    ImageRestored,
    ImageObserved,
)
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRecoverySnapshot,
    GroupRestored,
    GroupObserved,
)
from gitlab_source_selection import check_gitlab_task
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRecoverySnapshot,
    SshKeyRestored,
    SshKeyObserved,
)
from test_site_task_execution import request as task_request
from site_preparation_native import NativePreparation
from source_task_hooks import SourceTaskHooks
from test_slurm_commands import guard
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.lifecycle import OperationContext, ClosureReceipt
from lab_generate_skill.domain.process_identity import ProcessTermination
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import Case, Authority, resource_case
from site_worker_fixtures import configuration
from test_site_resource import inspect
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from storage_installation_fixtures import storage_installation
from test_admin_database_native import IMAGE, IMAGE_SHA
from test_linux_cgroups import actual_slurm_execution


class EngineeringAuthority(Authority):
    def __init__(self, case: Case, parent: Path) -> None:
        super().__init__(case.evidence)
        self.case, self.parent = case, parent
        self.ready: SiteResourceReady | None = None
        self.before_native = False
        self.closed: SiteStepClosed | None = None
        self.task_intents: dict[str, EvidenceRef] = {}
        self.task_input: str | None = None

    def authorize_spawn(
        self, spec: SiteResourceSpec, op: OperationContext, control: OperationControl
    ) -> None:
        assert spec == self.case.spec and op == self.case.op
        assert Path(spec.configuration.files.node_root) == self.parent / "instance"
        assert (
            self.parent.resolve(strict=True) == self.parent
            and not self.parent.is_symlink()
        )
        assert self.parent.stat().st_uid == os.getuid()
        assert (
            observe_process_cgroup(
                spec.slurm.execution, spec.slurm.parent.writer, control
            ).membership
            == spec.slurm.parent
        )

    def verify_ready(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify_ready(spec, ready, op, control)
        assert ready.worker.owner_guard.controller == spec.slurm.parent.writer
        target = ready.controller.target
        assert (
            observe_process_cgroup(
                spec.slurm.execution, ready.worker.owner_guard.worker, control
            ).membership
            == target.worker
        )
        raw = json.loads(self.store.read(ready.evidence, control=control))
        assert (
            raw["target"] == target.model_dump(mode="json")
            and raw["kernel"]
            and raw["commands"]
        )
        assert not Path(spec.configuration.files.node_root).exists()
        self.ready = ready

    def verify(
        self,
        config: SiteWorkerConfiguration,
        phase: Literal["configure", "start", "close"],
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        super().verify(config, phase, op, control)
        if phase == "start":
            assert self.ready is not None
            record = self.case.journal.read(config.token, op)
            assert record.state == "acquired"
            payload = json.loads(
                self.store.read(record.events[-1].evidence[0], control=control)
            )
            assert payload["details"]["ready"] == self.ready.model_dump(mode="json")
            assert payload["details"]["site_started"] is False
            assert not Path(config.files.node_root).exists()
            self.before_native = True

    def verify_task(
        self,
        config: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        # Engineering admission for this exact fixture only. The persisted input
        # is not a formal source claim or a production task intent implementation.
        assert config == self.case.spec.configuration and self.before_native
        request.check_site(config)
        intent = self.task_intents[request.operation.operation_id]
        assert (
            self.store.read(intent, control=control)
            == request.model_dump_json().encode()
        )
        assert self.task_input is not None and request.private_input == self.task_input
        if request.action != "snapshot":
            assert request.snapshot_ref is not None
            snapshot_type = (
                ImageRecoverySnapshot
                if config.site_id == "reddit"
                else (
                    (
                        GroupRecoverySnapshot
                        if check_gitlab_task(config, request.task)
                        else SshKeyRecoverySnapshot
                    )
                    if config.site_id == "gitlab"
                    else (
                        OrderEtaRecoverySnapshot
                        if config.site_id == "shopping"
                        else ProductRecoverySnapshot
                    )
                )
            )
            original = snapshot_type.model_validate_json(
                self.store.read(request.snapshot_ref, control=control)
            )
            assert (
                original.request.task == request.task
                and original.request.binding_ref == request.binding_ref
            )
            if isinstance(
                original,
                (
                    OrderEtaRecoverySnapshot,
                    SshKeyRecoverySnapshot,
                    GroupRecoverySnapshot,
                    ImageRecoverySnapshot,
                ),
            ):
                assert original.state.service.files == config.files
            else:
                assert (
                    original.state.plan.service.layout.node_root
                    == config.files.node_root
                )
                assert (
                    original.state.plan.service.layout.image_sha256
                    == config.files.image.sha256
                )
        assert (
            self.case.journal.read(
                config.token,
                self.case.op.cleanup(
                    "task-ledger-" + request.operation.operation_id,
                    now=datetime.now(timezone.utc),
                    seconds=10,
                ),
            ).state
            == "acquired"
        )

    def verify_started(
        self,
        spec: SiteResourceSpec,
        ready: SiteResourceReady,
        started: SiteInstanceStarted,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        assert self.before_native and self.ready == ready
        assert started.files == spec.configuration.files
        control.checkpoint()

    def verify_closed(
        self,
        spec: SiteResourceSpec,
        attempt: SiteResourceAttempt,
        termination: ProcessTermination | None,
        closed: SiteStepClosed | None,
        op: OperationContext,
        control: OperationControl,
    ) -> ClosureReceipt:
        assert self.before_native and self.ready is not None
        assert attempt.ready == self.ready and attempt.start_attempted
        assert (
            termination is not None
            and termination.state == "reaped"
            and not termination.cleanup_errors
        )
        assert closed is not None and closed.target == attempt.target
        raw = json.loads(self.store.read(closed.evidence, control=control))
        assert raw["phase"] == "closed" and raw["target"] == closed.target.model_dump(
            mode="json"
        )
        assert raw["kernel"] and raw["commands"]
        # Residual files remain isolated under this fresh predeclared root. The
        # test owner disposes them only after the closed journal is read back.
        proof = self.store.put(
            json.dumps(
                {
                    "engineering_only": True,
                    "attempt": attempt.model_dump(mode="json"),
                    "termination": asdict(termination),
                    "closed": closed.model_dump(mode="json"),
                    "residual_files": "retained_private_no_reuse",
                }
            ).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="engineering-site-close/1",
                visibility="private",
                producer="actual-site-engineering",
            ),
            control=control,
        )
        self.closed = closed
        return ClosureReceipt(
            token=spec.token,
            operation_id=op.operation_id,
            status="closed",
            evidence=(proof,),
        )


def has_deadline(error: BaseException) -> bool:
    def remote(value: RemoteError) -> bool:
        return (
            value.reason_code == "DEADLINE_EXCEEDED"
            or any(remote(c) for c in value.children)
            or (value.cause is not None and remote(value.cause))
        )

    if isinstance(error, OperationStopped):
        return error.reason_code == "DEADLINE_EXCEEDED"
    if isinstance(error, SiteWorkerFailure):
        return error.reply.error is not None and remote(error.reply.error)
    return isinstance(error, BaseExceptionGroup) and any(
        has_deadline(e) for e in error.exceptions
    )


def run_registered_site_case(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    *,
    task_hooks: SourceTaskHooks | None = None,
    site_id: Literal[
        "shopping_admin", "shopping", "gitlab", "reddit"
    ] = "shopping_admin",
) -> None:
    if task_hooks is not None and task_hooks.map_selection is not None:
        raise ValueError(
            "Selected Map input requires its separate original map source entry"
        )
    if (
        task_hooks is not None
        and task_hooks.reddit_selection is not None
        and (site_id != "reddit" or mode not in ("qualified_source", "actor_source"))
    ):
        raise ValueError("Selected Reddit input requires its original source entry")
    if task_hooks is not None and task_hooks.gitlab_selection is not None:
        if site_id != "gitlab" or mode not in ("qualified_source", "actor_source"):
            raise ValueError("Selected GitLab input requires its original source entry")
    if site_id == "gitlab" and (
        task_hooks is None or task_hooks.gitlab_selection is None
    ):
        raise ValueError("GitLab source requires an explicit original selection")
    gitlab_group = (
        site_id == "gitlab"
        and task_hooks is not None
        and task_hooks.gitlab_selection is not None
        and task_hooks.gitlab_selection.group
    )
    # Selected Shopping qualification can isolate login/Observation/reset before
    # spending time on Qwen. It creates no Actor or formal-source permission.
    assert site_id == "shopping_admin" or (
        mode == "qualified_source"
        or (mode == "actor_source" and task_hooks is not None)
    )
    execution, _ = actual_slurm_execution()
    parent = Path(tempfile.mkdtemp(prefix="lab-registered-site-", dir="/tmp"))
    from site_resource_native_plan import native_configuration, startup_seconds

    config = native_configuration(
        storage_installation(installed_sources),
        job_id=execution.job_id,
        parent=parent,
        site_id=site_id,
        private_evidence=None if task_hooks is None else task_hooks.private_site_plan,
    )
    if task_hooks is not None:
        if config.private_evidence is not None:
            assert config.token.owner == task_hooks.owner
        else:
            config = config.model_copy(
                update={
                    "token": config.token.model_copy(update={"owner": task_hooks.owner})
                }
            )
    c = resource_case(
        tmp_path,
        monkeypatch,
        config=config,
        real_step=True,
        store=None if task_hooks is None else task_hooks.evidence,
    )
    state_spec = None
    if mode in ("qualified_source", "captured_source", "actor_source"):
        from qualified_source_native import configure_qualification

        state_spec = configure_qualification(
            c,
            reddit_selection=(
                None if task_hooks is None else task_hooks.reddit_selection
            ),
            gitlab_selection=(
                None if task_hooks is None else task_hooks.gitlab_selection
            ),
        )
    c.op = c.op.model_copy(
        update={
            "deadline": datetime.now(timezone.utc)
            + timedelta(
                seconds=30 if mode == "prepare_deadline" else startup_seconds(site_id)
            )
        }
    )
    authority = EngineeringAuthority(c, parent)
    c.authority = authority
    facts: dict[str, Any] = {
        "passed": False,
        "engineering_only": True,
        "formal_site_authority": False,
        "synchronous_test_evidence": True,
        "mode": mode,
        "site_id": site_id,
        "private_root": str(parent),
    }
    output = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
    try:
        caught: BaseException | None = None
        try:
            with registered_site(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=authority,
            ) as site:
                assert (
                    mode != "prepare_deadline"
                ), "Partial preparation should expire before usable site"
                if mode not in ("qualified_source", "captured_source", "actor_source"):
                    with urllib.request.build_opener(
                        urllib.request.ProxyHandler({})
                    ).open(site.site.instance.endpoint, timeout=10) as response:
                        body = response.read(1024 * 1024 + 1)
                        assert (
                            response.status == 200
                            and len(body) <= 1024 * 1024
                            and b"login" in body.lower()
                        )
                facts["started"] = site.site.model_dump(mode="json")
                qualification = None
                if mode in ("qualified_source", "captured_source", "actor_source"):
                    from qualified_source_native import QualifiedSource

                    assert state_spec is not None
                    qualification = QualifiedSource(
                        c,
                        site,
                        state_spec,
                        allowed_actions=(
                            None if task_hooks is None else task_hooks.allowed_actions
                        ),
                        reddit_selection=(
                            None if task_hooks is None else task_hooks.reddit_selection
                        ),
                        gitlab_selection=(
                            None if task_hooks is None else task_hooks.gitlab_selection
                        ),
                    )
                    native_preparation = qualification.native
                else:
                    native_preparation = NativePreparation(
                        c, site.site.instance.endpoint
                    )
                authority.task_input = native_preparation.private_input_json()
                task_results = []
                snapshot_ref = None
                snapshot = None
                preparation = None
                # The qualified source uses its actual browser initial view;
                # the unchanged standalone inspect RPC is covered by4772547.
                actions = (
                    ("snapshot", "prepare", "restore")
                    if qualification is not None
                    else ("snapshot", "prepare", "inspect", "restore")
                )
                for action in actions:
                    template = task_request("prepare", "native-task-" + action)
                    seconds = (
                        (600 if action in ("snapshot", "restore") else 180)
                        if site_id in ("gitlab", "reddit")
                        else (
                            (300 if action == "snapshot" else 180)
                            if site_id == "shopping"
                            else (120 if action in ("snapshot", "restore") else 60)
                        )
                    )
                    if action == "restore":
                        assert preparation is not None
                        operation = preparation.operation.cleanup(
                            "native-task-restore",
                            now=datetime.now(timezone.utc),
                            seconds=seconds,
                        )
                    else:
                        operation = c.op.model_copy(
                            update={
                                "operation_id": "native-task-" + action,
                                "attempt_id": native_preparation.attempt_id,
                                "recovery_ref": native_preparation.recovery_ref,
                                "deadline": datetime.now(timezone.utc)
                                + timedelta(seconds=seconds),
                            }
                        )
                    request = SiteTaskRequest.model_validate(
                        {
                            **template.model_dump(),
                            "action": action,
                            "operation": operation,
                            "snapshot_ref": snapshot_ref,
                            "binding_ref": native_preparation.binding_ref,
                            "private_input": authority.task_input,
                            "task": native_preparation.public.identity,
                        }
                    )
                    intent = c.evidence.put(
                        request.model_dump_json().encode(),
                        EvidenceMetadata(
                            media_type="application/json",
                            content_schema="engineering-site-task-intent/1",
                            visibility="private",
                            producer="actual-site-engineering",
                        ),
                        control=guard(10),
                    )
                    authority.task_intents[request.operation.operation_id] = intent
                    result = site.tasks.execute_task(request, control=guard(seconds))
                    assert result.request_sha256 == request.digest
                    if action == "snapshot":
                        snapshot_type = (
                            ImageRecoverySnapshot
                            if site_id == "reddit"
                            else (
                                (
                                    GroupRecoverySnapshot
                                    if gitlab_group
                                    else SshKeyRecoverySnapshot
                                )
                                if site_id == "gitlab"
                                else (
                                    OrderEtaRecoverySnapshot
                                    if site_id == "shopping"
                                    else ProductRecoverySnapshot
                                )
                            )
                        )
                        snapshot = snapshot_type.model_validate_json(
                            result.private_result
                        )
                        assert snapshot.request == request
                        if isinstance(snapshot, ProductRecoverySnapshot):
                            assert snapshot.product.absent
                        snapshot_ref = c.evidence.put(
                            result.private_result.encode(),
                            EvidenceMetadata(
                                media_type="application/json",
                                content_schema=snapshot.schema_version,
                                visibility="private",
                                producer="actual-site-engineering",
                            ),
                            control=guard(10),
                        )
                        assert (
                            c.evidence.read(snapshot_ref)
                            == result.private_result.encode()
                        )
                        facts["snapshot_persisted_before_prepare"] = True
                        if qualification is not None:
                            qualification.after_snapshot(request, result, snapshot_ref)
                            facts["reset_plan_persisted_before_prepare"] = (
                                qualification.plan_ref.model_dump(mode="json")
                            )
                    elif action == "restore":
                        restored_type = (
                            ImageRestored
                            if site_id == "reddit"
                            else (
                                (GroupRestored if gitlab_group else SshKeyRestored)
                                if site_id == "gitlab"
                                else (
                                    OrderEtaRestored
                                    if site_id == "shopping"
                                    else ProductRestored
                                )
                            )
                        )
                        restored = restored_type.model_validate_json(
                            result.private_result
                        )
                        if isinstance(
                            restored,
                            (
                                OrderEtaRestored,
                                SshKeyRestored,
                                GroupRestored,
                                ImageRestored,
                            ),
                        ):
                            if isinstance(restored, ImageRestored):
                                assert isinstance(snapshot, ImageRecoverySnapshot)
                            elif isinstance(restored, GroupRestored):
                                assert isinstance(snapshot, GroupRecoverySnapshot)
                            elif isinstance(restored, SshKeyRestored):
                                assert isinstance(snapshot, SshKeyRecoverySnapshot)
                            else:
                                assert isinstance(snapshot, OrderEtaRecoverySnapshot)
                            assert (
                                restored.request == request
                                and restored.snapshot == snapshot
                            )
                            assert restored.request.snapshot_ref == snapshot_ref
                            assert restored.inventory == snapshot.state.inventory
                            facts["whole_tree_restored_before_resume"] = (
                                restored.model_dump(mode="json")
                            )
                        else:
                            assert isinstance(snapshot, ProductRecoverySnapshot)
                            assert restored.snapshot_ref == snapshot_ref
                            assert (
                                restored.operation == request.operation
                                and restored.product.absent
                            )
                            assert (
                                restored.state.snapshot_sha256 == snapshot.state.digest
                            )
                            assert (
                                restored.state.search.original == snapshot.state.search
                            )
                            assert (
                                restored.state.search.restored_data_streams
                                == snapshot.state.search.data_streams
                            )
                            assert (
                                restored.frontend.service == snapshot.state.plan.service
                            )
                            assert restored.frontend.backend.drained
                            facts["frontend_stopped_before_restore"] = (
                                restored.frontend.model_dump(mode="json")
                            )
                            facts["search_state_restored"] = True
                            facts["product_absent_after_restore"] = True
                        facts["complete_site_reset"] = False
                        if mode == "resumed_frontend":
                            from site_resume_native import resume_original

                            facts["frontend_resumption"] = resume_original(
                                c, site, request, result
                            )
                        if qualification is not None:
                            facts["qualified_source"] = qualification.after_restore(
                                request, result
                            )
                    else:
                        if site_id == "reddit":
                            image_state = ImageObserved.model_validate_json(
                                result.private_result
                            )
                            assert (
                                image_state.request == request
                                and image_state.snapshot == snapshot
                            )
                        elif site_id == "gitlab":
                            gitlab_observed_type = (
                                GroupObserved if gitlab_group else SshKeyObserved
                            )
                            ssh_state = gitlab_observed_type.model_validate_json(
                                result.private_result
                            )
                            assert (
                                ssh_state.request == request
                                and ssh_state.snapshot == snapshot
                            )
                        elif site_id == "shopping":
                            eta_state = OrderEtaState.model_validate_json(
                                result.private_result
                            )
                            assert eta_state.task == native_preparation.public.identity
                        else:
                            state = ProductState.model_validate_json(
                                result.private_result
                            )
                            assert (
                                state.product_id == 2041
                                and state.sku == "TRAIN-sony-headphones"
                            )
                            assert state.description in (
                                None,
                                "",
                            ) and state.short_description in (None, "")
                        if action == "prepare":
                            preparation = request
                            facts["preparation_records"] = native_preparation.publish(
                                request,
                                result,
                                site.site.instance,
                                environment=(
                                    None
                                    if qualification is None
                                    else qualification.environment
                                ),
                            )
                            if mode in ("captured_source", "actor_source"):
                                from site_capture_native import capture_original

                                facts["catalog_before"] = capture_original(
                                    c, site, request, "before"
                                )
                            if qualification is not None:
                                from lab_generate_skill.domain.preparation_record import (
                                    PreparedPublication,
                                )

                                facts["prepared_browser"] = qualification.observe(
                                    PreparedPublication.model_validate(
                                        facts["preparation_records"]["publication"]
                                    ),
                                    tmp_path / "qualified-browser",
                                    monkeypatch,
                                    on_session=(
                                        None
                                        if task_hooks is None
                                        else task_hooks.session(qualification)
                                    ),
                                )
                            if mode in ("captured_source", "actor_source"):
                                facts["catalog_after"] = capture_original(
                                    c, site, request, "after"
                                )
                                if task_hooks is None:
                                    assert (
                                        facts["catalog_before"]["catalog"]
                                        == facts["catalog_after"]["catalog"]
                                    )
                                else:
                                    assert qualification is not None
                                    task_hooks.evaluate(qualification, facts)
                        elif mode == "prepared_browser":
                            from prepared_browser_native import observe_prepared
                            from lab_generate_skill.domain.preparation_record import (
                                PreparedPublication,
                            )

                            facts["prepared_browser"] = observe_prepared(
                                native_preparation,
                                site.site,
                                PreparedPublication.model_validate(
                                    facts["preparation_records"]["publication"]
                                ),
                                tmp_path / "prepared-browser",
                                monkeypatch,
                            )
                    task_results.append(
                        {
                            "request": request.model_dump(mode="json"),
                            "result": result.model_dump(mode="json"),
                            "intent": intent.model_dump(mode="json"),
                        }
                    )
                if qualification is None:
                    assert (
                        task_results[1]["result"]["private_result"]
                        == task_results[2]["result"]["private_result"]
                    )
                facts["task_rpc"] = task_results
                facts["task_rpc_engineering_only"] = True
        except BaseException as error:
            caught = error
            facts["operation_error"] = describe_error(error).model_dump(mode="json")
        if mode != "prepare_deadline":
            if caught is not None:
                raise caught
        else:
            assert caught is not None and has_deadline(caught)
            assert (
                parent / "instance"
            ).is_dir(), "Need actual partial native preparation"
        record = inspect(c)
        assert (
            record.state == "closed"
            and authority.before_native
            and authority.closed is not None
        )
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        ending = json.loads(c.evidence.read(record.events[-1].evidence[0]))
        assert ending["details"]["cleanup_errors"] == []
        capture_ref = EvidenceRef.model_validate(
            ending["details"]["worker_capture_ref"]
        )
        capture = json.loads(c.evidence.read(capture_ref))
        facts.update(
            passed=True,
            record=record.model_dump(mode="json"),
            ending=ending,
            worker_capture=capture,
            original_domain=authority.closed.model_dump(mode="json"),
            identity_persisted_before_native_start=True,
        )
    finally:
        if (
            site_id in ("shopping", "gitlab", "reddit")
            and authority.closed is not None
            and not facts["passed"]
        ):
            from shopping_native_diagnostics import retain_startup_logs

            diagnostics = output / ("site-startup-diagnostics-" + mode)
            try:
                diagnostics.mkdir(mode=0o700)
                facts["startup_logs"] = retain_startup_logs(
                    c.spec.configuration.files, diagnostics
                )
            except BaseException as diagnostic:
                # Preserve the original thrown operation and retain secondary
                # diagnostics separately, never turn a failed run into pass.
                facts["diagnostic_error"] = describe_error(diagnostic).model_dump(
                    mode="json"
                )
        safe = authority.closed is not None and facts["passed"]
        if safe:
            assert parent.resolve(strict=True) == parent and not parent.is_symlink()
            shutil.rmtree(parent)
        facts["private_root_removed"] = safe and not parent.exists()
        (output / ("registered-site-" + mode + ".json")).write_text(
            json.dumps(facts, indent=2) + "\n"
        )


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "prepare_deadline",
        "prepared_browser",
        "resumed_frontend",
        "qualified_source",
        "captured_source",
    ],
)
def test_registered_actual_site_and_original_domain_close(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    run_registered_site_case(installed_sources, tmp_path, monkeypatch, mode)
