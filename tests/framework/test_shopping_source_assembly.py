"""Actual engineering adapters with explicit synthetic native/browser resources.

No website, GPU, kernel-domain or formal source admission is claimed here.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.sites.shopping.tasks.order_eta_resume import OrderEtaResume
from qualified_source_native import QualifiedSource, configure_qualification
from site_capture_native import capture_original
from source_task_evaluation import judge_source_task
from shopping_evaluator_fixtures import EtaEvalCase
from shopping_task_fixtures import case, request
from shopping_services_fixtures import Group
from site_resource_fixtures import resource_case
from site_worker_fixtures import configuration
from test_site_resource import enter
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path
import prepared_browser_native
from browser_resource_fixtures import resource_case as original_browser_case


@pytest.mark.parametrize("fault", ["none", "wrong_snapshot", "missing_closure"])
def test_same_source_preparation_initial_capture_and_original_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    # Match fake service identities to this fixture's host only. They remain
    # synthetic and cannot be used as actual namespace/worker proof.
    host, original_pin = current_process_identity(), Group.pin_namespace

    def pin(group: Group, name: str, control: Any) -> Any:
        value = original_pin(group, name, control)
        value = value.model_copy(
            update={
                key: getattr(value, key).model_copy(
                    update={
                        "node_id": host.node_id,
                        "boot_id": host.boot_id,
                        "start_ticks": host.start_ticks + offset + group.generation,
                    }
                )
                for key, offset in (("launcher", 10), ("init", 20))
            }
        )
        group.pins[-1] = value
        return value

    monkeypatch.setattr(Group, "pin_namespace", pin)
    worker, commands, groups = case(node_path)
    files = worker.instance.files_plan
    base = configuration(job_id="4752096")
    config = base.model_copy(
        update={
            "site_id": "shopping",
            "files": files,
            "token": base.token.model_copy(
                update={"expected_resource_id": files.instance_id}
            ),
        }
    )
    root = tmp_path / "site"
    root.mkdir()
    c = resource_case(root, monkeypatch, config=config)
    policy = configure_qualification(c)
    browsers: list[Any] = []

    def fake_browser(*args: Any, **kwargs: Any) -> Any:
        kwargs["real_step"] = False
        result = original_browser_case(*args, **kwargs)
        browsers.append(result)
        return result

    monkeypatch.setattr(prepared_browser_native, "resource_case", fake_browser)
    monkeypatch.setattr(
        prepared_browser_native,
        "EngineeringTreeAuthority",
        lambda store: browsers[-1].authority,
    )

    with enter(c) as original_site:

        class Parent:
            configuration = config.model_copy(update={"token": c.spec.token})

            def capture_task(
                self, req: Any, intent: Any, authority: Any, *, control: Any
            ) -> Any:
                authority.verify_capture(self.configuration, req, intent, control)
                return worker.capture_task(req, control=control)

            def resume_frontend(
                self, req: Any, intent: Any, authority: Any, *, control: Any
            ) -> Any:
                authority.verify_resume(self.configuration, req, intent, control)
                return OrderEtaResume(worker).resume_frontend(req, control=control)

        parent = Parent()
        live = RegisteredSite(original_site.site, original_site.tasks, parent, parent)
        source = QualifiedSource(c, live, policy)
        n = source.native

        def command(action: str, snapshot: Any = None) -> SiteTaskRequest:
            return SiteTaskRequest.model_validate(
                {
                    **request().model_dump(),
                    "task": n.public.identity,
                    "binding_ref": n.binding_ref,
                    "private_input": n.data.model_dump_json(),
                    "action": action,
                    "snapshot_ref": snapshot,
                    "operation": c.op.model_copy(
                        update={
                            "operation_id": "native-task-" + action,
                            "attempt_id": n.attempt_id,
                            "recovery_ref": n.recovery_ref,
                            "deadline": datetime.now(timezone.utc)
                            + timedelta(seconds=30),
                        }
                    ),
                }
            )

        snapshot_request = command("snapshot")
        snapshot_result = worker.execute_task(snapshot_request, control=guard())
        snapshot_ref = n.raw(
            snapshot_result.private_result.encode(), "shopping-eta-recovery/1"
        )
        if fault == "wrong_snapshot":
            with pytest.raises(AssertionError):
                source.after_snapshot(
                    snapshot_request.model_copy(update={"binding_ref": n.spec_ref}),
                    snapshot_result,
                    snapshot_ref,
                )
            assert "environment_ref" not in source.saved
            return
        source.after_snapshot(snapshot_request, snapshot_result, snapshot_ref)
        prepare = command("prepare", snapshot_ref)
        prepared = worker.execute_task(prepare, control=guard())
        published = n.publish(
            prepare, prepared, live.site.instance, environment=source.environment
        )
        before = capture_original(c, live, prepare, "before")
        observed = source.observe(
            PreparedPublication.model_validate(published["publication"]),
            tmp_path / "browser",
            monkeypatch,
        )
        assert observed["complete_baseline"] and browsers[0].channels[
            0
        ].engine.calls == ["start", "close"]
        after = capture_original(c, live, prepare, "after")
        assert before["catalog"] == after["catalog"]
        assert source.saved["browser_closed_before_restore"]
        restore = SiteTaskRequest.model_validate(
            {
                **prepare.model_dump(),
                "action": "restore",
                "operation": prepare.operation.cleanup(
                    "native-task-restore", now=datetime.now(timezone.utc), seconds=30
                ),
            }
        )
        restored = worker.execute_task(restore, control=guard())
        if fault == "missing_closure":
            source.saved["browser_closed_before_restore"] = False
            with pytest.raises(AssertionError):
                source.after_restore(restore, restored)
            assert worker.instance.state == "restored"
            return
        reset = source.after_restore(restore, restored)
        assert reset["reset_status"] == "safe"
        assert source.saved["reset"].status == "safe" and len(groups) == 3


@pytest.mark.parametrize("missing", [False, True])
def test_shopping_judgment_assembly_uses_original_selected_pairs_and_answer(
    tmp_path: Path, missing: bool
) -> None:
    c = EtaEvalCase(tmp_path)
    source: Any = SimpleNamespace(
        c=SimpleNamespace(
            evidence=c.store,
            spec=SimpleNamespace(configuration=SimpleNamespace(site_id="shopping")),
        ),
        native=SimpleNamespace(
            public=c.public,
            binding=c.binding,
            binding_ref=c.contract.task_contract_ref,
            put=c.put,
        ),
        saved={
            "baseline_inputs": SimpleNamespace(prepared=SimpleNamespace(scope=c.scope))
        },
    )
    facts = {
        "catalog_" + label: pair.model_dump(mode="json")
        for label, pair in (
            ("before", c.selection.before),
            ("after", c.selection.after),
        )
        if pair is not None
    }
    assert c.selection.page is not None
    actor = {
        "trace_ref": (
            c.selection.trace_ref.model_dump(mode="json")
            if c.selection.trace_ref
            else None
        )
    }
    if not missing:
        actor["page_capture"] = c.selection.page.model_dump(mode="json")
    result = judge_source_task(source, facts, actor)
    assert result["evaluation"]["status"] == ("unknown" if missing else "success")


def test_admin_judgment_assembly_preserves_original_four_check_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from product_evaluator_fixtures import EvalCase
    from lab_generate_skill.evaluators.shopping_admin.product_description import (
        ProductDescriptionEvaluator,
    )

    c = EvalCase(tmp_path, monkeypatch)
    source: Any = SimpleNamespace(
        c=SimpleNamespace(
            evidence=c.store,
            spec=SimpleNamespace(
                configuration=SimpleNamespace(site_id="shopping_admin")
            ),
        ),
        native=SimpleNamespace(
            public=c.public,
            binding=c.binding,
            binding_ref=c.contract.task_contract_ref,
            put=c.put,
        ),
        saved={
            "baseline_inputs": SimpleNamespace(
                prepared=SimpleNamespace(scope=c.trace.scope)
            )
        },
    )
    assert (
        c.selection.before is not None
        and c.selection.after is not None
        and c.selection.page is not None
        and c.selection.trace_ref is not None
    )
    facts = {
        "catalog_before": c.selection.before.model_dump(mode="json"),
        "catalog_after": c.selection.after.model_dump(mode="json"),
    }
    actor = {
        "trace_ref": c.selection.trace_ref.model_dump(mode="json"),
        "page_capture": c.selection.page.model_dump(mode="json"),
    }
    result = judge_source_task(source, facts, actor)
    assert result["evaluation"] == ProductDescriptionEvaluator(c.selection).evaluate(
        c.contract, c.store, guard()
    ).model_dump(mode="json")
    assert result["evaluation"]["status"] == "success"
