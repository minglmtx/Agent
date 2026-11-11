"""Real original closed declarations; explicit synthetic current permission edge."""

from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path
import pytest
from lab_generate_skill.adapters.map_runtime.readonly_authority import (
    verify_original_readonly_source,
)
from lab_generate_skill.adapters.ledger.resource_owner import ClaimedRunResourceOwner
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    ClosedSourceContexts,
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from lab_generate_skill.domain.map_navigation_worker_inputs import (
    MapNavigationWorkerInputs,
)
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.map_readonly_binding import bind_map_readonly_inputs
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.ports.lifecycle import OperationControl
from test_closed_actor_acquisition import retained
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault", ["none", "source-ref", "root", "current", "cancel", "material"]
)
def test_readonly_projection_requires_exact_original_source_and_current_gates(
    fault: str,
) -> None:
    material, evidence_root, _ = retained()
    store = ReadOnlyEvidence(evidence_root, max_object_bytes=64 * 1024**2)
    receipt = PublicContextReceipt.model_validate_json(
        store.read(material.context_ref, guard())
    )
    source = material.site.configuration.map_inputs
    assert isinstance(source, MapNavigationWorkerInputs)
    files = source.runtime.files.model_copy(
        update={
            "instance_id": "unit-candidate-assets",
            "node_root": "/tmp/unit-candidate-assets/instance",
        }
    )
    runtime = bind_map_readonly_inputs(
        source.runtime.model_copy(update={"files": files}), source.runtime
    )
    origin = MapOriginPolicy(
        mode="frozen_context",
        source_context_receipt_ref=material.context_ref,
        source_context_ref=receipt.public_context_ref,
        source_start_url="http://127.0.0.1:18001/",
    )
    inputs = source.model_copy(update={"runtime": runtime, "origin": origin})
    token = material.site.token.model_copy(
        update={
            "allocation_id": "unit-candidate-site",
            "expected_resource_id": files.instance_id,
        }
    )
    config = material.site.configuration.model_copy(
        update={"map_inputs": inputs, "files": files, "token": token}
    )
    spec = SiteResourceSpec.model_validate(
        material.site.model_copy(update={"configuration": config})
    )
    owner_id = token.owner
    op = OperationContext(
        operation_id="unit-readonly-current",
        run_id=owner_id.run_id,
        owner_id=owner_id.owner_id,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    calls = []

    class Controls:
        def bind(self, operation: OperationContext) -> OperationControl:
            return guard(60)

    class Transport(ClosedSourceReadTransport):
        def __init__(self) -> None:
            pass

        def require_current(self, *args: Any, **kwargs: Any) -> None:
            calls.append("source-owner")

        def check_current(self, control: OperationControl) -> None:
            control.checkpoint()
            calls.append("storage")
            if fault == "current":
                raise PermissionError("Original storage revoked")
            if fault == "cancel":
                raise OperationStopped("CANCELLED", op.operation_id)

    records = SupervisedClosedSourceContexts(material, Transport(), Controls())
    contexts = ClosedSourceContexts(records, material.context_ref)

    class Authority(OriginalExecutionClaimAuthority):
        def __init__(self) -> None:
            self.contexts = contexts

        def require_caller(self, operation: OperationContext) -> None:
            calls.append("caller")

    class Owner(ClaimedRunResourceOwner):
        def __init__(self) -> None:
            self.authority = Authority()

    if fault == "source-ref":
        origin = origin.model_copy(
            update={
                "source_context_receipt_ref": material.context_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
        inputs = inputs.model_copy(update={"origin": origin})
    elif fault == "root":
        readonly = runtime.readonly_inputs
        assert readonly is not None
        runtime = runtime.model_copy(
            update={
                "readonly_inputs": readonly.model_copy(
                    update={"source_node_root": "/tmp/foreign-assets/instance"}
                )
            }
        )
        inputs = inputs.model_copy(update={"runtime": runtime})
    elif fault == "material":
        records.material = material.model_copy(
            update={
                "context_ref": material.context_ref.model_copy(
                    update={"producer": "foreign"}
                )
            }
        )
    spec = SiteResourceSpec.model_validate(
        spec.model_copy(
            update={"configuration": config.model_copy(update={"map_inputs": inputs})}
        )
    )
    if fault == "none":
        verify_original_readonly_source(Owner(), spec, op, guard())
        assert calls == ["caller", "source-owner", "storage"]
    else:
        with pytest.raises((OwnershipConflict, PermissionError, OperationStopped)):
            verify_original_readonly_source(Owner(), spec, op, guard())


def test_actual_declaration_keeps_two_task_bindings_and_one_readonly_projection(
    tmp_path: Path, node_path: Path
) -> None:
    from production_inputs import OriginalDocuments, declare_site, declared_navigation
    from lab_generate_skill.adapters.clock import SystemClock
    from evidence_control_fixtures import EvidenceFixtureStore

    material, evidence_root, _ = retained()
    source = material.site.configuration.map_inputs
    assert isinstance(source, MapNavigationWorkerInputs)
    store = ReadOnlyEvidence(evidence_root, max_object_bytes=64 * 1024**2)
    receipt = PublicContextReceipt.model_validate_json(
        store.read(material.context_ref, guard())
    )
    origin = MapOriginPolicy(
        mode="frozen_context",
        source_context_receipt_ref=material.context_ref,
        source_context_ref=receipt.public_context_ref,
        source_start_url="http://127.0.0.1:18001/",
    )
    clock = SystemClock()

    class Controls:
        def bind(self, operation: OperationContext) -> OperationControl:
            return guard(60)

    # Only typed parameter declarations and a private fixture CAS are created.
    # Old source metadata supplies asset identities, never current permission.
    (tmp_path / "evidence").mkdir(mode=0o700)
    docs = OriginalDocuments(EvidenceFixtureStore(tmp_path / "evidence"), Controls())
    op = OperationContext(
        operation_id="unit-asset-declarations",
        run_id=source.scope.owner.run_id,
        owner_id=source.scope.owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=60),
    )
    values = []
    for i, sid in enumerate(("4f79336bf1b3f44b0bba", "6e27e10e6049cee4f85d")):
        selected = declared_navigation(sid)
        scope = source.scope.model_copy(
            update={
                "task": selected.public_template.identity,
                "attempt_id": "unit-" + str(i),
                "context_id": "unit-" + str(i),
            }
        )
        parent = node_path / ("candidate-" + str(i))
        parent.mkdir(mode=0o700)
        declared = declare_site(
            selected,
            scope,
            material.site.configuration.installation,
            docs,
            op,
            material.site.slurm.execution,
            material.site.slurm.parent,
            tmp_path,
            parent,
            "unit-" + str(i),
            origin,
            clock,
            defer_acquisition=True,
            readonly_source=source.runtime,
        )
        inputs = declared.spec.configuration.map_inputs
        assert isinstance(inputs, MapNavigationWorkerInputs)
        assert inputs.scope.task == selected.public_template.identity
        assert inputs.runtime.node_tree("routing") == source.runtime.node_tree(
            "routing"
        )
        assert not Path(inputs.runtime.files.node_root).exists()
        values.append(inputs)
    assert values[0].native_contract_sha256 != values[1].native_contract_sha256
    assert values[0].private_input_sha256 != values[1].private_input_sha256
    assert values[0].runtime.readonly_inputs == values[1].runtime.readonly_inputs
    assert values[0].runtime.node_tree("app") != values[1].runtime.node_tree("app")
