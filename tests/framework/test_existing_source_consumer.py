"""Real retained graphs through qualification and final plan consumers.

Historical source bytes remain read-only. Only the original-caller/kernel and
transport boundary is an explicit unit premise; no old job is reacquired. The
production default owner/transport still refuse cross-job consumption.
"""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from admin_production_task_plan import (
    AdminProductionBudgets,
    freeze_admin_execution_inputs,
)
from production_task_plan import MapProductionBudgets, freeze_execution_inputs
from production_inputs import OriginalDocuments
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.bootstrap.closed_source_read_bindings import (
    bind_closed_source_read,
)
from lab_generate_skill.bootstrap.admin_navigation_source_qualification import (
    qualify_admin_navigation_source,
)
from lab_generate_skill.bootstrap.map_source_qualification import (
    qualify_map_navigation_source,
)
from lab_generate_skill.bootstrap.map_navigation_source import (
    MapNavigationSourceSelection,
)
from lab_generate_skill.bootstrap.source_browser_assets import SourceBrowserAssets
from lab_generate_skill.domain.closed_source_read import ClosedSourceMaterial
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import (
    EvidenceMetadata,
    EvidenceRef,
    EvidenceRequirements,
)
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.public_context import PublicContextReceipt
from lab_generate_skill.ports.contexts import ContextFactReads
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.shopping_admin.tasks.navigation_spec import (
    AdminNavigationSpec,
)
from source_review_records import ReadOnlyEvidence
from initialization_binding_retained_fixtures import CASES, W
from test_source_publication_handoff import load_retained_source_case
from test_resource_journal import NoCancellation
from browsergym_fixtures import CHROMIUM
from browser_worker_fixtures import LIBS


@pytest.fixture(scope="module", params=("Admin", "Map"))
def original(request: pytest.FixtureRequest) -> Any:
    # Exact current Admin policy, using its retained normal-business producer.
    # The original old graph is separately checked for explicit incompatibility.
    return load_retained_source_case(
        request.param, job=4952933 if request.param == "Admin" else None
    )


def source_case(original: Any, patch: pytest.MonkeyPatch, fault: str = "none") -> Any:
    c = original
    evidence = ReadOnlyEvidence(c.evidence_root)
    clock = SystemClock()
    controls = OperationGuards(clock, NoCancellation())
    original_scope = c.retained["source"].scope
    operation = OperationContext(
        operation_id="unit-consume-original-source",
        run_id=original_scope.owner.run_id,
        owner_id=original_scope.owner.owner_id,
        deadline=clock.utcnow() + timedelta(seconds=120),
    )
    state = SimpleNamespace(fault=fault, reads=0, rights=0)

    class UnitOriginalCaller(OriginalSourceQualificationOwner):
        def require_caller(
            self, op: OperationContext, control: OperationControl
        ) -> None:
            control.checkpoint()
            assert (op.run_id, op.owner_id) == (
                self.scope.owner.run_id,
                self.scope.owner.owner_id,
            )
            state.rights += 1
            if state.fault == "revoked":
                raise PermissionError("Unit original source consumption right revoked")
            if state.fault == "cancelled":
                raise OperationStopped("CANCELLED", op.operation_id)

    owner = UnitOriginalCaller(
        original_scope,
        c.material.site.slurm.execution,
        c.material.site.slurm.parent,
        evidence,
    )

    class UnitRead(ClosedSourceReadTransport):
        def __init__(self) -> None:
            self.store = cast(Any, evidence)

        def require_current(
            self, material: ClosedSourceMaterial, op: OperationContext
        ) -> None:
            owner.require(op, controls.bind(op), new_work=False)
            assert material.site.token.owner == original_scope.owner
            assert material.site.slurm == c.material.site.slurm
            assert (
                material.site.configuration.installation
                == c.material.site.configuration.installation
            )

        def check_current(self, control: OperationControl) -> None:
            owner.require(operation, control, new_work=False)

        def read(
            self,
            material: ClosedSourceMaterial,
            control: OperationControl,
            **kwargs: Any,
        ) -> PublicContextReceipt:
            assert kwargs == {"context_inputs": True}
            state.reads += 1
            reader = bind_closed_source_read(material).contexts(
                evidence, controls, operation
            )
            assert isinstance(reader, ContextFactReads)
            receipt, inputs = reader.load_context_inputs(
                material.context_ref, operation
            )
            self.last_reply = cast(Any, SimpleNamespace(context_inputs=inputs))
            if fault == "cancel_after_read":
                state.fault = "cancelled"
            return receipt

    transport = UnitRead()
    spec, material = c.material.site, c.material
    if fault == "task":
        owner.scope = original_scope.model_copy(
            update={
                "task": original_scope.task.model_copy(
                    update={"source_task_id": "wrong-task"}
                )
            }
        )
    elif fault == "version":
        cfg = spec.configuration
        changed = cfg.installation.model_copy(
            update={"python_executable": "/tmp/unverified-python"}
        )
        spec = spec.model_copy(
            update={"configuration": cfg.model_copy(update={"installation": changed})}
        )
    elif fault == "missing":
        ref = material.context_ref.model_copy(
            update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
        )
        material = material.model_copy(update={"context_ref": ref})

    def no_source_effects(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "Qualified input must not construct/acquire a source resource"
        )

    import lab_generate_skill.bootstrap.admin_navigation_source_qualification as admin
    import lab_generate_skill.bootstrap.map_source_qualification as maps

    for module in (admin, maps):
        patch.setattr(module, "RetainedSiteResource", no_source_effects)
        patch.setattr(module, "SourceQualificationNativeAuthority", no_source_effects)

    control = controls.bind(operation)
    binding = c.retained["source_inputs"].baseline_inputs.binding
    private_bytes = evidence.read(binding.private_spec_ref, control)
    assets = SourceBrowserAssets(
        CHROMIUM,
        CHROMIUM.rsplit("/", 3)[0],
        (LIBS,),
        0,
        10000,
        4096,
        EvidenceRequirements(events=("terminal",)),
    )
    acquisition = material.site_record.events[1].operation.model_copy(
        update={
            "deadline": operation.deadline,
            "cancellation_ref": operation.cancellation_ref,
        }
    )

    def invoke() -> Any:
        kwargs: dict[str, Any] = dict(
            journal=cast(Any, None),
            controls=controls,
            clock=clock,
            prefix="source",
            metadata_seconds=120,
            source_reads=transport,
            publication_root=operation,
            retained_source=material,
        )
        public = c.retained["source_inputs"].context.task
        if c.site == "Admin":
            private = AdminNavigationSpec.model_validate_json(private_bytes)
            raw = evidence.read(private.native_contract_ref, control)
            return qualify_admin_navigation_source(
                owner,
                spec,
                acquisition,
                raw,
                private.native_contract_ref,
                public,
                assets,
                **kwargs,
            )
        private_map = NavigationSpec.model_validate_json(private_bytes)
        selected = MapNavigationSourceSelection(
            evidence.read(private_map.native_contract_ref, control),
            private_map.binding,
            public,
        )
        return qualify_map_navigation_source(
            owner, spec, acquisition, selected, private_map, assets, **kwargs
        )

    return SimpleNamespace(
        invoke=invoke,
        state=state,
        owner=owner,
        operation=operation,
        controls=controls,
        original=c,
    )


def test_qualified_graph_is_consumed_once_without_source_effects_then_reaches_final_plan(
    original: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = source_case(original, monkeypatch)
    source = case.invoke()
    assert source.receipt == original.retained["source"]
    assert source.inputs == original.retained["source_inputs"]
    assert case.owner._sealed and case.state.reads == 1
    writes: list[EvidenceRef] = []

    class Declarations:
        def read(self, reference: EvidenceRef, control: OperationControl) -> bytes:
            raise AssertionError(
                "Final consumer must not reread qualified source bodies"
            )

        def put(
            self, data: bytes, metadata: EvidenceMetadata, control: OperationControl
        ) -> EvidenceRef:
            control.checkpoint()
            ref = evidence_reference(data, metadata)
            writes.append(ref)
            return ref

    freeze: Any = (
        freeze_admin_execution_inputs
        if original.site == "Admin"
        else freeze_execution_inputs
    )
    budgets: Any = (
        AdminProductionBudgets() if original.site == "Admin" else MapProductionBudgets()
    )
    result = freeze(
        source,
        original.retained["declaration"].scope,
        original.actor,
        original.parameters,
        original.actor_inputs.parameters_ref,
        b"unused declaration argument",
        OriginalDocuments(Declarations(), case.controls),
        case.operation,
        budgets,
        original.actor_inputs,
    )
    assert result.task == source.inputs.baseline_inputs.binding
    assert writes and case.state.reads == 1


@pytest.mark.parametrize(
    "fault,expected,reads",
    [
        ("task", OwnershipConflict, 0),
        ("version", OwnershipConflict, 0),
        ("revoked", PermissionError, 0),
        ("missing", EvidenceNotFound, 1),
        ("cancel_after_read", OperationStopped, 1),
    ],
)
def test_existing_source_mismatch_revocation_missing_or_cancellation_never_falls_back(
    original: Any,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected: type[Exception],
    reads: int,
) -> None:
    case = source_case(original, monkeypatch, fault)
    with pytest.raises(expected):
        case.invoke()
    assert not case.owner._sealed and case.state.reads == reads


def test_old_admin_policy_is_retained_and_refused_without_rebuilding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = load_retained_source_case("Admin")
    case = source_case(old, monkeypatch)
    with pytest.raises(
        ValueError, match="Unsupported or incomplete Admin state policy"
    ):
        case.invoke()
    assert case.state.reads == 1
