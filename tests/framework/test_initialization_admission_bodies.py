"""Actual initialization producer handoff; live admission is an explicit double."""

from dataclasses import replace
from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.initialization_admission_inputs import (
    InitializationAdmissionInputs,
)
from lab_generate_skill.domain.task_initialization import TaskInitializationPlan
from lab_generate_skill.domain.task_execution import TaskExecutionPlan
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import initialization_case


@pytest.mark.parametrize("fault", ["none", "body", "revoked", "deadline"])
def test_producer_passes_complete_same_call_bodies_and_keeps_final_live_gate(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with initialization_case(node_path, monkeypatch) as c:
        init = c.initialization
        seen: list[InitializationAdmissionInputs] = []

        class BodyAuthority:
            def verify(self, *args: object) -> None:
                raise AssertionError("Adapted initializer must deliver original bodies")

            def verify_with_inputs(
                self,
                plan: TaskExecutionPlan,
                declaration: TaskInitializationPlan,
                inputs: InitializationAdmissionInputs,
                operation: OperationContext,
                control: OperationControl,
            ) -> None:
                seen.append(inputs)
                if fault == "body":
                    inputs = replace(
                        inputs,
                        prepared=inputs.prepared.model_copy(
                            update={
                                "snapshot_ref": inputs.prepared.snapshot_ref.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        ),
                    )
                inputs.require_original(plan, init.declaration_ref, declaration)
                c.authority.verify(plan, declaration, operation, control)
                if len(seen) == 5:
                    if fault == "revoked":
                        raise PermissionError("Current final admission revoked")
                    if fault == "deadline":
                        raise OperationStopped(
                            "DEADLINE_EXCEEDED", operation.operation_id
                        )

        init.authority = BodyAuthority()
        if fault == "none":
            result = c.start()
            assert result.actor.schema_version == "actor-run-request/2"
            assert len(seen) == 5 and all(x is seen[0] for x in seen)
        else:
            with pytest.raises(TaskInitializationUnconfirmed) as caught:
                c.start()
            expected = {
                "body": OwnershipConflict,
                "revoked": PermissionError,
                "deadline": OperationStopped,
            }[fault]
            assert isinstance(caught.value.primary, expected)
            assert len(seen) == (1 if fault == "body" else 5)
            assert init.state.phase == "quarantined"
        assert c.backend.calls.count("project") == (0 if fault == "body" else 1)
        assert c.browser.phase == ("new" if fault == "body" else "open")
    assert c.browser.phase == ("new" if fault == "body" else "closed")
