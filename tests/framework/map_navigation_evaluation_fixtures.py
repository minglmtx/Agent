"""Persist current unified judgment/Reset for fresh-process software review."""

from datetime import datetime, timezone
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
import os
import hashlib
import json
import subprocess
import sys
import pytest
from lab_generate_skill.adapters.sites import step as site_step
from lab_generate_skill.adapters.browsergym import step as browser_step
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.bootstrap.map_navigation_evaluation import (
    map_navigation_evaluator,
)
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.evaluators.map.navigation import (
    REQUIREMENTS,
    NavigationEvaluator,
)
from lab_generate_skill.sites.map.evidence_schema import MapNavigationEvidence
from map_closed_review_fixtures import closed_proof
from map_navigation_terminal_fixtures import NavigationTerminalCase
from map_qualification_fixtures import restore
from preparation_record_fixtures import put
from test_map_qualified_combination import StateAuthority
from test_slurm_commands import guard
import map_navigation_browser_resource_fixtures as initial_module
from browser_resource_fixtures import ResourceCase
from map_registered_worker_fixtures import RegisteredMapCase
from test_site_resource import inspect
from map_navigation_fixtures import navigation_case
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration


def bind_original_contract(c: RegisteredMapCase) -> None:
    """Upgrade a pure unit reference to complete persisted original source bytes."""
    assert isinstance(c.private, NavigationSpec)
    raw = navigation_case(c.scope.task.source_task_id).raw
    ref = c.put(raw, "map-native-contract/1")
    assert ref.sha256 == c.private.native_contract_ref.sha256
    c.private = c.private.model_copy(update={"native_contract_ref": ref})
    inputs = c.configuration.map_inputs
    assert inputs is not None
    c.configuration = SiteWorkerConfiguration.model_validate(
        c.configuration.model_copy(
            update={
                "map_inputs": inputs.model_copy(
                    update={
                        "private_input_sha256": hashlib.sha256(
                            c.private.model_dump_json().encode()
                        ).hexdigest()
                    }
                )
            }
        )
    )
    c.resource.spec = c.resource.spec.model_copy(
        update={"configuration": c.configuration}
    )


def retain_closed_proof(patch: pytest.MonkeyPatch) -> None:
    closed_proof(site_step, patch)
    create = cast(Callable[..., ResourceCase], getattr(initial_module, "resource_case"))

    def browser(*args: Any, **kwargs: Any) -> ResourceCase:
        result = create(*args, **kwargs)
        closed_proof(browser_step, patch)
        return result

    patch.setattr(initial_module, "resource_case", browser)


def selected(t: NavigationTerminalCase) -> MapNavigationEvidence:
    return MapNavigationEvidence(
        environment_ref=t.qualified.environment_ref,
        terminal_ref=t.selection_ref,
        final_guard=t.final_guard,
        browser_closure_ref=t.closure_ref,
    )


def contract(t: NavigationTerminalCase) -> EvaluationContract:
    b = t.baseline_inputs.binding
    return EvaluationContract(
        identity=b.identity,
        attempt_id=t.original.scope.attempt_id,
        task_contract_ref=t.original.binding,
        public_task_ref=b.public_task_ref,
        completion_spec_ref=b.private_spec_ref,
        requirements=REQUIREMENTS,
        scope="engineering",
    )


def evaluator(
    t: NavigationTerminalCase, value: MapNavigationEvidence | None = None
) -> NavigationEvaluator:
    return map_navigation_evaluator(
        selected(t) if value is None else value,
        t.qualified.preparation.records,
        t.original.resource.spec,
        t.qualified.live.site,
        t.read_operation,
    )


def facts(t: NavigationTerminalCase) -> dict[str, Any]:
    c, store, q = t.original, t.original.resource.evidence, t.qualified
    declared, evidence = contract(t), selected(t)
    checked = evaluator(t).evaluate(declared, store, guard(60))
    chosen_reset = restore(q, closure_refs=(t.closure_ref,))
    chosen_ref = put(store, chosen_reset)
    op = q.preparation.request.operation.cleanup(
        "navigation-review-reset-facts", now=datetime.now(timezone.utc), seconds=30
    ).model_copy(update={"recovery_ref": q.plan.environment_recovery_ref})
    inputs = q.qualifications.publish_reset_facts(chosen_ref, op)
    final_op = op.model_copy(update={"operation_id": "navigation-review-reset-summary"})
    receipt = assemble_reset(inputs, final_op)
    states = EvidenceStateRecords(store, c.resource.controls, StateAuthority(c))
    reset_ref = states.publish_reset(receipt, final_op)
    assert receipt.status == "safe"
    b = t.initial.browser
    record = b.journal.read(b.spec.token, b.op)
    return dict(
        engineering_only=True,
        synthetic_kernel=True,
        original_process=os.getpid(),
        configuration=c.resource.spec.model_dump(mode="json"),
        started=q.live.site.model_dump(mode="json"),
        evidence_root=str(c.workspace / "evidence"),
        prepared_browser=dict(
            browser_spec=b.spec.model_dump(mode="json"),
            browser_record=record.model_dump(mode="json"),
            baseline_inputs_ref=c.put(
                t.baseline_inputs.model_dump_json().encode(), "baseline-inputs/1"
            ).model_dump(mode="json"),
            initial_observation_ref=t.baseline_inputs.observation_ref.model_dump(
                mode="json"
            ),
        ),
        qualified_source=dict(
            baseline_ref=t.baseline_ref.model_dump(mode="json"),
            reset_inputs_ref=c.put(
                inputs.model_dump_json().encode(), "reset-inputs/1"
            ).model_dump(mode="json"),
            reset_ref=reset_ref.model_dump(mode="json"),
            reset_selection_ref=chosen_ref.model_dump(mode="json"),
        ),
        judgment=dict(
            selected_evidence_ref=put(store, evidence).model_dump(mode="json"),
            contract_ref=put(store, declared).model_dump(mode="json"),
            evaluation_ref=put(store, checked).model_dump(mode="json"),
        ),
        expected_status=checked.status,
    )


def closed_review(c: RegisteredMapCase, result: dict[str, Any]) -> None:
    result["resource_record"] = inspect(c.resource).model_dump(mode="json")
    path = c.workspace / "navigation-closed-review.json"
    raw = json.dumps(result).encode()
    path.write_bytes(raw)
    env = dict(os.environ)
    framework = Path(__file__).resolve().parent
    env["PYTHONPATH"] = str(framework) + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            str(framework / "map_navigation_closed_review_probe.py"),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert json.loads(child.stdout) == dict(
        separate_process=True,
        evaluation=result["expected_status"],
        reset="safe",
        read_only=True,
        engineering_only=True,
    )
    assert path.read_bytes() == raw
