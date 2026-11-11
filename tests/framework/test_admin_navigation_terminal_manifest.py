"""Foreign manifest identities fail before private initial/trace dependencies."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_navigation_terminal import (
    read_admin_navigation_terminal,
)
from lab_generate_skill.bootstrap.admin_navigation_captured import (
    read_admin_navigation_captured,
)
from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping_admin.navigation_terminal_schema import (
    AdminNavigationTerminalSelection,
    AdminNavigationCapturedEvidence,
)
from lab_generate_skill.evaluators.shopping_admin.navigation import REQUIREMENTS
from admin_navigation_initial_fixtures import initial_case
from preparation_record_fixtures import put
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


@pytest.mark.parametrize("record", ["terminal", "captured"])
@pytest.mark.parametrize("fault", ["task", "attempt", "owner", "run"])
def test_manifest_identity_rejected_before_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    record: str,
    fault: str,
) -> None:
    with initial_case(tmp_path, monkeypatch, contracts) as c:
        p = c.prepared
        store = p.browser.evidence
        prepared = p.preparation.adapter.load(
            p.binding.publication, p.preparation.request.operation
        )
        binding = TaskBinding.model_validate_json(store.read(prepared.task_binding_ref))
        contract = EvaluationContract(
            identity=prepared.scope.task,
            attempt_id=prepared.scope.attempt_id,
            task_contract_ref=prepared.task_binding_ref,
            public_task_ref=binding.public_task_ref,
            completion_spec_ref=prepared.private_checks_ref,
            requirements=REQUIREMENTS,
            scope="engineering",
        )
        scope = prepared.scope
        if fault == "task":
            scope = scope.model_copy(
                update={
                    "task": scope.task.model_copy(update={"source_task_id": "foreign"})
                }
            )
        elif fault == "attempt":
            scope = scope.model_copy(update={"attempt_id": "foreign"})
        else:
            scope = scope.model_copy(
                update={
                    "owner": scope.owner.model_copy(
                        update={"owner_id" if fault == "owner" else "run_id": "foreign"}
                    )
                }
            )

        def ref(schema: str) -> EvidenceRef:
            return c.selection.browser_spec_ref.model_copy(
                update={"content_schema": schema}
            )

        selected: AdminNavigationTerminalSelection | AdminNavigationCapturedEvidence
        if record == "terminal":
            selected = AdminNavigationTerminalSelection(
                scope=scope,
                initial=c.selection,
                initial_checks_ref=ref("initial-state-checks/1"),
                initial_capture_intent_ref=ref("browser-capture-intent/1"),
                initial_capture_result_ref=ref("browser-capture-result/1"),
                trace_ref=ref("interaction-trace/1"),
                trace_snapshot_ref=ref("trace-journal-snapshot/1"),
                terminal_return_ref=ref("browser-initial-return/1"),
                page_intent_ref=ref("browser-capture-intent/1"),
                page_result_ref=ref("browser-capture-result/1"),
                prepare_request_ref=ref("site-task-request/2"),
                environment_selection_ref=ref("environment-selection/1"),
            )
        else:
            selected = AdminNavigationCapturedEvidence(
                scope=scope,
                terminal_ref=ref("admin-navigation-terminal-selection/1"),
                browser_closure_ref=ref("closure-receipt/1"),
                guard_intent_ref=ref("site-capture-intent/2"),
                guard_result_ref=ref("site-task-result/1"),
            )
        reference = put(store, selected)
        seen: list[EvidenceRef] = []

        class Reads:
            def read(self, actual: EvidenceRef, control: OperationControl) -> bytes:
                seen.append(actual)
                return store.read(actual, control)

        reader = (
            read_admin_navigation_terminal
            if record == "terminal"
            else read_admin_navigation_captured
        )
        with pytest.raises(OwnershipConflict, match="manifest"):
            reader(Reads(), p.preparation.adapter, reference, contract, c.op, guard())
        assert seen == [reference]
